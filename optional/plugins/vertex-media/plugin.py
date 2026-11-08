"""vertex-media v0.5.1 -- durable original-group completion mentions."""
from __future__ import annotations

import base64
import asyncio
import re
from pathlib import Path
import sys
import time
from typing import Any

from maibot_sdk import Command, Field, MaiBotPlugin, PluginConfigBase, Tool
from maibot_sdk.types import ToolParameterInfo, ToolParamType

PLUGIN_DIR = Path(__file__).resolve().parent
if str(PLUGIN_DIR) not in sys.path:
    sys.path.insert(0, str(PLUGIN_DIR))
from vertex_media_client import VertexBackend
from vertex_media_core import Ledger, MediaError, MediaService, explicit_request
from image_delivery import transport_image
from completion_notifications import Completions
from media_intent import generation_rejection


class PluginSection(PluginConfigBase):
    enabled: bool = Field(default=True, description="仅处理用户明确请求的图片和语音")
    config_version: str = Field(default="0.4.0", description="配置版本")


class MediaConfig(PluginConfigBase):
    provider_config: str = Field(default="/MaiMBot/config/model_config.toml", description="只读读取 PrimaryProvider；不另存密钥")
    region: str = Field(default="global", description="从 PrimaryProvider 派生区域地址，不修改原配置")
    image_model: str = Field(default="gemini-3.1-flash-image", description="主线程实测的图片模型")
    tts_model: str = Field(default="gemini-3.1-flash-tts-preview", description="主线程实测的语音模型")
    voice: str = Field(default="Leda", description="预置音色")
    tts_style: str = Field(default="年轻清亮、略傲娇但不尖锐，自然亲切", max_length=200, description="中文女声风格，仅指导朗读，不增加正文")
    timeout_seconds: float = Field(default=120, ge=10, le=300, description="单次生成超时，超时绝不自动重试")
    data_dir: str = Field(default="/MaiMBot/data/vertex-media", description="所有群私聊共享的持久化目录；不得按会话分库")


class VertexConfig(PluginConfigBase):
    plugin: PluginSection = Field(default_factory=PluginSection)
    media: MediaConfig = Field(default_factory=MediaConfig)


def context_value(kwargs, field):
    for source in [kwargs] + [kwargs.get(k) for k in ("tool_execution_context", "execution_context", "tool_context", "context")]:
        value = source.get(field) if isinstance(source, dict) else getattr(source, field, None)
        if value:
            return str(value)
    return ""


def plain_text(message):
    # Raw text only: never image captions, reply history, or model-provided reasoning.
    segments = message.get("raw_message") or []
    texts = []
    for seg in segments:
        if isinstance(seg, dict) and seg.get("type") == "text":
            data = seg.get("data")
            texts.append(data if isinstance(data, str) else str((data or {}).get("text", "")))
    return " ".join(texts).strip()


class VertexMediaPlugin(MaiBotPlugin):
    config_model = VertexConfig

    async def on_load(self):
        self.ledger = Ledger(self.config.media.data_dir)
        self.completions = Completions(self.ledger)
        self.service = MediaService(self.ledger, VertexBackend(self.config.media), self._send, self._notice)
        self.completion_poller=asyncio.create_task(self.poll_completions())
        self.ctx.logger.info("vertex-media 0.5.1 已加载；核对发送记录后补发，通知持久化去重")

    async def on_unload(self):
        if poller:=getattr(self,'completion_poller',None):
            poller.cancel()
            await asyncio.gather(poller,return_exceptions=True)

    async def poll_completions(self):
        while True:
            try:
                await self.completions.flush_pending(self.ctx.send.hybrid)
                await self.completions.flush(self.ctx.send.hybrid)
            except asyncio.CancelledError:raise
            except Exception:pass
            await asyncio.sleep(2)

    async def on_config_update(self, scope: str, config_data: dict[str, Any], version: str):
        # Runner applies validated self config before invoking this callback.
        # Never switch quota databases during a configuration reload.
        del scope, config_data, version
        previous = self.service
        service = MediaService(self.ledger, VertexBackend(self.config.media), self._send, self._notice)
        service.active = previous.active
        service.sending = previous.sending
        self.service = service
        self.ctx.logger.info("vertex-media 配置已更新；继续使用原共享额度账本")

    async def _notice(self, kind, session, event):
        if event == 'start' and kind == 'image':
            await self.ctx.send.text('好的，本鱼要开始画啦！', session)
        elif event == 'delivery_failed':
            if kind == 'image':
                await self.ctx.send.text('图片已经画好并保存，但 QQ 的发送确认还没回来。我会先核对聊天记录，确认没发出再补发，不会重新画或再扣次数。', session)
                return
            command = '/重发图片' if kind == 'image' else '/重发语音'
            await self.ctx.send.text(f'已经生成好了，但 QQ 发送失败或回执不明。成品已保存，可用 {command} 重发，不会再扣生成次数。', session)
        elif event == 'generation_failed':
            await self.ctx.send.text('这次没能完成生成，可用 /媒体额度 查看状态；结果不明时本鱼不会自动重复生成。', session)

    async def _send(self, kind, path, session):
        if kind == 'image':
            import asyncio
            path = await asyncio.to_thread(transport_image, path)
        encoded = base64.b64encode(path.read_bytes()).decode("ascii")
        if kind == "image":
            result = await self.ctx.send.image(encoded, session, return_details=True)
            return result
        else:
            result = await self.ctx.send.custom("voice", encoded, session, return_details=True)
        return result.get("sent") is True if isinstance(result, dict) else result is True

    async def _current_request(self, session, kind=None, operation=None, requester="", anchor_id="", require_anchor=False):
        now = time.time()
        result = await self.ctx.message.get_by_time_in_chat(session, str(now - 600), str(now),
            limit=6, limit_mode="latest", filter_mai=True, filter_command=False, include_binary_data=False)
        if isinstance(result, list):
            messages = result
        elif isinstance(result, dict) and result.get("success") is True:
            messages = result.get("messages", [])
        else:
            messages = []
        if requester:
            messages=[m for m in messages if str(((m.get('message_info') or {}).get('user_info') or {}).get('user_id',''))==requester]
        if not anchor_id and (not messages or not isinstance(messages[0], dict)):
            raise MediaError("无法核验当前用户请求，请用户重新明确提出")

        # Tool authorization uses the host anchor, never a newer group message.
        if require_anchor and not anchor_id:
            raise MediaError("缺少原始请求定位，未启动生成；请稍后重试")
        if anchor_id:
            result = await self.ctx.message.get_by_id(anchor_id, stream_id=session, include_binary_data=False)
            anchor = result.get("message") if isinstance(result, dict) and result.get("success") is True else result
            if not isinstance(anchor, dict) or str(anchor.get("message_id", "")) != str(anchor_id):
                raise MediaError("原始请求不存在，未启动生成")
            owner = str(((anchor.get("message_info") or {}).get("user_info") or {}).get("user_id", ""))
            if (anchor.get("session_id") != session or anchor.get("is_notify") or anchor.get("is_mai")
                    or not owner or (requester and owner != requester)
                    or not 0 <= now - float(anchor.get("timestamp", 0)) <= 600):
                raise MediaError("原始请求身份、会话或时效不匹配，未启动生成")
            for later in messages:
                if (isinstance(later, dict) and later.get("session_id") == session
                        and float(later.get("timestamp", 0)) > float(anchor["timestamp"])
                        and str(((later.get("message_info") or {}).get("user_info") or {}).get("user_id", "")) == owner
                        and re.search(r"(?:取消|别画了|不要画了|停止画图|不用画了)", plain_text(later))):
                    raise MediaError("发起人已取消，未启动生成")
            return anchor, plain_text(anchor)

        # Direct commands retain their own freshly received command context.
        valid = [m for m in messages if isinstance(m, dict) and m.get("session_id") == session
                 and m.get("message_id") and not m.get("is_notify")
                 and 0 <= now - float(m.get("timestamp", 0)) <= 600]
        if not valid:
            raise MediaError("当前请求上下文无效或已过期，请用户重新提出")
        target_message = max(valid, key=lambda m: float(m.get("timestamp", 0)))
        return target_message, plain_text(target_message)

    async def _reference(self, session, current, reference_message_id, image_index):
        if type(image_index) is not int or image_index < 0:
            raise MediaError("原图序号无效")

        candidates = []
        if reference_message_id:
            candidates.append(str(reference_message_id))
        if current.get("reply_to"):
            candidates.append(str(current["reply_to"]))
        if current.get("message_id"):
            candidates.append(str(current["message_id"]))

        image_message = None
        for candidate_id in candidates:
            res = await self.ctx.message.get_by_id(candidate_id, stream_id=session, include_binary_data=True)
            msg = res.get("message") if isinstance(res, dict) and res.get("success") is True else res if isinstance(res, dict) else None
            if isinstance(msg, dict) and any(isinstance(p, dict) and p.get("type") == "image" for p in msg.get("raw_message", [])):
                image_message = msg
                break

        if image_message is None:
            now = time.time()
            recent = await self.ctx.message.get_by_time_in_chat(session, str(now - 600), str(now),
                limit=6, limit_mode="latest", filter_mai=False, filter_command=False, include_binary_data=True)
            msgs = recent.get("messages", []) if isinstance(recent, dict) else recent if isinstance(recent, list) else []
            for msg in reversed(msgs):
                if isinstance(msg, dict) and any(isinstance(p, dict) and p.get("type") == "image" for p in msg.get("raw_message", [])):
                    image_message = msg
                    break
        if isinstance(image_message, dict) and image_message.get("success") is True:
            image_message = image_message.get("message")
        if not isinstance(image_message, dict) or image_message.get("session_id") != session:
            raise MediaError("当前会话找不到指定原图")
        images = [p for p in image_message.get("raw_message", []) if isinstance(p, dict) and p.get("type") == "image"]
        if image_index >= len(images):
            raise MediaError("缺少原图，请用户引用或重发图片")
        encoded = images[image_index].get("binary_data_base64", "")
        if not isinstance(encoded, str) or len(encoded) > 28 * 1024 * 1024:
            raise MediaError("原图过大或不可读取")
        try:
            data = base64.b64decode(encoded, validate=True)
            from PIL import Image
            import io
            with Image.open(io.BytesIO(data)) as im:
                fmt = im.format
                im.verify()
            mime = {"PNG": "image/png", "JPEG": "image/jpeg", "WEBP": "image/webp"}.get(fmt)
            if not mime or not data or len(data) > 20 * 1024 * 1024:
                raise ValueError()
            return data, mime
        except Exception as exc:
            print('MEDIA_CMD_EXC:', type(exc), exc)
            raise MediaError("原图无效，仅支持20MB以内 PNG/JPEG/WebP") from None

    async def _execute(self, kind, operation, text, job_id, kwargs, reference_message_id="", image_index=0):
        try:
            if not self.config.plugin.enabled:
                raise MediaError("插件已停用")
            session = context_value(kwargs, "stream_id") or context_value(kwargs, "session_id")
            if not session:
                raise MediaError("缺少当前会话")
            current, actual = await self._current_request(session, kind=kind, operation=operation,
                requester=context_value(kwargs, "user_id"), anchor_id=context_value(kwargs, "anchor_message_id"), require_anchor=True)
            if not explicit_request(actual, kind, operation):
                return {"success": False, "error_code": "local_intent_rejected", "retryable": False,
                        "upstream_called": False, "content": (generation_rejection(actual) if kind == "image" else "当前用户未明确要求语音生成。") + " 这是本地意图校验，不是生成接口故障；不得改写参数反复尝试。"}
            reference = None
            if kind == "image":
                is_edit_request = bool(re.search(r"(?:改|编辑|修改|换背景|去掉|加字|重绘|换成|变成|改色|改成)", actual))
                if operation == "edit" or is_edit_request:
                    try:
                        reference = await self._reference(session, current, reference_message_id, image_index)
                        if reference is not None:
                            operation = "edit"
                    except Exception:
                        if operation == "edit":
                            raise
                if reference is None:
                    if is_edit_request and operation == "generate":
                        raise MediaError("当前消息要求编辑，但未找到原图，请用户引用或重发原图")
                    if re.search(r"(?:大肥鱼|肥鱼|自己|本鱼|自画像|形象|三视图|人设|鲸鱼娘)", (actual + " " + text).lower()):
                        media_cfg = getattr(self.config, "media", None)
                        data_dir = getattr(media_cfg, "data_dir", None)
                        if data_dir:
                            sheet_path = Path(data_dir) / "dafeiyu_character_sheet.png"
                            if sheet_path.exists():
                                reference = (sheet_path.read_bytes(), "image/png")
            self.completions.remember(current,kind,operation)
            result = await self.service.run(kind, session, current["message_id"], text,
                operation=operation, reference=reference, job_id=job_id)
            if kind == 'image' and result.get('notification_owner') == 'media_plugin':
                result['stop_after_execution'] = True
            return result
        except MediaError as exc:
            return {"success": False, "content": str(exc)}
        except Exception:
            # SDK and upstream exceptions may carry sensitive data. No raw logging.
            return {"success": False, "content": "媒体工具内部错误；未自动重新生成，请先查询额度或任务状态"}

    @Tool("vertex_draw", description="仅在用户明确要求新画、绘制、生成或编辑时使用，理解自然表达，不要求固定口令。随机图用send_setu；仅说发张某角色图片先澄清，不调用生成。operation=generate/edit/resend/quota。成功生成后发送失败只能resend，不得重新生成。相同消息去重；明确新请求须用户另发消息。",
        parameters=[
            ToolParameterInfo(name="operation", param_type=ToolParamType.STRING, description="generate/edit/resend/quota", required=False),
            ToolParameterInfo(name="prompt", param_type=ToolParamType.STRING, description="图片内容或修改要求，最多2000字", required=False),
            ToolParameterInfo(name="reference_message_id", param_type=ToolParamType.STRING, description="编辑用当前会话原图ID；默认引用消息或当前消息", required=False),
            ToolParameterInfo(name="image_index", param_type=ToolParamType.INTEGER, description="原图索引，从0开始", required=False),
            ToolParameterInfo(name="job_id", param_type=ToolParamType.STRING, description="重发成品ID，默认当前会话最新成品", required=False)], visibility="visible")
    async def vertex_draw(self, operation="generate", prompt="", reference_message_id="", image_index=0, job_id="", **kwargs: Any):
        return await self._execute("image", operation, prompt, job_id, kwargs, reference_message_id, image_index)

    @Tool("vertex_tts", description="已停用，请改用 unified_tts_action",
        parameters=[
            ToolParameterInfo(name="operation", param_type=ToolParamType.STRING, description="generate/resend/quota", required=False),
            ToolParameterInfo(name="text", param_type=ToolParamType.STRING, description="实际朗读文本，最多300字", required=False),
            ToolParameterInfo(name="job_id", param_type=ToolParamType.STRING, description="重发成品ID，默认当前会话最新语音", required=False)], visibility="hidden")
    async def vertex_tts(self, operation="generate", text="", job_id="", **kwargs: Any):
        return await self._execute("audio", operation, text, job_id, kwargs)

    @Command('vertex_media_direct', description='直接生成图片或语音、查询额度和重发，不经过聊天模型规划', pattern=r'^\s*/(?P<media_operation>画图|改图|修图|语音|媒体额度|重发图片|重发语音)(?:\s+(?P<media_text>[\s\S]{1,2000}))?\s*$', permission='public')
    async def media_command(self, stream_id='', platform='', matched_groups=None, **kwargs):
        if platform != 'qq' or not stream_id:
            return False, '仅用于已开放的 QQ 会话', True
        try:
            current, actual = await self._current_request(stream_id, requester=context_value(kwargs,'user_id'))
            match = re.fullmatch(r'\s*/(画图|改图|修图|语音|媒体额度|重发图片|重发语音)(?:\s+([\s\S]{1,2000}))?\s*', actual)
            if match is None:
                raise MediaError('当前真实消息不是媒体命令')
            command, text = match.group(1), (match.group(2) or '').strip()
            kind = 'audio' if command in {'语音', '重发语音'} else 'image'
            operation = 'quota' if command == '媒体额度' else 'resend' if command.startswith('重发') else 'edit' if command in {'改图', '修图'} else 'generate'
            if operation == 'generate' and not text:
                raise MediaError('用法：/画图 图片描述，/改图 修改要求，或 /语音 需要朗读的文字')
            if not self.config.plugin.enabled:
                raise MediaError('插件已停用')
            reference = await self._reference(stream_id, current, '', 0) if operation == 'edit' else None
            if reference is None and kind == 'image':
                if re.search(r"(?:大肥鱼|肥鱼|自己|本鱼|自画像|形象|三视图|人设|鲸鱼娘)", (actual + ' ' + text).lower()):
                    media_cfg = getattr(self.config, 'media', None)
                    data_dir = getattr(media_cfg, 'data_dir', None)
                    if data_dir:
                        sheet_path = Path(data_dir) / 'dafeiyu_character_sheet.png'
                        if sheet_path.exists():
                            reference = (sheet_path.read_bytes(), 'image/png')
            self.completions.remember(current,kind,operation)
            result = await self.service.run(kind, stream_id, current['message_id'], text, operation=operation, reference=reference)
        except MediaError as exc:
            result = {'success': False, 'content': str(exc)}
        except Exception as e:
            import traceback; traceback.print_exc()
            result = {'success': False, 'content': '媒体命令执行失败，未自动重新生成；可用 /媒体额度 查询'}
        if result.get('success') and command == '媒体额度':
            quota = result['quota']
            lines = ['今日共享额度（北京时间零点重置）：']
            for key, label in [('image', '图片'), ('audio', '语音')]:
                value = quota[key]
                lines.append(f"{label}已用 {value['used']}/{value['limit']}，处理中或结果待确认 {value['reserved']}")
            lines.append('视频暂未启用。')
            result['content'] = '\n'.join(lines)
        if not result.get('success') or command == '媒体额度':
            await self.ctx.send.text(str(result.get('content') or result), stream_id)
        return bool(result.get('success')), str(result.get('content', '')), True


def create_plugin():
    return VertexMediaPlugin()
