"""codex-draw 插件冒烟测试（不启动宿主，直接验证纯逻辑与配置模型）。"""

from pathlib import Path
from unittest.mock import patch

import json
import os
import re
import sys

PLUGIN_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PLUGIN_DIR))

import plugin  # noqa: E402


def _make_plugin(**overrides):
    p = plugin.create_plugin()
    cfg = {
        "plugin": {"enabled": True, "config_version": "1"},
        "codex": {},
        "compliance": {},
    }
    for section, values in overrides.items():
        cfg[section] = values
    p.set_plugin_config(cfg)
    return p


def test_create_and_defaults():
    p = plugin.create_plugin()
    p.set_plugin_config({})
    assert p.config.plugin.enabled is True
    assert p.config.codex.proxy_url == "127.0.0.1:7890"
    assert p.config.codex.codex_path == "codex"
    assert p.config.codex.model == ""
    assert p.config.codex.reasoning_effort == "medium"
    assert p.config.codex.max_concurrent_jobs == 4
    assert p.config.compliance.enabled is True
    assert p.config.compliance.review_model == "vlm"
    print("ok: create + defaults")


def test_build_config_schema():
    schema = plugin.CodexDrawPlugin.build_config_schema()
    assert isinstance(schema, dict)
    # 代理与审查模型字段都应进入 schema
    text = json.dumps(schema, ensure_ascii=False)
    assert "proxy_url" in text
    assert "max_concurrent_jobs" in text
    assert "reasoning_effort" in text
    assert "review_model" in text
    print("ok: build_config_schema")


def test_normalize_proxy():
    p = plugin.create_plugin()
    p.set_plugin_config({})
    assert p._normalize_proxy("127.0.0.1:7890") == "http://127.0.0.1:7890"
    assert p._normalize_proxy("http://127.0.0.1:7890") == "http://127.0.0.1:7890"
    assert p._normalize_proxy("https://proxy.example:8080") == "https://proxy.example:8080"
    assert p._normalize_proxy("   ") == ""
    print("ok: normalize_proxy")


def test_build_proxy_env():
    p = _make_plugin(codex={"proxy_url": "127.0.0.1:7890"})
    proxy_keys = ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy")
    inherited = {key: "http://inherited.invalid:8080" for key in proxy_keys}
    inherited["CODEX_DRAW_TEST_MARKER"] = "preserved"

    # 配置代理时覆盖继承值；留空（含纯空白）时必须移除继承的代理。
    with patch.dict(os.environ, inherited):
        original_env = os.environ.copy()
        env = p._build_proxy_env()
        assert all(env[key] == "http://127.0.0.1:7890" for key in proxy_keys)
        assert env["CODEX_DRAW_TEST_MARKER"] == "preserved"
        for raw_proxy in ("", "   "):
            p2 = _make_plugin(codex={"proxy_url": raw_proxy})
            env2 = p2._build_proxy_env()
            assert not any(key in env2 for key in proxy_keys)
            assert env2["CODEX_DRAW_TEST_MARKER"] == "preserved"
        assert dict(os.environ) == original_env  # 不修改宿主环境
    print("ok: build_proxy_env")


def test_parse_review_verdict():
    pv = plugin.CodexDrawPlugin._parse_review_verdict
    # 约定格式：只返回 {"review":"true"} 或 {"review":"false"}
    assert pv('{"review": "true"}') is True
    assert pv('{"review": "false"}') is False
    assert pv('{"review": true}') is True
    assert pv('{"review": false}') is False
    assert pv('{"review": "TRUE"}') is True  # 大小写不敏感
    # 无合法 JSON / 缺少 review 字段 / 旧格式 → 失败关闭
    assert pv('我无法确定。') is False
    assert pv('{"allowed": true}') is False
    assert pv('') is False
    print("ok: parse_review_verdict")


def test_review_instruction_uses_narrow_rejection_scope():
    instruction = plugin._REVIEW_INSTRUCTION
    assert "不要仅因出现敏感关键词" in instruction
    assert "只有请求明确且实质性地要求" in instruction
    assert "从上下文无法明确确认违规时应判定通过" in instruction
    assert "政治新闻与讽刺" in instruction


def test_extract_thread_id():
    et = plugin.CodexDrawPlugin._extract_thread_id
    log = "\n".join(
        [
            "Reading additional input from stdin...",
            '{"type": "thread.started", "thread_id": "abc-123"}',
            '{"type": "item.completed", "item": {"id": "x"}}',
            '{"type": "turn.completed", "usage": {}}',
        ]
    )
    assert et(log) == "abc-123"
    assert et("no json here") == ""
    print("ok: extract_thread_id")


def test_detect_image_format():
    d = plugin.CodexDrawPlugin._detect_image_format
    assert d(b"\x89PNG\r\n\x1a\nrest") == (".png", "image/png")
    assert d(b"\xff\xd8\xff rest") == (".jpg", "image/jpeg")
    assert d(b"RIFF" + b"xxxx" + b"WEBP" + b"xx") == (".webp", "image/webp")
    try:
        d(b"not an image")
        raise AssertionError("should have raised")
    except ValueError:
        pass
    print("ok: detect_image_format")


def test_extract_reply_message_id():
    e = plugin.CodexDrawPlugin._extract_reply_message_id
    assert e({"reply_to": "top-id"}) == "top-id"
    assert e({"raw_message": [{"type": "reply", "data": {"target_message_id": "seg-id"}}]}) == "seg-id"
    assert e({}) == ""
    assert e(None) == ""
    print("ok: extract_reply_message_id")


def test_extract_tool_stream_id():
    e = plugin.CodexDrawPlugin._extract_tool_stream_id
    assert e({"stream_id": "s1"}) == "s1"
    assert e({"session_id": "s2"}) == "s2"
    assert e({"tool_execution_context": {"stream_id": "s3"}}) == "s3"
    assert e({"execution_context": {"session_id": "s4"}}) == "s4"
    assert e({}) == ""
    print("ok: extract_tool_stream_id")


def test_split_command_payload():
    s = plugin.CodexDrawPlugin._split_command_payload
    assert s("") == ("draw", "")
    assert s("一只红色的立方体") == ("draw", "一只红色的立方体")
    assert s("审查 把背景换成蓝色") == ("review", "把背景换成蓝色")
    assert s("check change the background to blue") == ("review", "change the background to blue")
    assert s("REVIEW draw a cat") == ("review", "draw a cat")
    # 首词不是审查词时整体作为绘图提示词
    assert s("审查一只猫") == ("draw", "审查一只猫")  # 无空格，"审查一只猫"整体不是子命令
    print("ok: split_command_payload")


def test_command_pattern_with_image_prefix():
    # 命令匹配不锚定开头，兼容「图片 + /gpt」同消息发送（图片文本排在 /gpt 前）
    m = re.search(plugin._GPT_COMMAND_PATTERN, "某段图片描述 /gpt 将图片改为摄影风格")
    assert m and m.group("prompt").strip() == "将图片改为摄影风格"
    m2 = re.search(plugin._GPT_COMMAND_PATTERN, "/gpt 一只红色的立方体")
    assert m2 and m2.group("prompt").strip() == "一只红色的立方体"
    m3 = re.search(plugin._GPT_COMMAND_PATTERN, "/gpt")
    assert m3 and m3.group("prompt").strip() == ""
    # 无斜杠、/gptxxx 均不应命中
    assert re.search(plugin._GPT_COMMAND_PATTERN, "gpt 没有斜杠") is None
    assert re.search(plugin._GPT_COMMAND_PATTERN, "/gptxxx 误匹配") is None
    print("ok: command pattern with image prefix")


if __name__ == "__main__":
    test_create_and_defaults()
    test_build_config_schema()
    test_normalize_proxy()
    test_build_proxy_env()
    test_parse_review_verdict()
    test_extract_thread_id()
    test_detect_image_format()
    test_extract_reply_message_id()
    test_extract_tool_stream_id()
    test_split_command_payload()
    test_command_pattern_with_image_prefix()
    print("\nALL SMOKE TESTS PASSED")
