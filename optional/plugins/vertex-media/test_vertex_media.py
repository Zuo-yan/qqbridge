"""Offline tests: all test files and databases stay below this directory."""
from abc import ABC, abstractmethod
import asyncio
import base64
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import importlib.util
import inspect
import io
import json
from pathlib import Path
import sys
import tempfile
import time
from types import SimpleNamespace as NS, ModuleType
import unittest
from unittest.mock import AsyncMock, patch
import wave

from PIL import Image
from vertex_media_core import (BJT, GenerationError, Ledger, MediaError, MediaService,
                               beijing_day, explicit_request, wav_audio)
from vertex_media_client import VertexBackend, provider_settings

ROOT = Path(__file__).resolve().parent


def png():
    out = io.BytesIO()
    Image.new("RGB", (1024, 1024), "blue").save(out, "PNG")
    return out.getvalue()


def pcm(seconds=1):
    return b"\x00\x00" * int(24000 * seconds)


class Sandbox:
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=tempfile.gettempdir(), prefix="test-data-")
        self.addCleanup(self.temp.cleanup)
        self.now = [datetime(2026, 11, 4, 23, 59, 59, tzinfo=BJT).timestamp()]
        self.ledger = Ledger(self.temp.name, clock=lambda: self.now[0])


class LedgerTests(Sandbox, unittest.TestCase):
    def test_concurrent_cross_group_and_private_share_five(self):
        def reserve(i):
            ledger = Ledger(self.temp.name, clock=lambda: self.now[0])
            try:
                return ledger.reserve(f"group-{i}" if i % 2 else f"private-{i}", str(i), "image")[1]
            except MediaError:
                return False
        with ThreadPoolExecutor(max_workers=12) as pool:
            self.assertEqual(sum(pool.map(reserve, range(30))), 10)
        self.assertEqual(self.ledger.quota()["image"]["reserved"], 10)

    def test_atomic_duplicate_reservation(self):
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(lambda _: self.ledger.reserve("g", "same", "audio")[1], range(20)))
        self.assertEqual(sum(results), 1)

    def test_midnight_reset_late_success_uses_reservation_day(self):
        job, _ = self.ledger.reserve("g", "old", "image")
        self.ledger.start_attempt(job["id"])
        self.now[0] += 2
        self.assertEqual(self.ledger.quota()["day"], "2026-11-05")
        self.ledger.finish(job["id"], "ready", asset="old.png")
        self.assertEqual(self.ledger.quota()["image"]["used"], 0)
        self.ledger.reserve("newgroup", "new", "image")
        self.assertEqual(self.ledger.quota()["image"]["reserved"], 1)

    def test_attempt_cap_and_failure_release(self):
        for i in range(20):
            job, _ = self.ledger.reserve("g", str(i), "image")
            self.ledger.start_attempt(job["id"])
            self.ledger.finish(job["id"], "failed")
        q = self.ledger.quota()["image"]
        self.assertEqual((q["used"], q["reserved"], q["attempts"]), (0, 0, 20))
        with self.assertRaises(MediaError):
            self.ledger.reserve("other-group", "21", "image")

    def test_restart_preserves_uncertain_and_attempts(self):
        job, _ = self.ledger.reserve("g", "m", "audio")
        self.ledger.start_attempt(job["id"])
        self.ledger.finish(job["id"], "uncertain")
        reopened = Ledger(self.temp.name, clock=lambda: self.now[0])
        self.assertEqual(reopened.quota()["audio"]["reserved"], 1)
        self.assertEqual(reopened.quota()["audio"]["attempts"], 1)
        self.assertFalse(reopened.reserve("g", "m", "audio")[1])

    def test_seed_idempotent_and_shared(self):
        day = beijing_day(self.now[0])
        self.assertTrue(self.ledger.seed_usage("probe-image", day, "image", 1, 1))
        self.assertFalse(self.ledger.seed_usage("probe-image", day, "image", 1, 1))
        self.ledger.seed_usage("probe-audio", day, "audio", 2, 2)
        self.assertEqual(self.ledger.quota()["image"]["used"], 1)
        self.assertEqual(self.ledger.quota()["audio"]["attempts"], 2)
        with self.assertRaises(MediaError):
            self.ledger.seed_usage("probe-image", day, "image", 2, 2)
        with self.assertRaises(MediaError):
            self.ledger.seed_usage("too-many", day, "image", 10, 10)

    def test_video_disabled_including_internal_api(self):
        with self.assertRaises(MediaError):
            self.ledger.reserve("g", "m", "video")
        self.assertEqual(self.ledger.quota()["video"]["limit"], 2)
        self.assertFalse(self.ledger.quota()["video"]["enabled"])


class AudioAndIntentTests(unittest.TestCase):
    def test_actual_duration_60_boundary_and_overlong(self):
        data, duration = wav_audio(pcm(60), "audio/l16;rate=24000;channels=1")
        self.assertEqual(duration, 60)
        self.assertTrue(data.startswith(b"RIFF"))
        with self.assertRaises(MediaError):
            wav_audio(pcm(60.01), "audio/l16;rate=24000;channels=1")

    def test_wav_header_and_truncation(self):
        data, _ = wav_audio(pcm(2), "audio/l16;rate=24000;channels=1")
        self.assertEqual(wav_audio(data, "audio/wav")[1], 2)
        with self.assertRaises(MediaError):
            wav_audio(data[:-10], "audio/wav")
        for bad in [b"", b"123"]:
            with self.assertRaises(MediaError):
                wav_audio(bad, "audio/l16;rate=24000;channels=1")
        with self.assertRaises(MediaError):
            wav_audio(b"mp3?", "audio/mpeg")

    def test_explicit_requests_only(self):
        for text in ["帮我画一只鲸鱼", "生成一张图片", "把这张图改成蓝色", "将背景换成海边"]:
            self.assertTrue(explicit_request(text, "image", "generate"), text)
        for text in ["你好", "画质很好", "你会画图吗？", "不要生成图片", "如何生成图片？", "举例：帮我画一只猫"]:
            self.assertFalse(explicit_request(text, "image", "generate"), text)
        self.assertTrue(explicit_request("用语音回复我", "audio", "generate"))
        self.assertTrue(explicit_request("朗读这段话", "audio", "generate"))
        self.assertFalse(explicit_request("不要发语音", "audio", "generate"))
        self.assertFalse(explicit_request("你好", "image", "resend"))
        self.assertTrue(explicit_request("重发刚才的图片", "image", "resend"))


class ServiceTests(Sandbox, unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.backend = NS(generate=AsyncMock(return_value=(pcm(), "audio/l16;rate=24000;channels=1")))
        self.sender = AsyncMock(return_value=True)
        self.service = MediaService(self.ledger, self.backend, self.sender)

    async def test_start_ack_after_quota_before_generation_once_no_repeat_on_resend(self):
        events = []
        async def notice(kind, session, event):
            self.assertEqual(self.ledger.quota()[kind]['reserved'], 1)
            events.append(event)
        async def generate(*args, **kwargs):
            self.assertEqual(events, ['start'])
            return pcm(), 'audio/l16'
        self.backend.generate.side_effect = generate
        self.service.notifier = notice
        await self.service.run('audio', 'g', 'm', '你好')
        await self.service.run('audio', 'g', 'm', '重复')
        await self.service.run('audio', 'g', 'retry', '', operation='resend')
        self.assertEqual(events, ['start'])
        self.backend.generate.assert_awaited_once()

    async def test_no_start_ack_when_quota_exhausted(self):
        notice = AsyncMock()
        self.service.notifier = notice
        self.ledger.seed_usage('full-day', beijing_day(self.now[0]), 'audio', 20, 20)
        with self.assertRaises(MediaError):
            await self.service.run('audio', 'g', 'm', '你好')
        notice.assert_not_awaited()
        self.backend.generate.assert_not_awaited()

    async def test_send_failure_resend_no_generation_or_charge(self):
        self.sender.return_value = False
        result = await self.service.run("audio", "g", "m", "你好")
        self.assertTrue(result["generated"])
        self.assertFalse(result["success"])
        self.assertEqual(self.ledger.quota()["audio"]["used"], 1)
        self.sender.return_value = True
        recovered = MediaService(Ledger(self.temp.name, clock=lambda: self.now[0]), self.backend, self.sender)
        self.assertTrue((await recovered.run("audio", "g", "new", "", operation="resend"))["success"])
        self.assertEqual(self.backend.generate.await_count, 1)
        self.assertEqual(self.ledger.quota()["audio"]["attempts"], 1)

    async def test_retry_once_then_success(self):
        self.backend.generate.side_effect = [GenerationError("暂时失败", retryable=True), (pcm(), "audio/l16;rate=24000;channels=1")]
        self.assertTrue((await self.service.run("audio", "g", "m", "你好"))["success"])
        self.assertEqual(self.backend.generate.await_count, 2)
        self.assertEqual(self.ledger.quota()["audio"]["used"], 1)
        self.assertEqual(self.ledger.quota()["audio"]["attempts"], 2)

    async def test_retry_never_exceeds_two(self):
        self.backend.generate.side_effect = GenerationError("暂时失败", retryable=True)
        with self.assertRaises(GenerationError):
            await self.service.run("audio", "g", "m", "你好")
        self.assertEqual(self.backend.generate.await_count, 2)
        self.assertEqual(self.ledger.quota()["audio"]["reserved"], 0)

    async def test_stable_error_no_retry_or_success_charge(self):
        self.backend.generate.side_effect = GenerationError("配置或权限错误")
        with self.assertRaises(GenerationError):
            await self.service.run("audio", "g", "m", "你好")
        self.assertEqual(self.backend.generate.await_count, 1)
        self.assertEqual(self.ledger.quota()["audio"]["used"], 0)

    async def test_timeout_no_retry_including_restart_same_message(self):
        self.backend.generate.side_effect = GenerationError("超时", uncertain=True)
        with self.assertRaises(GenerationError):
            await self.service.run("audio", "g", "m", "你好")
        recovered = MediaService(self.ledger, self.backend, self.sender)
        await recovered.run("audio", "g", "m", "模型改写了参数")
        self.assertEqual(self.backend.generate.await_count, 1)
        self.assertEqual(self.ledger.quota()["audio"]["reserved"], 1)

    async def test_duplicate_prompt_changes_do_not_generate_explicit_new_message_does(self):
        await self.service.run("audio", "g", "m", "你好")
        await self.service.run("audio", "g", "m", "另一种提示词")
        self.assertEqual(self.backend.generate.await_count, 1)
        await self.service.run("audio", "g", "user-new-message", "再来一条")
        self.assertEqual(self.backend.generate.await_count, 2)

    async def test_cannot_resend_to_different_session(self):
        result = await self.service.run("audio", "private-a", "m", "你好")
        with self.assertRaises(MediaError):
            await self.service.run("audio", "group-b", "new", "", operation="resend", job_id=result["job_id"])

    async def test_overlong_audio_rejected_no_send(self):
        self.backend.generate.return_value = (pcm(61), "audio/l16;rate=24000;channels=1")
        with self.assertRaises(MediaError):
            await self.service.run("audio", "g", "m", "短文本也不能代替实际时长校验")
        self.sender.assert_not_awaited()
        self.assertEqual(self.backend.generate.await_count, 1)
        self.assertEqual(self.ledger.quota()["audio"]["reserved"], 0)

    async def test_text_limit_before_attempt(self):
        with self.assertRaises(MediaError):
            await self.service.run("audio", "g", "m", "字" * 301)
        self.backend.generate.assert_not_awaited()

    async def test_crash_after_asset_save_recovers_without_generation(self):
        job, _ = self.ledger.reserve("g", "m", "audio")
        self.ledger.start_attempt(job["id"])
        self.service.asset_path(job).write_bytes(wav_audio(pcm(), "audio/l16")[0])
        result = await self.service.run("audio", "g", "m", "你好")
        self.assertTrue(result["generated"])
        self.backend.generate.assert_not_awaited()
        await self.service.run("audio", "g", "new", "", operation="resend")
        self.sender.assert_awaited_once()
        self.assertEqual(self.ledger.quota()["audio"]["used"], 1)

    async def test_concurrent_same_request_and_network_outside_sqlite_lock(self):
        entered, release = asyncio.Event(), asyncio.Event()
        async def generate(*args, **kwargs):
            entered.set()
            await release.wait()
            return pcm(), "audio/l16"
        self.backend.generate.side_effect = generate
        task = asyncio.create_task(self.service.run("audio", "g", "m", "你好"))
        await entered.wait()
        try:
            duplicate = await self.service.run("audio", "g", "m", "你好")
            self.assertIn("正在生成", duplicate["content"])
            # An independent connection can reserve while the remote request awaits.
            self.ledger.reserve("other", "m2", "audio")
        finally:
            release.set()
            await task
        self.assertEqual(self.backend.generate.await_count, 1)

    async def test_image_single_output_normalized_and_edit_shared_quota(self):
        self.backend.generate.return_value = (png(), "image/png")
        result = await self.service.run("image", "g", "m", "改成蓝色", operation="edit", reference=(png(), "image/png"))
        self.assertTrue(result["success"])
        self.assertEqual(self.ledger.quota()["image"]["used"], 1)
        path = self.sender.call_args.args[1]
        with Image.open(path) as image:
            self.assertLessEqual(max(image.size), 1024)


class ProviderTests(Sandbox, unittest.TestCase):
    def test_primary_read_only_region_derivation_and_no_bearer(self):
        path = Path(self.temp.name) / "model_config.toml"
        text = '[[api_providers]]\nname="PrimaryProvider"\nbase_url="https://asia-aiplatform.googleapis.com/v1beta1/projects/example/locations/asia/publishers/google"\napi_key="fake-test-key"\nauth_type="bearer"\n'
        path.write_text(text)
        base, key = provider_settings(path)
        self.assertEqual(base, "https://aiplatform.googleapis.com/v1beta1/projects/example/locations/global/publishers/google")
        self.assertEqual(key, "fake-test-key")
        self.assertIn("us-central1-aiplatform", provider_settings(path, "us-central1")[0])
        self.assertEqual(path.read_text(), text)

    def test_provider_error_redacted(self):
        path = Path(self.temp.name) / "bad.toml"
        path.write_text('api_key="fake-secret"\nbroken =')
        with self.assertRaises(MediaError) as raised:
            provider_settings(path)
        self.assertNotIn("fake-secret", str(raised.exception))


def load_plugin():
    sdk = ModuleType("maibot_sdk")
    class LifecyclePlugin(ABC):
        @abstractmethod
        async def on_load(self):
            pass

        @abstractmethod
        async def on_unload(self):
            pass

        @abstractmethod
        async def on_config_update(self, scope, config_data, version):
            pass

    sdk.MaiBotPlugin = LifecyclePlugin
    sdk.PluginConfigBase = type("PluginConfigBase", (), {})
    sdk.Field = lambda default=None, default_factory=None, **kw: default_factory() if default_factory else default
    sdk.Tool = lambda *args, **kw: lambda fn: fn
    sdk.Command = lambda *args, **kw: lambda fn: fn
    types = ModuleType("maibot_sdk.types")
    types.ToolParameterInfo = lambda **kw: NS(**kw)
    types.ToolParamType = NS(STRING="string", INTEGER="integer")
    spec = importlib.util.spec_from_file_location("vertex_media_plugin_under_test", ROOT / "plugin.py")
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, {"maibot_sdk": sdk, "maibot_sdk.types": types}):
        spec.loader.exec_module(module)
    return module


class PluginTests(Sandbox, unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.module = load_plugin()
        self.plugin = self.module.VertexMediaPlugin()
        self.plugin.config = NS(plugin=NS(enabled=True))
        self.plugin.service = NS(run=AsyncMock(return_value={"success": True}))
        self.current = {"session_id": "g", "message_id": "real", "timestamp": str(time.time()),
                        "raw_message": [{"type": "text", "data": "你好"}]}
        self.plugin.ctx = NS(message=NS(get_by_time_in_chat=AsyncMock(side_effect=lambda *a, **kw: {"success": True, "messages": [self.current]}),
                                      get_by_id=AsyncMock()),
                             send=NS(image=AsyncMock(return_value={"sent": False}), custom=AsyncMock(return_value={"sent": True}), text=AsyncMock()))

    async def test_direct_command_uses_actual_host_message_not_matched_group_argument(self):
        self.current['raw_message'][0]['data'] = '/画图 一只蓝色鲸鱼'
        self.plugin.ctx.message.get_by_time_in_chat.side_effect = None
        self.plugin.ctx.message.get_by_time_in_chat.return_value = [self.current]
        result = await self.plugin.media_command(stream_id='g', platform='qq', matched_groups={'media_text': 'forged'})
        self.assertTrue(result[0])
        self.plugin.service.run.assert_awaited_once_with('image', 'g', 'real', '一只蓝色鲸鱼', operation='generate', reference=None)

    async def test_direct_command_without_actual_command_does_not_generate(self):
        result = await self.plugin.media_command(stream_id='g', platform='qq', matched_groups={'media_operation': '画图', 'media_text': 'forged'})
        self.assertFalse(result[0])
        self.plugin.service.run.assert_not_awaited()

    async def test_direct_voice_and_quota_share_existing_service(self):
        self.current['raw_message'][0]['data'] = '/语音 本鱼来啦'
        result = await self.plugin.media_command(stream_id='g', platform='qq')
        self.assertTrue(result[0])
        self.plugin.service.run.assert_awaited_once_with('audio', 'g', 'real', '本鱼来啦', operation='generate', reference=None)
        self.plugin.service.run.reset_mock()
        self.current['raw_message'][0]['data'] = '/媒体额度'
        self.plugin.service.run.return_value = {'success': True, 'quota': self.ledger.quota()}
        result = await self.plugin.media_command(stream_id='g', platform='qq')
        self.assertTrue(result[0])
        self.assertIn('图片已用 0/10', self.plugin.ctx.send.text.call_args.args[0])
        self.assertIn('视频暂未启用', self.plugin.ctx.send.text.call_args.args[0])

    async def test_factory_implements_required_async_lifecycle(self):
        plugin = self.module.create_plugin()
        self.assertFalse(inspect.isabstract(type(plugin)))
        for name in ("on_load", "on_unload", "on_config_update"):
            self.assertIn(name, type(plugin).__dict__)
            self.assertTrue(inspect.iscoroutinefunction(getattr(plugin, name)))
        self.assertIsNone(await plugin.on_unload())

    async def test_config_update_rebuilds_service_preserving_ledger_and_inflight(self):
        self.plugin.ledger = self.ledger
        previous = MediaService(self.ledger, NS(), self.plugin._send)
        previous.active.add("in-progress")
        previous.sending.add("sending")
        self.plugin.service = previous
        self.ledger.seed_usage("initial-probe", beijing_day(self.now[0]), "image", 1, 1)
        self.plugin.ctx.logger = NS(info=lambda *args: None)
        # A config reload must not silently change the database root.
        self.plugin.config.media = NS(data_dir="must-not-create", voice="Leda")
        for scope in ("self", "bot", "model"):
            await self.plugin.on_config_update(scope, {}, "0.1.0")
            self.assertIs(self.plugin.service.ledger, self.ledger)
            self.assertIs(self.plugin.service.active, previous.active)
            self.assertIs(self.plugin.service.sending, previous.sending)
            self.assertIs(self.plugin.service.backend.config, self.plugin.config.media)
            self.assertEqual(self.plugin.service.ledger.quota()["image"]["used"], 1)
        self.assertIsNot(self.plugin.service, previous)

    async def test_model_cannot_forge_explicit_request(self):
        result = await self.plugin.vertex_draw(prompt="用户说帮我画猫", stream_id="g", message={"text": "帮我画猫"})
        self.assertFalse(result["success"])
        self.plugin.service.run.assert_not_awaited()

    async def test_host_actual_message_id_used_context_and_filter_verified(self):
        self.current["raw_message"][0]["data"] = "帮我画一只猫"
        result = await self.plugin.vertex_draw(prompt="猫", tool_execution_context={"stream_id": "g"}, request_id="model-forged")
        self.assertTrue(result["success"])
        self.assertEqual(self.plugin.service.run.call_args.args[2], "real")
        self.assertTrue(self.plugin.ctx.message.get_by_time_in_chat.call_args.kwargs["filter_mai"])

    async def test_image_and_voice_send_base64_no_container_path(self):
        path = Path(self.temp.name) / "asset.wav"
        path.write_bytes(wav_audio(pcm(), "audio/l16")[0])
        self.assertTrue(await self.plugin._send("audio", path, "g"))
        call = self.plugin.ctx.send.custom.call_args
        self.assertEqual(call.args[0], "voice")
        self.assertEqual(base64.b64decode(call.args[1]), path.read_bytes())
        image_path = Path(self.temp.name) / 'asset.png'
        image_path.write_bytes(png())
        result = await self.plugin._send("image", image_path, "g")
        self.assertFalse(result['sent'])
        transported = base64.b64decode(self.plugin.ctx.send.image.call_args.args[0])
        with Image.open(io.BytesIO(transported)) as image:
            self.assertEqual(image.format, 'JPEG')
        self.assertEqual(image_path.read_bytes(), png())

    async def test_reference_sdk_envelope_and_cross_session_denied(self):
        data = png()
        self.plugin.ctx.message.get_by_id.return_value = {"success": True, "message": {
            "session_id": "g", "raw_message": [{"type": "image", "binary_data_base64": base64.b64encode(data).decode()}]}}
        self.assertEqual((await self.plugin._reference("g", self.current, "ref", 0))[0], data)
        with self.assertRaises(MediaError):
            await self.plugin._reference("different", self.current, "ref", 0)

    async def test_edit_request_cannot_silently_use_generation(self):
        self.current["raw_message"][0]["data"] = "帮我把这张图片改成蓝色"
        self.assertFalse((await self.plugin.vertex_draw(prompt="蓝色", stream_id="g"))["success"])
        self.plugin.service.run.assert_not_awaited()


class SDKContractTests(unittest.IsolatedAsyncioTestCase):
    async def test_modalities_trailing_slash_style_and_sdk_retries_disabled(self):
        captured = []
        aio = NS(models=NS(generate_content=AsyncMock(return_value=NS(parts=[NS(inline_data=NS(data=pcm(), mime_type="audio/l16"), thought=False)]))), aclose=AsyncMock())
        genai = ModuleType("google.genai")
        genai.Client = lambda **kw: captured.append(kw) or NS(aio=aio, close=lambda: None)
        types = NS(**{name: (lambda **kw: NS(**kw)) for name in ["HttpOptions", "HttpRetryOptions", "GenerateContentConfig", "ImageConfig", "SpeechConfig", "VoiceConfig", "PrebuiltVoiceConfig"]})
        types.Part = NS(from_text=lambda **kw: NS(**kw), from_bytes=lambda **kw: NS(**kw))
        genai.types = types
        google = ModuleType("google")
        google.genai = genai
        httpx = ModuleType("httpx")
        httpx.TimeoutException = type("TimeoutException", (Exception,), {})
        httpx.TransportError = type("TransportError", (Exception,), {})
        # The deployed TTS adapter first tries its alternate HTTP backend.
        # Return no audio to exercise its Google fallback without network calls.
        class EmptyHTTP:
            async def __aenter__(self):
                return self
            async def __aexit__(self, *args):
                pass
            async def post(self, *args, **kwargs):
                return NS(content=b'')
        httpx.AsyncClient = lambda **kwargs: EmptyHTTP()
        config = NS(provider_config="unused", region="global", image_model="image-test", tts_model="tts-test", timeout_seconds=120, voice="Leda", tts_style="年轻清亮")
        backend = VertexBackend(config)
        with patch.dict(sys.modules, {"google": google, "google.genai": genai, "google.genai.types": types, "httpx": httpx}), patch("vertex_media_client.provider_settings", return_value=("https://example.test/publishers/google", "fake-test-key")):
            await backend.generate("audio", "你好")
            self.assertEqual(captured[0]["http_options"].retry_options.attempts, 1)
            self.assertTrue(captured[0]["http_options"].base_url.endswith("/"))
            self.assertEqual(captured[0]["http_options"].api_version, "")
            call = aio.models.generate_content.call_args
            self.assertEqual(call.kwargs["config"].response_modalities, ["AUDIO"])
            self.assertIn("年轻清亮", call.kwargs["contents"][0].text)
            self.assertIn("<transcript>你好</transcript>", call.kwargs["contents"][0].text)
            aio.models.generate_content.return_value.parts[0].inline_data = NS(data=png(), mime_type="image/png")
            await backend.generate("image", "鲸鱼")
            self.assertEqual(aio.models.generate_content.call_args.kwargs["config"].response_modalities, ["TEXT", "IMAGE"])
            self.assertEqual(aio.models.generate_content.call_args.kwargs["config"].image_config.image_size, "1K")


if __name__ == "__main__":
    unittest.main()
