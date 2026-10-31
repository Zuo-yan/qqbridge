"""Codex 绘图/编辑插件。

通过本地 codex CLI（需已登录、需走本机代理）生成或编辑图片：
- ``/gpt <提示词>``：用 codex 生成新图片并回传当前聊天流；
- **回复一条含图片的消息**再发 ``/gpt <提示词>``：把该图作为参考图触发图片编辑。

送入 codex 之前，会另起一个上下文的多模态 LLM（默认 maibot 的 ``vlm`` 视觉模型）
对「提示词 [+ 参考图]」做合规审查，审查不通过则拒绝执行。

codex 登录由用户自行进入 CLI 完成，本插件不托管登录，仅在未登录/网络异常时
给出对应提示。
"""

from __future__ import annotations

from dataclasses import dataclass
from maibot_sdk import Command, Field, MaiBotPlugin, PluginConfigBase, Tool
from maibot_sdk.types import ToolParameterInfo, ToolParamType
from pathlib import Path
from typing import Any, List, Tuple

import asyncio
import base64
import json
import os
import re
import signal
import tempfile
import uuid
import time


DEFAULT_PROXY_URL = "127.0.0.1:7890"
DEFAULT_REVIEW_MODEL = "vlm"

# codex 生成图片后可能继续执行检查、复制等步骤。插件不等待整个 agent 会话结束，
# 而是短间隔检测图片是否已经完整落盘。
_IMAGE_POLL_INTERVAL_SECONDS = 0.2
_IMAGE_STABLE_CHECKS = 2
_PROGRESS_POLL_INTERVAL_SECONDS = 5.0
# 即使持续返回活动信号，也不能让未出图任务无限占用进程和并发名额。
_MAX_JOB_DURATION_SECONDS = 30 * 60.0
_PROCESS_TERMINATE_GRACE_SECONDS = 1.0

# codex 出图产物扩展名
_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}

# 参考图魔数识别（与 MAIMAI-comfy 保持一致的写法）
_IMAGE_FORMATS: tuple[tuple[bytes, str, str], ...] = (
    (b"\x89PNG\r\n\x1a\n", ".png", "image/png"),
    (b"\xff\xd8\xff", ".jpg", "image/jpeg"),
)

# /gpt 的「仅审查」子命令触发词（取提示词首词，忽略大小写）
_REVIEW_SUBCOMMANDS = {"审查", "check", "review"}

# /gpt 命令匹配：宿主用 re.search 匹配纯文本，因此不锚定文本开头，以兼容「图片 + /gpt」
# 同一条消息发送时图片描述/占位文本排在 /gpt 之前的情况；前瞻确保 /gpt 后是空白或行尾，
# 避免 /gptxxx 之类误匹配。
_GPT_COMMAND_PATTERN = r"/gpt(?=\s|$)(?P<prompt>[\s\S]*)"


class ComplianceRejected(RuntimeError):
    """合规审查不通过，禁止执行。"""


class CodexMissingError(RuntimeError):
    """未找到 codex 可执行文件。"""


class CodexLoginError(RuntimeError):
    """codex 未登录或鉴权失败。"""


class CodexNetworkError(RuntimeError):
    """codex 出图时的网络/代理失败。"""


class CodexOutputError(RuntimeError):
    """codex 运行结束但未产出图片。"""


@dataclass(frozen=True)
class ReferenceImage:
    """作为编辑参考的图片。"""

    content: bytes
    suffix: str
    mime_type: str


class PluginSectionConfig(PluginConfigBase):
    """插件基础配置。"""

    __ui_label__ = "插件"
    __ui_icon__ = "package"
    __ui_order__ = 0

    enabled: bool = Field(default=True, description="是否启用插件")
    config_version: str = Field(default="3", description="配置版本")


class CodexSection(PluginConfigBase):
    """codex CLI 与代理配置。"""

    __ui_label__ = "Codex"
    __ui_icon__ = "image"
    __ui_order__ = 1

    codex_path: str = Field(default="codex", description="codex 可执行文件路径，留空/默认按 PATH 查找")
    proxy_url: str = Field(
        default=DEFAULT_PROXY_URL,
        description="HTTP 代理地址（host:port），codex 调用需要代理；留空则直连",
        json_schema_extra={"placeholder": "host:port"},
    )
    model: str = Field(default="", description="codex 对话/代理模型，留空则使用 codex 自身默认")
    reasoning_effort: str = Field(
        default="medium", description="codex 代理思考努力，留空则使用 codex 自身默认"
    )
    timeout_seconds: float = Field(
        default=180.0,
        ge=10.0,
        description="连续无活动超时（秒）；有活动时继续等待，但总出图时长最多 30 分钟",
    )
    max_concurrent_jobs: int = Field(
        default=4,
        ge=1,
        description="同时执行的出图任务上限；达到上限时静默忽略新请求，不排队",
    )
    generated_dir: str = Field(
        default="", description="codex 生成图片目录，留空则使用 $CODEX_HOME/generated_images"
    )


class ComplianceSection(PluginConfigBase):
    """送入 codex 前的 LLM 合规审查配置。"""

    __ui_label__ = "合规审查"
    __ui_icon__ = "shield"
    __ui_order__ = 2

    enabled: bool = Field(default=True, description="是否在送入 codex 前进行 LLM 合规审查")
    review_model: str = Field(
        default=DEFAULT_REVIEW_MODEL,
        description="审查用的 maibot 模型任务名（默认 vlm = 多模态视觉模型）",
    )
    timeout_ms: int = Field(default=60000, ge=1000, description="审查调用超时（毫秒）")


class CodexDrawConfig(PluginConfigBase):
    """Codex 绘图插件完整配置。"""

    plugin: PluginSectionConfig = Field(default_factory=PluginSectionConfig)
    codex: CodexSection = Field(default_factory=CodexSection)
    compliance: ComplianceSection = Field(default_factory=ComplianceSection)


# 合规审查提示词（内联简体中文常量；本项目首选语言为简体中文）。
# 有参考图时会在其前附带图片，让多模态模型连同参考图一起审查。
_REVIEW_INSTRUCTION = (
    "你是图片生成请求的合规审查员。请根据用户实际要求生成的画面进行判断；若附带参考图，"
    "需结合图片与文字判断。不要仅因出现敏感关键词、角色身份、画风或题材名称而拒绝。\n"
    "只有请求明确且实质性地要求以下内容时才拒绝：露骨色情或性行为；任何涉及未成年人或"
    "疑似未成年人的色情化内容；写实且重度的肢解、虐杀或血腥折磨；煽动或指导现实中的"
    "暴力、犯罪、自残；基于受保护特征的仇恨或去人化攻击\n"
    "以下内容应允许：普通人物与公众人物、泳装或非色情暴露、恋爱与亲密互动、医学或古典"
    "艺术语境下的非色情人体、武器或非写实打斗、轻微血迹、虚构恐怖、政治新闻与讽刺、"
    "宗教题材、知名角色、画风参考、戏仿，以及一般冒犯性但不构成上述严重伤害的内容。\n"
    "从上下文无法明确确认违规时应判定通过；不要猜测人物年龄、恶意意图或画面之外的用途。\n"
    "请只输出一个 JSON 对象，不要输出任何其他内容（不要解释、不要多余文字），格式：\n"
    '{"review": "true"} 表示通过；{"review": "false"} 表示不通过'
)


class CodexDrawPlugin(MaiBotPlugin):
    """Codex 绘图/编辑插件。"""

    config_model = CodexDrawConfig

    def __init__(self) -> None:
        super().__init__()
        # 后台出图任务池，避免任务被 GC，并在卸载时统一取消
        self._background_tasks: set[asyncio.Task[Any]] = set()

    async def on_load(self) -> None:
        self.ctx.logger.info("Codex 绘图插件已加载，持久化任务恢复检查中。")
        recovery = asyncio.create_task(self._recover_jobs())
        self._background_tasks.add(recovery)
        recovery.add_done_callback(self._background_tasks.discard)

    async def on_unload(self) -> None:
        for task in list(self._background_tasks):
            task.cancel()
        if self._background_tasks:
            await asyncio.gather(*self._background_tasks, return_exceptions=True)
        self._background_tasks.clear()

    async def on_config_update(self, scope: str, config_data: dict[str, object], version: str) -> None:
        """配置热更新回调。config_model 模式下 self.config 会自动刷新，无需手动读取。"""
        del scope, config_data, version

    # ------------------------------------------------------------------ #
    # 配置派生
    # ------------------------------------------------------------------ #

    def _normalize_proxy(self, raw: str) -> str:
        """把 host:port 归一化成带 scheme 的代理地址。"""
        value = raw.strip()
        if not value:
            return ""
        if not re.match(r"^https?://", value):
            value = f"http://{value}"
        return value

    def _build_proxy_env(self) -> dict[str, str]:
        """构造 codex 子进程环境变量；代理留空则清除继承的代理变量（直连）。"""
        env = os.environ.copy()
        proxy = self._normalize_proxy(self.config.codex.proxy_url)
        for key in ("HTTPS_PROXY", "HTTP_PROXY", "ALL_PROXY"):
            if proxy:
                env[key] = proxy
                env[key.lower()] = proxy
            else:
                env.pop(key, None)
                env.pop(key.lower(), None)
        return env

    def _codex_gen_dir(self) -> Path:
        """codex 图片产物根目录。"""
        configured = self.config.codex.generated_dir.strip()
        if configured:
            return Path(configured).expanduser()
        codex_home = Path(os.environ.get("CODEX_HOME", "~/.codex")).expanduser()
        return codex_home / "generated_images"

    # ------------------------------------------------------------------ #
    # 参考图读取（回复图片触发编辑）
    # ------------------------------------------------------------------ #

    @staticmethod
    def _extract_reply_message_id(message: Any) -> str:
        """从命令消息载荷中读取被回复消息 ID。"""
        if not isinstance(message, dict):
            return ""
        reply_to = str(message.get("reply_to") or "").strip()
        if reply_to:
            return reply_to

        raw_message = message.get("raw_message")
        if not isinstance(raw_message, list):
            return ""
        for segment in raw_message:
            if not isinstance(segment, dict) or str(segment.get("type") or "").lower() != "reply":
                continue
            data = segment.get("data")
            if isinstance(data, dict):
                target_message_id = str(data.get("target_message_id") or "").strip()
                if target_message_id:
                    return target_message_id
        return ""

    @staticmethod
    def _detect_image_format(content: bytes) -> tuple[str, str]:
        """按魔数识别参考图格式，返回 (文件后缀, MIME)。"""
        for signature, suffix, mime_type in _IMAGE_FORMATS:
            if content.startswith(signature):
                return suffix, mime_type
        if content.startswith(b"RIFF") and len(content) >= 12 and content[8:12] == b"WEBP":
            return ".webp", "image/webp"
        raise ValueError("参考图仅支持 PNG、JPEG 或 WebP 格式")

    def _resolve_reference_message_id(self, message: Any) -> str:
        """解析参考图来源消息 ID。

        - 优先被回复消息（reply_to / reply 段），对应「回复含图消息后发 /gpt」；
        - 否则回退到当前命令消息自身（message_id），对应「同一条消息里带图 + /gpt」。
        """
        if not isinstance(message, dict):
            return ""
        reply_message_id = self._extract_reply_message_id(message)
        if reply_message_id:
            return reply_message_id
        return str(message.get("message_id") or "").strip()

    async def _load_reference_image(
        self, message: Any, stream_id: str, *, image_index: int = 0, required: bool = False,
    ) -> ReferenceImage | None:
        """读取参考图（被回复消息或当前命令消息中的第一张静态图片）；无图时返回 None（不视为错误）。"""
        reference_message_id = self._resolve_reference_message_id(message)
        if not reference_message_id:
            if required:
                raise ValueError("请从当前聊天中选定要修改的原图消息，或请用户引用/重发原图。")
            return None

        if type(image_index) is not int or image_index < 0:
            raise ValueError("图片序号必须为非负整数，第一张是0。")

        reference_message = await self.ctx.message.get_by_id(
            reference_message_id,
            stream_id=stream_id,
            include_binary_data=True,
        )
        if not isinstance(reference_message, dict):
            if required:
                raise ValueError("当前聊天中找不到指定原图消息，请用户引用或重发原图。")
            return None

        # Only the current chat may supply a reference; never fall back to another chat.
        actual_stream = str(reference_message.get("session_id") or reference_message.get("stream_id") or "")
        if actual_stream and actual_stream != stream_id:
            raise ValueError("参考图不属于当前聊天。")

        raw_message = reference_message.get("raw_message")
        if not isinstance(raw_message, list):
            if required:
                raise ValueError("指定消息中没有可读取的原图。")
            return None
        images = [segment for segment in raw_message if isinstance(segment, dict)
                  and str(segment.get("type") or "").lower() in {"image", "emoji"}]
        if not images:
            if required:
                raise ValueError("指定消息没有图片，请选择真正含原图的消息，而不是图片文字描述。")
            return None
        if image_index >= len(images):
            raise ValueError(f"该消息只有{len(images)}张图片，无法读取序号{image_index}。")
        image_segment = images[image_index]

        encoded = image_segment.get("binary_data_base64")
        if not isinstance(encoded, str) or not encoded:
            raise ValueError("原图数据已不可读取，请用户重发；不能仅凭图片描述进行原图编辑。")
        if len(encoded) > 28 * 1024 * 1024:
            raise ValueError("参考图过大，请发送20MB以内的图片。")
        try:
            content = base64.b64decode(encoded, validate=True)
        except ValueError as exc:
            raise ValueError("原图数据损坏，请用户重发。") from exc
        if not content:
            raise ValueError("原图数据为空，请用户重发。")
        if len(content) > 20 * 1024 * 1024:
            raise ValueError("参考图过大，请发送20MB以内的图片。")
        try:
            suffix, mime_type = self._detect_image_format(content)
        except ValueError:
            # QQ animated stickers are usable as a static first-frame reference.
            if not content.startswith((b"GIF87a", b"GIF89a", b"BM")):
                raise
            from PIL import Image
            import io
            with Image.open(io.BytesIO(content)) as im:
                im.seek(0)
                out = io.BytesIO()
                im.convert("RGBA").save(out, format="PNG")
                content = out.getvalue()
            suffix, mime_type = ".png", "image/png"
        return ReferenceImage(content=content, suffix=suffix, mime_type=mime_type)

    # ------------------------------------------------------------------ #
    # 合规审查（另起上下文的多模态 LLM 调用）
    # ------------------------------------------------------------------ #

    async def _review_prompt(self, prompt: str, ref: ReferenceImage | None) -> bool:
        """另起上下文跑一次多模态合规审查，返回是否通过（True=通过，False=拒绝）。"""
        task_name = self.config.compliance.review_model.strip() or DEFAULT_REVIEW_MODEL

        if ref is not None:
            data_url = f"data:{ref.mime_type};base64,{base64.b64encode(ref.content).decode('utf-8')}"
            review_prompt: Any = [
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": data_url},
                        {
                            "text": "这是用户作为参考图的图片，请连同下面的文字请求一起审查：\n"
                            f"{prompt}\n\n{_REVIEW_INSTRUCTION}"
                        },
                    ],
                }
            ]
        else:
            review_prompt = f"{prompt}\n\n{_REVIEW_INSTRUCTION}"

        result = await self.ctx.llm.generate(
            prompt=review_prompt,
            # review_model 配置存储的是任务名；SDK 的 model 参数用于指定具体模型。
            task_name=task_name,
            temperature=0.2,
            max_tokens=64,
            timeout_ms=self.config.compliance.timeout_ms,
        )
        if not result.get("success"):
            raise RuntimeError(f"合规审查调用失败：{result.get('error') or result.get('response') or result}")
        return self._parse_review_verdict(str(result.get("response") or ""))

    async def _compliance_check(self, prompt: str, ref: ReferenceImage | None) -> None:
        """出图前置审查；不通过则抛 ComplianceRejected。"""
        if not self.config.compliance.enabled:
            return
        if not await self._review_prompt(prompt, ref):
            raise ComplianceRejected("内容不合规")

    @staticmethod
    def _parse_review_verdict(response: str) -> bool:
        """解析审查模型的裁决。约定模型只输出 {"review":"true"} 或 {"review":"false"}；
        无法解析出合法裁决时按「不通过」处理（合规门禁失败关闭）。"""
        text = response.strip()
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            try:
                payload = json.loads(match.group(0))
            except (json.JSONDecodeError, TypeError):
                payload = None
            if isinstance(payload, dict):
                value = payload.get("review")
                if isinstance(value, bool):
                    return value
                if isinstance(value, str):
                    return value.strip().lower() == "true"
        # 无合法 JSON / 缺少 review 字段 / 值非法：合规门禁失败关闭，判定不通过
        return False

    # ------------------------------------------------------------------ #
    # codex 出图
    # ------------------------------------------------------------------ #

    @staticmethod
    def _build_codex_prompt(prompt: str, reference_path: str = "") -> str:
        """要求 codex 明确调用图片生成能力，并在产图后立即结束。"""
        reference_instruction = (
            "这是基于原图的图片编辑任务。随本轮输入附带的图片就是用户指定的原图，"
            f"本地原文件路径：{reference_path}。\n"
            "必须把该原图作为图像编辑工具的输入/参考图传入，使用referenced_image_paths"
            "或当前工具等价的参考图参数；如工具只接收会话图片，则引用本轮附图。"
            "保留用户未要求改变的主体、构图与细节，只修改用户明确要求的部分。"
            "不要只看图后按文字另画一张，不要将原图当作生成结果返回。\n"
            if reference_path else ""
        )
        return (
            "$imagegen\n"
            "请调用图片生成能力完成下面的生成或编辑请求。图片成功生成并保存后立即结束任务，"
            "不要复制、移动、打开、检查或解释产物。\n\n"
            f"{reference_instruction}{prompt}"
        )

    @staticmethod
    def _is_complete_image(content: bytes, suffix: str) -> bool:
        """检查图片文件是否具有对应格式的完整结束标记。"""
        normalized_suffix = suffix.lower()
        if normalized_suffix == ".png":
            return content.startswith(b"\x89PNG\r\n\x1a\n") and content.endswith(b"IEND\xaeB\x60\x82")
        if normalized_suffix in {".jpg", ".jpeg"}:
            return content.startswith(b"\xff\xd8\xff") and content.endswith(b"\xff\xd9")
        if normalized_suffix == ".webp":
            if not (content.startswith(b"RIFF") and len(content) >= 12 and content[8:12] == b"WEBP"):
                return False
            return len(content) >= int.from_bytes(content[4:8], "little") + 8
        return False

    def _read_complete_image(self, image_path: Path | None) -> tuple[bytes, str] | None:
        """读取完整的图片；文件仍在写入或格式不完整时返回 None。"""
        if image_path is None:
            return None
        try:
            content = image_path.read_bytes()
        except (FileNotFoundError, OSError):
            return None
        if not self._is_complete_image(content, image_path.suffix):
            return None
        return content, self._mime_for_suffix(image_path.suffix)

    @staticmethod
    async def _terminate_process_group(
        proc: asyncio.subprocess.Process,
        wait_task: asyncio.Task[int],
    ) -> None:
        """终止 codex 及其派生进程，避免只杀包装进程后留下原生子进程。"""
        try:
            os.killpg(proc.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass

        try:
            await asyncio.wait_for(asyncio.shield(wait_task), timeout=_PROCESS_TERMINATE_GRACE_SECONDS)
        except asyncio.TimeoutError:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            await wait_task
            return

        # 包装进程可能已经退出，但进程组内仍有原生子进程存活。
        try:
            os.killpg(proc.pid, 0)
        except ProcessLookupError:
            return
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass

    async def _run_codex(self, prompt: str, ref: ReferenceImage | None) -> tuple[bytes, str]:
        """调用 codex exec 出图，返回 (图片字节, MIME)。未登录/网络/无产物时抛对应异常。"""
        codex_path = self.config.codex.codex_path.strip() or "codex"
        model = self.config.codex.model.strip()
        reasoning_effort = self.config.codex.reasoning_effort.strip()
        env = self._build_proxy_env()
        timeout = self.config.codex.timeout_seconds

        args = [
            codex_path,
            "exec",
            "--json",
            "--skip-git-repo-check",
            "--sandbox",
            "workspace-write",
        ]
        if model:
            args += ["-m", model]
        if reasoning_effort:
            args += ["--config", f'model_reasoning_effort="{reasoning_effort}"']

        # 用独立临时目录作为工作根；参考图写入其中并用 -i 附加给 codex。
        # 提示词统一经 stdin 传入，生成与编辑两条路径保持一致。
        with tempfile.TemporaryDirectory(prefix="codex-draw-") as workdir:
            reference_path = ""
            if ref is not None:
                ref_file = Path(workdir) / f"ref_0{ref.suffix}"
                ref_file.write_bytes(ref.content)
                reference_path = str(ref_file)
                args += ["-i", str(ref_file)]

            try:
                proc = await asyncio.create_subprocess_exec(
                    *args,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    stdin=asyncio.subprocess.PIPE,
                    cwd=workdir,
                    env=env,
                    start_new_session=True,
                )
            except FileNotFoundError as exc:
                raise CodexMissingError(str(exc)) from exc

            if proc.stdout is None or proc.stderr is None or proc.stdin is None:
                raise RuntimeError("codex 子进程管道初始化失败")

            stdout_chunks: List[bytes] = []
            loop = asyncio.get_running_loop()
            started_at = last_activity = loop.time()
            progress_source = "进程启动"
            thread_id_future = loop.create_future()

            def consume_event(line: str) -> None:
                nonlocal last_activity, progress_source
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    return
                if not isinstance(event, dict):
                    return
                event_type = event.get("type")
                # stderr、普通文本和错误事件不作为刷新事件流计时的依据。
                if event_type in ("thread.started", "turn.started", "item.started", "item.updated", "item.completed"):
                    last_activity = loop.time()
                    progress_source = f"事件 {event_type}"
                if event_type == "thread.started" and not thread_id_future.done():
                    discovered_thread_id = self._extract_thread_id(line)
                    if discovered_thread_id:
                        thread_id_future.set_result(discovered_thread_id)

            async def read_stdout() -> None:
                pending_text = ""
                while chunk := await proc.stdout.read(65536):
                    stdout_chunks.append(chunk)
                    pending_text += chunk.decode("utf-8", errors="ignore")
                    lines = pending_text.split("\n")
                    pending_text = lines.pop()
                    for line in lines:
                        consume_event(line)

                    # 限制异常非 JSON 输出造成的缓存增长。
                    if len(pending_text) > 65536:
                        pending_text = pending_text[-65536:]

                if pending_text:
                    consume_event(pending_text)

            stdout_task = asyncio.create_task(read_stdout())
            stderr_task = asyncio.create_task(proc.stderr.read())
            wait_task = asyncio.create_task(proc.wait())

            try:
                proc.stdin.write(self._build_codex_prompt(prompt, reference_path).encode("utf-8"))
                await proc.stdin.drain()
                proc.stdin.close()

                next_wait_log = started_at + timeout
                next_progress_poll = started_at
                session_path: Path | None = None
                session_state: Tuple[int, int] | None = None
                thread_id = ""
                image_result: tuple[bytes, str] | None = None
                last_image_state: tuple[Path, int, int] | None = None
                stable_checks = 0
                stop_reason = ""

                while True:
                    if not thread_id and thread_id_future.done():
                        thread_id = thread_id_future.result()

                    # 工具的 wait 返回不一定出现在 exec JSON 流中；同时轮询本次
                    # 会话的落盘记录，只读取文件状态，不扫描内容或其他会话的活动。
                    now = loop.time()
                    if thread_id and (now >= next_progress_poll or now - last_activity >= timeout):
                        if session_path is None:
                            session_path = self._find_codex_session(thread_id)
                        if session_path is not None:
                            try:
                                session_stat = session_path.stat()
                            except FileNotFoundError:
                                session_path = None
                            else:
                                current_state = (session_stat.st_size, session_stat.st_mtime_ns)
                                if current_state != session_state:
                                    session_state = current_state
                                    last_activity = now
                                    progress_source = "会话记录更新"
                        next_progress_poll = now + _PROGRESS_POLL_INTERVAL_SECONDS

                    if thread_id:
                        image_path = self._latest_image_in_dir(self._codex_gen_dir() / thread_id)
                        if image_path is not None:
                            try:
                                image_stat = image_path.stat()
                            except FileNotFoundError:
                                last_image_state = None
                                stable_checks = 0
                            else:
                                image_state = (image_path, image_stat.st_size, image_stat.st_mtime_ns)
                                if image_state == last_image_state:
                                    stable_checks += 1
                                else:
                                    last_image_state = image_state
                                    stable_checks = 1
                                    last_activity = loop.time()
                                    progress_source = "图片文件写入"
                                if stable_checks >= _IMAGE_STABLE_CHECKS:
                                    image_result = self._read_complete_image(image_path)
                                    if image_result is not None:
                                        stop_reason = "image_ready"
                                        break

                    # 子进程可能仍占用输出管道；主进程退出后应立即清理进程组。
                    if proc.returncode is not None:
                        stop_reason = "process_exited"
                        break

                    now = loop.time()
                    hard_remaining = started_at + _MAX_JOB_DURATION_SECONDS - now
                    if hard_remaining <= 0:
                        stop_reason = "hard_timeout"
                        break
                    remaining = last_activity + timeout - now
                    if remaining <= 0:
                        stop_reason = "timeout"
                        break
                    if now >= next_wait_log:
                        self.ctx.logger.info(
                            "codex 出图继续轮询等待：会话=%s，累计=%.1f 秒，无活动=%.1f 秒，最近活动=%s",
                            thread_id or "尚未返回",
                            now - started_at,
                            now - last_activity,
                            progress_source,
                        )
                        next_wait_log = now + timeout
                    await asyncio.sleep(min(_IMAGE_POLL_INTERVAL_SECONDS, remaining, hard_remaining))

                self.ctx.logger.info(
                    "codex 出图等待结束：会话=%s，原因=%s，累计=%.1f 秒，无活动=%.1f 秒，最近活动=%s",
                    thread_id or "尚未返回",
                    {
                        "image_ready": "图片就绪",
                        "process_exited": "进程退出",
                        "timeout": "无活动超时",
                        "hard_timeout": "总时长超限",
                    }[stop_reason],
                    loop.time() - started_at,
                    loop.time() - last_activity,
                    progress_source,
                )
                # 主进程正常或异常退出时，同样回收进程组内残留的子进程。
                await self._terminate_process_group(proc, wait_task)

                await stdout_task
                stderr_bytes = await stderr_task
            except BaseException:
                await asyncio.shield(self._terminate_process_group(proc, wait_task))
                await asyncio.gather(stdout_task, stderr_task, return_exceptions=True)
                raise

        stdout_bytes = b"".join(stdout_chunks)
        stdout_text = stdout_bytes.decode("utf-8", errors="ignore")
        stderr_text = stderr_bytes.decode("utf-8", errors="ignore").strip()

        thread_id = thread_id or self._extract_thread_id(stdout_text)
        if image_result is None and thread_id:
            image_path = self._latest_image_in_dir(self._codex_gen_dir() / thread_id)
            image_result = self._read_complete_image(image_path)
        if image_result is not None:
            return image_result

        if stop_reason == "hard_timeout":
            raise asyncio.TimeoutError(
                f"codex 出图达到总时长上限 {_MAX_JOB_DURATION_SECONDS / 60:g} 分钟，已终止进程组；"
                f"最近活动：{progress_source}；会话：{thread_id or '尚未返回'}"
            )
        if stop_reason == "timeout":
            raise asyncio.TimeoutError(
                f"codex 连续 {timeout} 秒无活动，累计等待 {loop.time() - started_at:.1f} 秒；"
                f"最近活动：{progress_source}；会话：{thread_id or '尚未返回'}"
            )
        if proc.returncode != 0:
            self._raise_for_codex_error(proc.returncode or -1, stderr_text or stdout_text)
        if not thread_id:
            raise CodexOutputError("codex 已运行但未返回会话 ID，无法定位产物图片")
        raise CodexOutputError("codex 运行完成，但该会话未产出完整图片")

    @staticmethod
    def _find_codex_session(thread_id: str) -> Path | None:
        """按本次会话 ID 定位记录；路径找到后由调用方缓存，兼容跨日任务。"""
        if not re.fullmatch(r"[A-Za-z0-9-]+", thread_id):
            return None
        codex_home = Path(os.environ.get("CODEX_HOME", "~/.codex")).expanduser()
        return next((codex_home / "sessions").glob(f"*/*/*/rollout-*-{thread_id}.jsonl"), None)

    @staticmethod
    def _raise_for_codex_error(returncode: int, detail: str) -> None:
        """按退出码/报错内容分类抛出可读异常（不吞掉原始信息）。"""
        lowered = detail.lower()
        if "not logged in" in lowered or "auth" in lowered or "login" in lowered or "unauthorized" in lowered:
            raise CodexLoginError(detail or "codex 未登录")
        if any(
            token in lowered
            for token in ("proxy", "network", "connection", "refused", "unreachable", "timeout", "dns")
        ):
            raise CodexNetworkError(detail or "codex 出图网络/代理异常")
        raise RuntimeError(f"codex 出图失败（退出码 {returncode}）：{detail or '无输出'}")

    @staticmethod
    def _extract_thread_id(stdout_text: str) -> str:
        """从 --json 的 JSONL 事件流里提取 thread_id（取最后一个 thread.started）。"""
        thread_id = ""
        for line in stdout_text.splitlines():
            line = line.strip()
            if not line.startswith("{"):
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if event.get("type") == "thread.started":
                thread_id = str(event.get("thread_id") or "").strip()
        return thread_id

    def _latest_image_in_dir(self, directory: Path) -> Path | None:
        """取目录内最新的图片文件（按 mtime）。"""
        if not directory.is_dir():
            return None
        candidates = [p for p in directory.iterdir() if p.is_file() and p.suffix.lower() in _IMAGE_SUFFIXES]
        if not candidates:
            return None
        return max(candidates, key=lambda p: p.stat().st_mtime)

    @staticmethod
    def _mime_for_suffix(suffix: str) -> str:
        return {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".webp": "image/webp",
        }.get(suffix.lower(), "image/png")

    # ------------------------------------------------------------------ #
    # 后台任务编排
    # ------------------------------------------------------------------ #

    async def _send_text(self, stream_id: str, text: str) -> None:
        if not stream_id:
            return
        try:
            await self.ctx.send.text(text=text, stream_id=stream_id)
        except Exception as exc:
            self.ctx.logger.error("codex-draw 回传文本失败: %s", exc, exc_info=True)

    async def _run_draw_job(self, stream_id: str, prompt: str, ref: ReferenceImage | None) -> None:
        """执行单个出图任务：合规审查 → codex 出图 → 回传图片/提示。"""
        task_label = "编辑" if ref is not None else "生成"
        try:
            await self._compliance_check(prompt, ref)
            await self._send_text(stream_id, "GPT-image2绘制中")
            content, mime_type = await self._run_codex(prompt, ref)
            encoded = base64.b64encode(content).decode("utf-8")
            send_result = await self.ctx.send.image(encoded, stream_id)
            if not send_result:
                # A timeout can mean delivered without an acknowledgement: never retry blindly.
                self.ctx.logger.error("codex %s完成但图片发送失败或回执不明: %s", task_label, stream_id)
                await self._send_text(stream_id, "图片已经画好，但发送失败或回执超时，请先查看群里是否收到。图片仍保存在服务器上。")
        except ComplianceRejected:
            # 合规拒绝属于预期结果，静默终止任务，不向聊天发送任何消息。
            return
        except CodexMissingError:
            await self._send_text(stream_id, "未找到 codex 命令，请先安装 codex CLI。")
        except CodexLoginError:
            await self._send_text(stream_id, "codex 未登录，请先在终端执行 `codex login` 完成登录。")
        except CodexNetworkError as exc:
            await self._send_text(stream_id, f"codex 出图失败（网络/代理）：{exc}")
        except asyncio.TimeoutError as exc:
            await self._send_text(stream_id, f"出图超时，请稍后再试 ⏳（{exc}）")
        except Exception as exc:
            # 边界处转为用户可读消息，同时完整记录堆栈，不掩盖根因
            self.ctx.logger.error("codex %s失败: %s", task_label, exc, exc_info=True)
            await self._send_text(stream_id, f"出图失败：{exc}")

    def _job_dir(self):
        directory = self._codex_gen_dir().parent / "draw_jobs"
        directory.mkdir(parents=True, exist_ok=True)
        return directory

    def _save_job(self, record):
        record["updated"] = time.time()
        path = self._job_dir() / (record["id"] + ".json")
        pending = path.with_suffix(".pending")
        pending.write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")
        pending.chmod(0o600)
        pending.replace(path)

    async def _recover_jobs(self):
        # Wait for the QQ adapter to connect before resuming persisted work.
        await asyncio.sleep(15)
        for path in sorted(self._job_dir().glob("*.json")):
            try:
                record = json.loads(path.read_text(encoding="utf-8"))
                if record["state"] not in ("queued", "generating", "ready"):
                    if record["state"] == "sending":
                        record["state"] = "delivery_unknown"
                        self._save_job(record)
                    continue
                if record.get("recovery", 0) >= 1:
                    record["state"] = "interrupted"
                    self._save_job(record)
                    continue
                record["recovery"] = record.get("recovery", 0) + 1
                self._save_job(record)
                await self._run_durable_job(record)
            except asyncio.CancelledError:
                raise
            except Exception:
                self.ctx.logger.exception("绘图任务恢复失败: %s", path.name)

    async def _run_durable_job(self, record):
        stream_id = record["stream_id"]
        try:
            image_path = self._job_dir() / (record["id"] + ".image")
            if not image_path.exists():
                ref_data = record.get("ref")
                ref = ReferenceImage(base64.b64decode(ref_data["data"]), ref_data["suffix"], ref_data["mime_type"]) if ref_data else None
                record["state"] = "generating"
                self._save_job(record)
                await self._compliance_check(record["prompt"], ref)
                await self._send_text(stream_id, "开始画啦，画好会发到这里。")
                content, mime_type = await self._run_codex(record["prompt"], ref)
                pending = image_path.with_suffix(".pending-image")
                pending.write_bytes(content)
                pending.replace(image_path)
                record["mime_type"] = mime_type
            record["state"] = "ready"
            self._save_job(record)
            encoded = base64.b64encode(image_path.read_bytes()).decode()
            record["state"] = "sending"
            self._save_job(record)
            try:
                delivered = await self.ctx.send.image(encoded, stream_id)
            except Exception as exc:
                delivered = False
                record["error"] = str(exc)[:300]
            record["state"] = "sent" if delivered else "delivery_unknown"
            self._save_job(record)
            self.ctx.logger.info("绘图交付任务 %s state=%s", record["id"], record["state"])
            if not delivered:
                await self._send_text(stream_id, "图已经画好，但QQ发送回执不明。先看看群里是否收到；原图已保存，可以要求重发，不必重新画。")
        except asyncio.CancelledError:
            # Leave the last checkpoint for startup recovery.
            raise
        except ComplianceRejected:
            record["state"] = "rejected"
            self._save_job(record)
        except Exception as exc:
            record["state"] = "failed"
            record["error"] = str(exc)[:300]
            self._save_job(record)
            await self._send_text(stream_id, "这次绘图失败了，任务记录已保留，可以再试一次。")
            self.ctx.logger.exception("绘图任务失败 %s", record["id"])

    @Tool("draw_status", description="查询当前聊天最新绘图任务的真实状态。用户问进度、画完了吗或是否卡住时必须先查，不要猜测。", parameters=[], visibility="visible")
    async def draw_status(self, **kwargs):
        stream_id = str(kwargs.get("stream_id") or "")
        if not stream_id:
            return {"success": False, "content": "缺少当前聊天，无法查询。"}
        records = [json.loads(p.read_text(encoding="utf-8")) for p in self._job_dir().glob("*.json")]
        records = [r for r in records if r["stream_id"] == stream_id]
        if not records:
            return {"success": True, "content": "没有持久化绘图任务记录，不能声称正在绘图。"}
        latest = max(records, key=lambda r: r["updated"])
        return {"success": True, "content": json.dumps({k: latest.get(k) for k in ("id", "state", "updated", "error")}, ensure_ascii=False)}

    @Tool("draw_resend", description="用户明确要求重发最新绘图时使用；先确认群里未收到，避免重复。不重新生成图片。", parameters=[], visibility="visible")
    async def draw_resend(self, **kwargs):
        stream_id = str(kwargs.get("stream_id") or "")
        if not stream_id:
            return {"success": False, "content": "缺少当前聊天。"}
        records = [json.loads(p.read_text(encoding="utf-8")) for p in self._job_dir().glob("*.json")]
        records = [r for r in records if r["stream_id"] == stream_id]
        if not records:
            return {"success": False, "content": "没有可重发任务。"}
        record = max(records, key=lambda r: r["updated"])
        if record["state"] not in ("sent", "delivery_unknown", "ready"):
            return {"success": False, "content": "最新任务尚无可发送成品，请先查询状态。"}
        await self._run_durable_job(record)
        return {"success": record["state"] == "sent", "content": record["state"]}

    def _spawn_draw_job(self, stream_id: str, prompt: str, ref: ReferenceImage | None) -> bool:
        """在无等待队列的前提下尝试启动出图任务。

        返回 True 表示已受理；当正在执行的任务已达 WebUI 配置的上限时，
        返回 False 并静默忽略请求。本方法在事件循环内不产生 await，因此“检查 +
        登记任务”之间不会被其他协程插入。
        """
        if len(self._background_tasks) >= self.config.codex.max_concurrent_jobs:
            return False

        job_id = uuid.uuid4().hex
        record = dict(id=job_id, stream_id=stream_id, prompt=prompt, state="queued", updated=time.time(), recovery=0)
        if ref is not None:
            record["ref"] = dict(data=base64.b64encode(ref.content).decode(), suffix=ref.suffix, mime_type=ref.mime_type)
        self._save_job(record)
        task = asyncio.create_task(self._run_durable_job(record))
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)
        return True

    # ------------------------------------------------------------------ #
    # 对外入口
    # ------------------------------------------------------------------ #

    def _build_command_help(self) -> str:
        return (
            "Codex 绘图用法：\n"
            "· /gpt <提示词>：生成一张图片\n"
            "· 回复一条含图片的消息，再发 /gpt <提示词>：基于该图做图片编辑\n"
            "· 或在同一条消息里发送「图片 + /gpt <提示词>」：基于该图做图片编辑\n"
            "· /gpt 审查 <提示词>：只触发合规审查并回复审查结果（不出图；回复含图消息可连同参考图一起审查）"
        )

    @staticmethod
    def _split_command_payload(payload: str) -> tuple[str, str]:
        """把 /gpt 后的载荷拆成 (模式, 文本)：
        - 首词命中审查子命令 → ("review", 去掉首词的文本)
        - 否则整体视为绘图提示词 → ("draw", 原始文本)
        """
        if not payload:
            return "draw", ""
        first, _, rest = payload.partition(" ")
        if first.lower() in _REVIEW_SUBCOMMANDS:
            return "review", rest.strip()
        return "draw", payload

    @Command(
        "gpt",
        description=(
            "用 codex 生成或编辑图片：/gpt <提示词>；回复含图消息后发送则触发编辑；"
            "/gpt 审查 <提示词> 仅做合规审查并回复结果"
        ),
        pattern=_GPT_COMMAND_PATTERN,
    )
    async def handle_gpt(self, stream_id: str = "", **kwargs: Any) -> tuple[bool, str, int]:
        """手动 /gpt 命令入口。"""
        if not stream_id:
            return False, "当前聊天流不可用，无法执行 /gpt", 1

        matched_groups = kwargs.get("matched_groups", {})
        payload = str((matched_groups or {}).get("prompt") or "").strip()
        if not payload:
            await self._send_text(stream_id, self._build_command_help())
            return True, "已显示 /gpt 用法", 2

        mode, text = self._split_command_payload(payload)

        # 仅审查子命令：不绘图，另起上下文跑合规审查并直接回复裁决
        if mode == "review":
            if not text:
                await self._send_text(stream_id, "请提供要审查的提示词，例如：/gpt 审查 <提示词>")
                return True, "已提示 /gpt 审查用法", 2
            try:
                ref = await self._load_reference_image(kwargs.get("message"), stream_id)
                allowed = await self._review_prompt(text, ref)
            except Exception as exc:
                self.ctx.logger.error("codex-draw 合规审查失败: %s", exc, exc_info=True)
                # 审查调用异常属系统错误（非「拒绝」），同样不向聊天暴露内部细节
                await self._send_text(stream_id, "合规审查失败，请稍后再试")
                return False, "合规审查失败", 1
            # 仅回通过/不通过，不返回理由
            await self._send_text(stream_id, "✅ 通过合规审查" if allowed else "❌ 未通过合规审查")
            return True, "已完成合规审查", 2

        # A missing/corrupt image must not silently turn an edit into text-only generation.
        try:
            ref = await self._load_reference_image(kwargs.get("message"), stream_id)
        except ValueError as exc:
            await self._send_text(stream_id, str(exc))
            return False, str(exc), 1
        if not self._spawn_draw_job(stream_id, text, ref):
            return True, "Codex 出图并发已满，已静默忽略", 2
        # 审查通过后由后台任务回复绘制中；审查拒绝时静默终止。
        return True, "已提交 Codex 出图任务", 2

    @Tool(
        "gpt_draw",
        description=(
            "用GPT生成新图或基于群友原图修改图片，完成后直接发回当前聊天。"
            "修改这张图、换背景、加文字等请求必须edit=true，reference_message_id填写当前上下文"
            "真正含原图消息的msg_id；若请求引用另一条含图消息，应选那条原图消息。"
            "可使用先发图后用自然语言提出的修改需求，不需要用户输入/gpt指令。"
            "有多张图时根据用户指向选择image_index；不明确则先问，不要猜。"
            "只有明确画新图时才不传参考图。取不到原图不能用图片描述代替，也不要声称已经编辑。"
            "任务在后台执行，受理后等待插件回图，不重复提交。"
            "提示词会在出图前先经过合规审查，不合规则被拒绝。"
        ),
        parameters=[
            ToolParameterInfo(
                name="prompt",
                param_type=ToolParamType.STRING,
                description="用户希望生成的图片内容的自然语言提示词。",
                required=True,
            ),
            ToolParameterInfo(
                name="reference_message_id", param_type=ToolParamType.STRING,
                description="当前聊天中含用户指定原图的消息msg_id，修改图片时必须填写；纯生成留空。",
                required=False,
            ),
            ToolParameterInfo(
                name="image_index", param_type=ToolParamType.INTEGER,
                description="原图在该消息图片中的序号，从0开始；默认0。",
                required=False,
            ),
            ToolParameterInfo(
                name="edit", param_type=ToolParamType.BOOLEAN,
                description="基于原图修改时为true；仅画新图为false。",
                required=False,
            ),
        ],
        visibility="visible",
    )
    async def handle_gpt_draw(
        self, prompt: str, reference_message_id: str = "", image_index: int = 0,
        edit: bool = False, **kwargs: Any,
    ) -> dict[str, Any]:
        """LLM 工具入口：提交后台生成任务。"""
        normalized_prompt = (prompt or "").strip()
        if not normalized_prompt:
            return {"success": False, "message": "prompt 不能为空"}

        stream_id = self._extract_tool_stream_id(kwargs)
        if not stream_id:
            return {"success": False, "message": "当前工具执行上下文缺少 stream_id/session_id，无法回传图片"}

        reference_message_id = str(reference_message_id or "").strip()
        if edit and not reference_message_id:
            return {"success": False, "message": "修改图片需要reference_message_id。请从上下文选出含原图的msg_id；无法确定时请用户引用或重发原图，不要转成纯生成。"}
        ref = None
        if reference_message_id:
            try:
                ref = await self._load_reference_image(
                    {"message_id": reference_message_id}, stream_id,
                    image_index=image_index, required=True,
                )
            except (ValueError, RuntimeError) as exc:
                return {"success": False, "message": str(exc)}
        if not self._spawn_draw_job(stream_id, normalized_prompt, ref=ref):
            return {
                "success": False,
                "message": "Codex 出图并发已满，请静默结束，不要向聊天流发送提示。",
            }
        return {
            "success": True,
            "mode": "edit" if ref is not None else "generate",
            "reference_message_id": reference_message_id,
            "image_index": image_index if ref is not None else None,
            "message": "插件已受理出图任务；后台完成后会把图片发送到当前聊天流。",
        }

    @staticmethod
    def _extract_tool_stream_id(kwargs: dict[str, Any]) -> str:
        """从工具执行上下文中提取 stream_id（宿主会注入多种来源）。"""
        context_sources = [
            kwargs.get("tool_execution_context"),
            kwargs.get("execution_context"),
            kwargs.get("tool_context"),
            kwargs.get("context"),
        ]

        def read(field_name: str) -> str:
            direct = str(kwargs.get(field_name) or "").strip()
            if direct:
                return direct
            for source in context_sources:
                if isinstance(source, dict):
                    value = str(source.get(field_name) or "").strip()
                    if value:
                        return value
                value = str(getattr(source, field_name, "") or "").strip()
                if value:
                    return value
            return ""

        return read("stream_id") or read("session_id")


def create_plugin() -> CodexDrawPlugin:
    """插件工厂函数（Runner 入口）。"""
    return CodexDrawPlugin()
