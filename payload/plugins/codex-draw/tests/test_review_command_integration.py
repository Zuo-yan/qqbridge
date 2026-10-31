"""/gpt 审查 子命令集成测试（stub ctx，不依赖真实 LLM / codex / 宿主）。

运行：python tests/test_review_command_integration.py
"""

import asyncio
import sys
from pathlib import Path
from typing import Any
from unittest.mock import patch

from maibot_sdk.capabilities.llm import LLMCapability

import pytest

PLUGIN_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PLUGIN_DIR))

import plugin  # noqa: E402
pytestmark = pytest.mark.asyncio


# 1x1 PNG（用于构造“被回复的图片”）
_TINY_PNG_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJ"
    "AAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


class _Logger:
    def info(self, *a, **k):
        pass

    def error(self, *a, **k):
        pass


class _Send:
    def __init__(self, owner: "_Stub"):
        self._o = owner

    async def text(self, text: str = "", stream_id: str = "", **k):
        self._o.sent.append(text)
        return True

    async def image(self, image_data: str, stream_id: str = "", **k):
        self._o.sent.append(f"[image]{len(image_data)}")
        return True


class _Message:
    async def get_by_id(self, message_id: str, **k):
        # 返回一条含 1x1 PNG 的消息
        return {
            "raw_message": [
                {"type": "image", "data": "", "binary_data_base64": _TINY_PNG_B64}
            ]
        }


class _Stub:
    verdict: str
    sent: list[str]
    llm_calls: list[dict[str, Any]]

    async def call_capability(self, capability: str, **payload: Any):
        # 保留真实 SDK 的参数封装，仅替换 RPC，避免宽松 generate stub 掩盖接口变化。
        assert capability == "llm.generate"
        assert payload["task_name"]
        assert not payload.get("model")
        assert not payload.get("model_name")
        self.llm_calls.append(payload)
        return {"success": True, "response": self.verdict}


def _make_stub(verdict: str) -> Any:
    stub = _Stub()
    stub.verdict = verdict
    stub.sent = []
    stub.llm_calls = []
    stub.logger = _Logger()
    stub.send = _Send(stub)
    stub.message = _Message()
    stub.llm = LLMCapability(stub)
    return stub


def _make_plugin(stub: Any) -> plugin.CodexDrawPlugin:
    p = plugin.create_plugin()
    p.set_plugin_config(
        {
            "plugin": {"enabled": True, "config_version": "1"},
            "codex": {"codex_path": "codex", "proxy_url": "127.0.0.1:7890", "model": "", "timeout_seconds": 180, "generated_dir": ""},
            "compliance": {"enabled": True, "review_model": "vlm", "timeout_ms": 60000},
        }
    )
    p._set_context(stub)
    return p


async def test_review_allowed():
    stub = _make_stub('{"review": "true"}')
    p = _make_plugin(stub)
    ok, label, level = await p.handle_gpt(
        stream_id="s1", matched_groups={"prompt": "审查 一只红色的立方体"}, message=None
    )
    assert ok and level == 2
    assert any("✅ 通过合规审查" in s for s in stub.sent), stub.sent
    assert stub.llm_calls and stub.llm_calls[0]["task_name"] == "vlm"
    assert isinstance(stub.llm_calls[0]["prompt"], str)  # 无参考图 → 纯文本 prompt
    print("ok: review allowed")


async def test_review_rejected():
    stub = _make_stub('{"review": "false"}')
    p = _make_plugin(stub)
    ok, _, _ = await p.handle_gpt(
        stream_id="s1", matched_groups={"prompt": "审查 敏感内容"}, message=None
    )
    assert ok
    assert any("❌ 未通过合规审查" in s for s in stub.sent), stub.sent
    # 拒绝时不返回具体理由
    assert not any("涉黄" in s for s in stub.sent), stub.sent
    print("ok: review rejected")


@pytest.mark.parametrize("configured, expected", [(" custom_vision ", "custom_vision"), ("   ", "vlm")])
async def test_review_task_configuration(configured: str, expected: str):
    stub = _make_stub('{"review": "true"}')
    p = _make_plugin(stub)
    p.config.compliance.review_model = configured

    assert await p._review_prompt("一只红色的立方体", None)
    assert stub.llm_calls[0]["task_name"] == expected
    assert stub.llm_calls[0]["timeout_ms"] == 60000


async def test_review_service_error_blocks_draw():
    stub = _make_stub("")
    p = _make_plugin(stub)
    with patch.object(stub, "call_capability", return_value={"success": False, "error": "模型不可用"}):
        with pytest.raises(RuntimeError, match="合规审查调用失败：模型不可用"):
            await p._compliance_check("一只红色的立方体", None)


async def test_review_no_text():
    stub = _make_stub("")
    p = _make_plugin(stub)
    ok, _, _ = await p.handle_gpt(stream_id="s1", matched_groups={"prompt": "审查"}, message=None)
    assert ok
    assert any("请提供要审查的提示词" in s for s in stub.sent), stub.sent
    assert not stub.llm_calls  # 未触发 LLM
    print("ok: review no-text hint")


async def test_review_with_replied_image():
    stub = _make_stub('{"review": "true"}')
    p = _make_plugin(stub)
    message = {"reply_to": "msg-1"}
    ok, _, _ = await p.handle_gpt(
        stream_id="s1", matched_groups={"prompt": "review 把背景换成蓝色"}, message=message
    )
    assert ok
    assert any("✅ 通过合规审查" in s for s in stub.sent), stub.sent
    # 有参考图 → 多模态消息列表 prompt（含 image_url part）
    prompt_arg = stub.llm_calls[0]["prompt"]
    assert stub.llm_calls[0]["task_name"] == "vlm"
    assert isinstance(prompt_arg, list) and prompt_arg[0]["content"][0]["type"] == "image_url"
    print("ok: review with replied image (multimodal)")


async def test_reference_from_current_message():
    # 当前命令消息自带图（无 reply_to）：回退用 message_id 取图
    stub = _make_stub('{"review": "true"}')
    p = _make_plugin(stub)
    ref = await p._load_reference_image({"message_id": "cur-1"}, "s1")
    assert ref is not None and ref.suffix == ".png"
    # 回复消息优先：有 reply_to 时用它（即便当前消息也带 message_id）
    ref2 = await p._load_reference_image({"reply_to": "r-1", "message_id": "cur-2"}, "s1")
    assert ref2 is not None
    print("ok: reference from current message / reply")


async def test_draw_concurrency_full_is_silent():
    stub = _make_stub('{"review": "true"}')
    p = _make_plugin(stub)

    with patch.object(p, "_spawn_draw_job", return_value=False):
        ok, label, level = await p.handle_gpt(
            stream_id="s1", matched_groups={"prompt": "一只红色的立方体"}, message=None
        )

    assert ok and level == 2
    assert "静默忽略" in label
    assert stub.sent == []
    assert stub.llm_calls == []


if __name__ == "__main__":
    asyncio.run(test_review_allowed())
    asyncio.run(test_review_rejected())
    asyncio.run(test_review_no_text())
    asyncio.run(test_review_with_replied_image())
    asyncio.run(test_reference_from_current_message())
    asyncio.run(test_draw_concurrency_full_is_silent())
    print("\nALL REVIEW-COMMAND INTEGRATION TESTS PASSED")
