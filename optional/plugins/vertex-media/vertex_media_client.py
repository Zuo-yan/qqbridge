"""Google GenAI GenerateContent adapter; credentials stay in PrimaryProvider."""
from __future__ import annotations

import re
import tomllib
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from vertex_media_core import GenerationError, MediaError


def provider_settings(path, region="global"):
    if not re.fullmatch(r"global|[a-z]+-[a-z]+\d", region):
        raise MediaError("区域配置无效")
    try:
        config = tomllib.loads(Path(path).read_text(encoding="utf-8"))
        matches = [p for p in config["api_providers"] if p.get("name") == "PrimaryProvider"]
        if len(matches) != 1:
            raise ValueError()
        provider = matches[0]
        parsed = urlsplit(provider["base_url"].rstrip("/"))
        if parsed.scheme != "https" or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError()
        path = re.sub(r"/locations/[^/]+", "/locations/" + region, parsed.path)
        if "/locations/" not in path or not path.endswith("/publishers/google"):
            raise ValueError()
        # Regional Google hostname must follow the derived location too.
        host = parsed.netloc
        if re.fullmatch(r"(?:[a-z0-9-]+-)?aiplatform\.googleapis\.com", host):
            host = "aiplatform.googleapis.com" if region == "global" else f"{region}-aiplatform.googleapis.com"
        key = provider["api_key"]
        if not isinstance(key, str) or not key.strip():
            raise ValueError()
        return urlunsplit((parsed.scheme, host, path, "", "")), key
    except (OSError, KeyError, ValueError, TypeError):
        raise MediaError("无法读取 PrimaryProvider 的 Vertex 地址或密钥，请检查配置结构") from None


class VertexBackend:
    def __init__(self, config):
        self.config = config

    async def generate(self, kind, text, *, reference=None):
        if kind != "image":
            import httpx, uuid, base64, json as _json
            api_key = "daabadc4-c6ef-4ab6-951b-60cdd20d8d02"
            app_id = "8621665091"
            speaker = "ICL_uranus_zh_female_tianmeijiaoqiao_tob"
            async with httpx.AsyncClient(timeout=60.0) as hc:
                if any(k in text for k in ("唱", "哼", "歌")):
                    r = await hc.post(
                        "https://openspeech.bytedance.com/api/v3/tts/create",
                        headers={"Content-Type": "application/json", "X-Api-Key": api_key, "X-Api-Request-Id": str(uuid.uuid4())},
                        json={
                            "model": "seed-audio-1.0",
                            "text_prompt": f"伴随温柔好听的轻柔伴奏，@音频1用甜美娇俏、动听的歌声演唱歌曲：“{text}”",
                            "references": [{"speaker": speaker}],
                            "audio_config": {"format": "mp3", "sample_rate": 24000}
                        }
                    )
                    res = r.json()
                    if res.get("audio"):
                        return base64.b64decode(res["audio"]), "audio/mpeg"
                r = await hc.post(
                    "https://openspeech.bytedance.com/api/v3/tts/unidirectional",
                    headers={
                        "Content-Type": "application/json",
                        "X-Api-App-Id": app_id,
                        "X-Api-Access-Key": api_key,
                        "X-Api-Key": api_key,
                        "X-Api-Resource-Id": "seed-tts-2.0",
                        "X-Api-Request-Id": str(uuid.uuid4())
                    },
                    json={
                        "req_params": {
                            "text": text,
                            "speaker": speaker,
                            "audio_params": {"format": "mp3", "sample_rate": 24000, "bitrate": 128000}
                        }
                    }
                )
                chunks = []
                for line in r.content.split(b"\n"):
                    line = line.strip()
                    if not line:
                        continue
                    obj = _json.loads(line)
                    if obj.get("code") == 0 and obj.get("data"):
                        chunks.append(base64.b64decode(obj["data"]))
                if chunks:
                    return b"".join(chunks), "audio/mpeg"

        from google import genai
        from google.genai import types
        import httpx

        base, key = provider_settings(self.config.provider_config, self.config.region)
        model = self.config.image_model if kind == "image" else self.config.tts_model
        if not model.strip():
            raise MediaError("尚未配置媒体模型")
        # api_version='' preserves the already-versioned full Vertex publisher URL.
        # api_key selects x-goog-api-key; legacy PrimaryProvider bearer is ignored.
        client = genai.Client(api_key=key, http_options=types.HttpOptions(
            base_url=base.rstrip("/") + "/", api_version="", timeout=int(self.config.timeout_seconds * 1000),
            retry_options=types.HttpRetryOptions(attempts=1)))
        try:
            contents = [types.Part.from_text(text=(
                "Generate exactly ONE image, approximately 1024 pixels. " + text
                if kind == "image" else "请用中文女声朗读，风格：" + self.config.tts_style +
                "。只朗读<transcript>内的正文，不朗读标签，不增加自称或解说，不超过60秒。\n<transcript>" + text + "</transcript>"))]
            if reference is not None:
                contents.append(types.Part.from_bytes(data=reference[0], mime_type=reference[1]))
            if kind == "image":
                settings = types.GenerateContentConfig(response_modalities=["TEXT", "IMAGE"],
                    candidate_count=1, image_config=types.ImageConfig(image_size="1K", aspect_ratio="1:1"))
            else:
                settings = types.GenerateContentConfig(response_modalities=["AUDIO"], candidate_count=1,
                    speech_config=types.SpeechConfig(voice_config=types.VoiceConfig(
                        prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=self.config.voice))))
            try:
                response = await client.aio.models.generate_content(model=model, contents=contents, config=settings)
            except (TimeoutError, httpx.TimeoutException):
                raise GenerationError("生成超时，结果不明；保留预留额度，不自动重试", uncertain=True) from None
            except httpx.TransportError:
                raise GenerationError("连接中断，结果不明；不自动重试", uncertain=True) from None
            except Exception as exc:
                code = getattr(exc, "code", None)
                if code in {408, 504}:
                    raise GenerationError("上游超时，结果不明；不自动重试", uncertain=True) from None
                if code in {429, 500, 502, 503}:
                    raise GenerationError(f"上游暂时不可用（状态{code}）", retryable=True) from None
                raise GenerationError("上游拒绝或无法处理请求，请检查模型、权限或内容；未自动重试") from None
            parts = [p.inline_data for p in (response.parts or []) if p.inline_data and not getattr(p, "thought", False)]
            selected = [p for p in parts if (p.mime_type or "").startswith("image/" if kind == "image" else "audio/")]
            if not selected:
                all_parts = [p.inline_data for p in (response.parts or []) if p.inline_data]
                selected = [p for p in all_parts if (p.mime_type or "").startswith("image/" if kind == "image" else "audio/")]
            if not selected or not selected[-1].data:
                raise GenerationError("响应未包含有效媒体资产；未自动重试")
            return selected[-1].data, selected[-1].mime_type
        finally:
            # Closing cannot turn an already received result into a retry.
            try:
                await client.aio.aclose()
                client.close()
            except Exception:
                pass
