import sys
from pathlib import Path

_PLUGIN_DIR = Path(__file__).resolve().parent.parent
_PLUGIN_DIR_TEXT = str(_PLUGIN_DIR)
if _PLUGIN_DIR_TEXT not in sys.path:
    sys.path.insert(0, _PLUGIN_DIR_TEXT)

import unittest

from private_humanizer.config import HumanizerConfig, load_config
from private_humanizer.context import (
    chat_type_from_message,
    classify_session_id,
    extract_chat_fields,
    extract_last_user_message,
    extract_message_text,
    is_definitely_group,
    is_definitely_private,
)
from private_humanizer.guards import (
    INTIMATE_BRIDGE_FALLBACKS,
    INTIMATE_TERMS,
    guard_memory_items,
    guard_reply_text,
    is_intimate_context,
)
from private_humanizer.matching import Matcher, MatchResult
from private_humanizer.prompting import append_extra_prompt, build_humanizer_prompt
from private_humanizer.session import SessionTracker


RAW_CONFIG = {
    "plugin": {
        "enabled": True,
        "private_only": True,
        "target_platforms": ["qq"],
        "target_user_ids": ["123456789"],
    },
    "schedule": {
        "manual_schedule": "下午整理房间，晚上陪用户聊天。",
    },
    "life_environment": {
        "environment": "",
        "auto_generate_when_empty": True,
    },
    "target_profiles": [
        {
            "profile_id": "target",
            "platform": "qq",
            "user_id": "123456789",
            "display_name": "目标用户",
            "preferences": "聊天偏好：喜欢亲密但自然的陪伴。",
            "important_dates": "生日：未知",
        }
    ],
}


_EMPTY_SESSION = SessionTracker()


class CoreTest(unittest.TestCase):
    def _matcher(self, config: HumanizerConfig | None = None) -> Matcher:
        return Matcher(config or load_config(RAW_CONFIG), _EMPTY_SESSION)

    def test_matches_target_private_chat(self):
        config = load_config(RAW_CONFIG)
        matcher = self._matcher(config)
        match = matcher.match(
            {"message": {"platform": "qq", "user_id": "123456789", "chat_type": "private"}},
        )
        self.assertTrue(match.matched)
        self.assertEqual(match.profile.display_name, "目标用户")

    def test_skips_group_chat(self):
        config = load_config(RAW_CONFIG)
        matcher = self._matcher(config)
        match = matcher.match(
            {"message": {"platform": "qq", "user_id": "123456789", "group_id": "123", "chat_type": "group"}},
        )
        self.assertFalse(match.matched)

    def test_is_definitely_private_checks(self):
        self.assertTrue(is_definitely_private({"chat_type": "private"}))
        self.assertTrue(is_definitely_private({"chat_type": "dm"}))
        self.assertFalse(is_definitely_private({"chat_type": "group"}))
        self.assertFalse(is_definitely_private({"chat_type": "", "group_id": "123"}))

    def test_is_definitely_group_checks(self):
        self.assertTrue(is_definitely_group({"chat_type": "group"}))
        self.assertTrue(is_definitely_group({"group_id": "123", "chat_type": ""}))
        self.assertFalse(is_definitely_group({"chat_type": "private"}))
        self.assertFalse(is_definitely_group({"chat_type": "", "group_id": ""}))

    def test_extract_chat_fields_from_nested_message(self):
        fields = extract_chat_fields({
            "message": {"platform": "qq", "user_id": "123", "chat_type": "private"},
            "session_id": "s1",
        })
        self.assertEqual(fields["platform"], "qq")
        self.assertEqual(fields["user_id"], "123")
        self.assertEqual(fields["chat_type"], "private")

    def test_prompt_contains_boundaries(self):
        config = load_config(RAW_CONFIG)
        prompt = build_humanizer_prompt(config, config.target_profiles[0])
        self.assertIn("事实边界", prompt)
        self.assertIn("未知", prompt)
        self.assertIn("目标用户", prompt)

    def test_prompt_contains_life_environment_and_schedule(self):
        config = load_config(RAW_CONFIG)
        prompt = build_humanizer_prompt(config, config.target_profiles[0])
        self.assertIn("生活环境", prompt)
        self.assertIn("自动生成", prompt)
        self.assertIn("私聊日程参考", prompt)
        self.assertIn("下午整理房间", prompt)

    def test_append_extra_prompt_sets_when_empty(self):
        result = append_extra_prompt({"extra_prompt": ""}, "test")
        self.assertIn("test", result["extra_prompt"])

    def test_append_extra_prompt_appends(self):
        result = append_extra_prompt({"extra_prompt": "hello"}, "world")
        self.assertEqual(result["extra_prompt"], "hello\n\nworld")

    def test_guard_rewrites_unsupported_preference(self):
        config = load_config(RAW_CONFIG)
        result = guard_reply_text("我给你准备了你最爱的蜜桃粽子。", config, config.target_profiles[0])
        self.assertTrue(result.changed)
        self.assertIn("不敢", result.text)

    def test_guard_fallback_for_fact_uses_right_template(self):
        config = load_config(RAW_CONFIG)
        result = guard_reply_text("我给你买了一件你最爱的东西。", config)
        self.assertTrue(result.changed)
        self.assertIn("不敢", result.text)

    def test_guard_blocks_daily_topic_shift_in_intimate_context(self):
        config = load_config(RAW_CONFIG)
        result = guard_reply_text(
            "那我们中午打算吃点什么呢♪",
            config,
            config.target_profiles[0],
            context_text="肉棒还在小穴里没有拔出来呢",
        )
        self.assertTrue(result.changed)
        self.assertIn("intimate_topic_shift", result.risk_types)

    def test_guard_keeps_daily_topic_without_intimate_context(self):
        config = load_config(RAW_CONFIG)
        result = guard_reply_text(
            "那我们中午打算吃点什么呢♪",
            config,
            config.target_profiles[0],
            context_text="早上好呢",
        )
        self.assertFalse(result.changed)

    def test_guard_does_not_false_trigger_on_common_words(self):
        config = load_config(RAW_CONFIG)
        result = guard_reply_text(
            "抱抱你，今天身体舒服吗？",
            config,
            config.target_profiles[0],
            context_text="我今天跑完步腿有点酸",
        )
        self.assertFalse(result.changed)

    def test_intimate_bridge_fallbacks_are_gender_neutral(self):
        for fallback in INTIMATE_BRIDGE_FALLBACKS:
            self.assertNotIn("姐姐", fallback)

    def test_intimate_terms_excludes_common_words(self):
        self.assertNotIn("舒服", INTIMATE_TERMS)
        self.assertNotIn("身体", INTIMATE_TERMS)
        self.assertNotIn("腿", INTIMATE_TERMS)
        self.assertNotIn("嘴巴", INTIMATE_TERMS)
        self.assertNotIn("亲", INTIMATE_TERMS)
        self.assertNotIn("吻", INTIMATE_TERMS)
        self.assertNotIn("抱", INTIMATE_TERMS)
        self.assertNotIn("射", INTIMATE_TERMS)
        self.assertNotIn("舔", INTIMATE_TERMS)

    def test_is_intimate_context_only_matches_explicit(self):
        self.assertTrue(is_intimate_context("我想要做爱"))
        self.assertTrue(is_intimate_context("肉棒"))
        self.assertFalse(is_intimate_context("今天身体不舒服"))
        self.assertFalse(is_intimate_context("亲，你好呀"))
        self.assertFalse(is_intimate_context("今天发射了火箭"))
        self.assertFalse(is_intimate_context("他是一条舔狗"))
        self.assertTrue(is_intimate_context("射在里面了"))

    def test_memory_guard_filters_risky_items(self):
        config = load_config(RAW_CONFIG)
        filtered, blocked = guard_memory_items(["用户最喜欢桃子汽水", "用户今天说要加班"], config)
        self.assertEqual(filtered, ["用户今天说要加班"])
        self.assertEqual(len(blocked), 1)

    def test_memory_guard_handles_dict_items(self):
        config = load_config(RAW_CONFIG)
        filtered, blocked = guard_memory_items({"good": "hello", "fact": "用户最喜欢桃子汽水"}, config)
        self.assertEqual(filtered, {"good": "hello"})
        self.assertGreater(len(blocked), 0)

    def test_memory_guard_blocks_risky_situation_string(self):
        config = load_config(RAW_CONFIG)
        filtered, blocked = guard_memory_items("用户最喜欢桃子汽水", config)
        self.assertIsNone(filtered)
        self.assertEqual(len(blocked), 1)

        filtered_safe, blocked_safe = guard_memory_items("用户今天说要加班", config)
        self.assertEqual(filtered_safe, "用户今天说要加班")
        self.assertEqual(blocked_safe, [])

    def test_followup_config_defaults(self):
        config = load_config(RAW_CONFIG)
        self.assertTrue(config.proactive_followup.enabled)
        self.assertTrue(config.schedule.inject_into_planner)
        self.assertTrue(config.life_environment.auto_generate_when_empty)
        self.assertTrue(config.schedule.allow_user_interrupt)
        self.assertEqual(config.proactive_followup.delay_seconds, 35)
        self.assertFalse(config.logging.save_rewrite_pairs)

    def test_standard_user_id_mismatch_is_not_target(self):
        config = load_config(RAW_CONFIG)
        matcher = self._matcher(config)
        match = matcher.match(
            {"session_id": "abc", "platform": "qq", "user_id": "not-target", "chat_type": "private"},
        )
        self.assertFalse(match.matched)

    def test_config_empty_fields_handled(self):
        empty_config = {
            "plugin": {"enabled": True, "target_platforms": [], "target_user_ids": []},
        }
        config = load_config(empty_config)
        self.assertTrue(config.plugin.enabled)
        self.assertEqual(config.target_profiles, [])

    def test_config_load_handles_none(self):
        config = load_config(None)
        self.assertTrue(config.plugin.enabled)

    def test_config_bool_strings_are_parsed(self):
        """字符串形式的布尔配置不能按 Python bool() 语义误解析（"false" -> True）。"""
        config = load_config({
            "plugin": {
                "enabled": "false",
                "private_only": "false",
                "target_platforms": ["qq"],
                "target_user_ids": ["123456789"],
            },
            "guard": {
                "memory_guard_enabled": "false",
                "style_guard_enabled": "false",
            },
            "logging": {"enabled": "false"},
        })
        self.assertFalse(config.plugin.enabled)
        self.assertFalse(config.plugin.private_only)
        self.assertFalse(config.guard.memory_guard_enabled)
        self.assertFalse(config.guard.style_guard_enabled)
        self.assertFalse(config.logging.enabled)

        config_true = load_config({
            "plugin": {"enabled": "true", "private_only": "on"},
        })
        self.assertTrue(config_true.plugin.enabled)
        self.assertTrue(config_true.plugin.private_only)


    def test_matches_target_without_explicit_chat_type(self):
        config = load_config(RAW_CONFIG)
        sessions = SessionTracker()
        matcher = Matcher(config, sessions)
        match = matcher.match(
            {"platform": "qq", "user_id": "123456789"},
        )
        self.assertTrue(
            match.matched,
            f"Should match target user even without chat_type in kwargs (reason={match.reason})",
        )

    def test_matches_via_captured_chat_type(self):
        config = load_config(RAW_CONFIG)
        sessions = SessionTracker()
        sessions.capture("sess_001", chat_type="private")
        matcher = Matcher(config, sessions)
        match = matcher.match(
            {"session_id": "sess_001", "platform": "qq", "user_id": "123456789"},
        )
        self.assertTrue(match.matched)

    # ------------------------------------------------------------------
    # 泄露修复：群聊会话 ID 形态识别与硬拦截
    # ------------------------------------------------------------------

    def test_group_session_id_never_matches_in_model_hook(self):
        """Replyer/Planner hook 只有 session_id=qq_group_xxx 时，即使文本里有目标称呼也不注入。"""
        config = load_config(RAW_CONFIG)
        sessions = SessionTracker()
        matcher = Matcher(config, sessions)
        match = matcher.match(
            {
                "session_id": "qq_group_1049246517",
                "messages": [{"role": "user", "content": "目标用户今天在群里说了什么呀"}],
            },
        )
        self.assertFalse(match.matched)

    def test_group_session_id_rejects_even_with_target_user_id(self):
        config = load_config(RAW_CONFIG)
        matcher = Matcher(config, SessionTracker())
        match = matcher.match(
            {
                "session_id": "qq_group_1049246517",
                "user_id": "123456789",
                "chat_type": "group",
            },
        )
        self.assertFalse(match.matched)

    def test_poisoned_group_cache_is_rejected_and_cleaned(self):
        """历史脏缓存（群会话被误标记为私聊）也要被硬拦截并清掉。"""
        config = load_config(RAW_CONFIG)
        sessions = SessionTracker()
        sessions.mark_matched("qq_group_1049246517", chat_type="private")
        matcher = Matcher(config, sessions)
        match = matcher.match({"session_id": "qq_group_1049246517"})
        self.assertFalse(match.matched)
        self.assertFalse(sessions.is_matched("qq_group_1049246517"))
        self.assertEqual(
            sessions.get_captured("qq_group_1049246517").get("chat_type"),
            "group",
        )

    def test_receive_capture_de_poisons_group_session(self):
        """群消息在 receive 阶段就把曾经误匹配的会话缓存降级为 group。"""
        config = load_config(RAW_CONFIG)
        sessions = SessionTracker()
        sessions.mark_matched("qq_group_1049246517", chat_type="private")
        sessions.reject_group("qq_group_1049246517")
        self.assertFalse(sessions.is_matched("qq_group_1049246517"))

    # ------------------------------------------------------------------
    # 识别修复：私聊形态会话 ID / receive 确认
    # ------------------------------------------------------------------

    def test_private_session_id_matches_without_user_id(self):
        """Replyer/Planner hook 只有 session_id=qq_private_<target> 时也能命中。"""
        config = load_config(RAW_CONFIG)
        matcher = Matcher(config, SessionTracker())
        match = matcher.match({"session_id": "qq_private_123456789"})
        self.assertTrue(match.matched)
        self.assertEqual(match.user_id, "123456789")
        self.assertEqual(match.reason, "private session user matched")

    def test_private_session_id_mismatch_is_not_target(self):
        config = load_config(RAW_CONFIG)
        matcher = Matcher(config, SessionTracker())
        match = matcher.match({"session_id": "qq_private_999999999"})
        self.assertFalse(match.matched)

    def test_receive_capture_confirms_target_session(self):
        """chat.receive 的序列化消息按 message_info 确认目标，之后只有 session_id 的 hook 也能命中。"""
        config = load_config(RAW_CONFIG)
        sessions = SessionTracker()
        message = {
            "platform": "qq",
            "session_id": "qq_private_123456789",
            "message_info": {
                "user_info": {"user_id": "123456789", "user_nickname": "小明"},
                "group_info": None,
            },
        }
        sessions.capture(
            str(message.get("session_id", "")),
            chat_type=chat_type_from_message(message),
            platform=message.get("platform", ""),
            user_id=message["message_info"]["user_info"]["user_id"],
        )
        sessions.confirm_target(
            message["session_id"],
            platform=message["platform"],
            user_id=message["message_info"]["user_info"]["user_id"],
        )
        matcher = Matcher(config, sessions)
        match = matcher.match({"session_id": "qq_private_123456789"})
        self.assertTrue(match.matched)

    def test_receive_capture_group_not_confirmed(self):
        config = load_config(RAW_CONFIG)
        sessions = SessionTracker()
        message = {
            "platform": "qq",
            "session_id": "qq_group_1049246517",
            "message_info": {
                "user_info": {"user_id": "123456789", "user_nickname": "小明"},
                "group_info": {"group_id": "1049246517", "group_name": "测试群"},
            },
        }
        self.assertEqual(chat_type_from_message(message), "group")
        sessions.reject_group(message["session_id"])
        matcher = Matcher(config, sessions)
        match = matcher.match({"session_id": "qq_group_1049246517"})
        self.assertFalse(match.matched)

    def test_prompt_fallback_rejects_empty_session(self):
        """没有 session_id 时禁止用提示词文本兜底，防止注入到无法确认的会话。"""
        config = load_config(RAW_CONFIG)
        matcher = Matcher(config, SessionTracker())
        match = matcher.match(
            {"messages": [{"role": "user", "content": "目标用户今天过得怎么样"}]},
        )
        self.assertFalse(match.matched)

    def test_prompt_fallback_rejects_group_session_id(self):
        config = load_config(RAW_CONFIG)
        matcher = Matcher(config, SessionTracker())
        match = matcher.match(
            {
                "session_id": "qq_group_1049246517",
                "messages": [{"role": "user", "content": "目标用户今天在群里怎么样"}],
            },
        )
        self.assertFalse(match.matched)

    def test_prompt_fallback_works_for_private_session_id(self):
        config = load_config(RAW_CONFIG)
        matcher = Matcher(config, SessionTracker())
        match = matcher.match(
            {
                "session_id": "dm_other_user",
                "messages": [{"role": "user", "content": "目标用户今天过得怎么样"}],
            },
        )
        self.assertTrue(match.matched)
        self.assertEqual(match.reason, "prompt text matched")

    def test_prompt_fallback_skips_default_profile_id(self):
        """默认占位 profile_id="target" 不参与文本匹配，避免误命中英文 target。"""
        config = load_config(RAW_CONFIG)
        matcher = Matcher(config, SessionTracker())
        match = matcher.match(
            {
                "session_id": "dm_other_user",
                "messages": [{"role": "user", "content": "请把 target 设置成 100"}],
            },
        )
        self.assertFalse(match.matched)

    def test_extract_last_user_message(self):
        messages = [
            {"role": "system", "content": "system"},
            {"role": "assistant", "content": "回复"},
            {"role": "user", "content": "第一条"},
            {"role": "assistant", "content": "再回复"},
            {"role": "user", "content": ["<message user=\"A\">", "第二条"]},
        ]
        self.assertEqual(extract_last_user_message(messages), "<message user=\"A\">\n第二条")
        self.assertEqual(extract_last_user_message([]), "")
        self.assertEqual(extract_last_user_message(None), "")
        self.assertEqual(extract_last_user_message([{"role": "assistant", "content": "x"}]), "")

    def test_classify_session_id(self):
        self.assertEqual(classify_session_id("qq_group_1049246517"), "group")
        self.assertEqual(classify_session_id("group_123"), "group")
        self.assertEqual(classify_session_id("qq_private_3130274394"), "private")
        self.assertEqual(classify_session_id("private_123"), "private")
        self.assertEqual(classify_session_id("qq_123456"), "private")
        self.assertEqual(classify_session_id(""), "")
        self.assertEqual(classify_session_id("random-uuid"), "")

    def test_extract_chat_fields_derives_chat_type_from_session_id(self):
        fields = extract_chat_fields({"session_id": "qq_group_1049246517"})
        self.assertEqual(fields["chat_type"], "group")
        fields = extract_chat_fields({"session_id": "qq_private_123456789"})
        self.assertEqual(fields["chat_type"], "private")


class MatcherSpecificTest(unittest.TestCase):
    """Tests for the Matcher's internal matching strategies."""

    def test_match_by_fields_direct_hit(self):
        config = load_config(RAW_CONFIG)
        matcher = Matcher(config, SessionTracker())
        result = matcher._match_by_fields(
            {"message": {"platform": "qq", "user_id": "123456789", "chat_type": "private"}},
            config,
        )
        self.assertTrue(result.matched)
        self.assertEqual(result.reason, "profile matched")

    def test_match_by_fields_rejects_group(self):
        config = load_config(RAW_CONFIG)
        matcher = Matcher(config, SessionTracker())
        result = matcher._match_by_fields(
            {"message": {"platform": "qq", "user_id": "123456789", "chat_type": "group", "group_id": "g1"}},
            config,
        )
        self.assertFalse(result.matched)
        self.assertEqual(result.reason, "not private chat")

    def test_match_by_fields_uncertain_returns_not_target(self):
        config = load_config(RAW_CONFIG)
        matcher = Matcher(config, SessionTracker())
        result = matcher._match_by_fields(
            {"message": {"platform": "qq", "user_id": "999", "chat_type": "private"}},
            config,
        )
        self.assertFalse(result.matched)
        self.assertEqual(result.reason, "not target")

    def test_session_cache_match_works_after_confirmation(self):
        config = load_config(RAW_CONFIG)
        sessions = SessionTracker()
        sessions.confirm_target("sess_001", platform="qq", user_id="123456789")
        matcher = Matcher(config, sessions)
        result = matcher._match_by_session(
            {"session_id": "sess_001", "platform": "qq", "user_id": "123456789"},
            config,
        )
        self.assertTrue(result.matched)
        self.assertEqual(result.reason, "cached matched session")

    def test_session_cache_does_not_match_unconfirmed_session(self):
        config = load_config(RAW_CONFIG)
        matcher = Matcher(config, SessionTracker())
        result = matcher._match_by_session(
            {"session_id": "unknown_sess"},
            config,
        )
        self.assertFalse(result.matched)

    def test_prompt_match_does_not_fire_in_group_text(self):
        config = load_config(RAW_CONFIG)
        matcher = Matcher(config, SessionTracker())
        result = matcher._match_by_prompt(
            {
                "messages": [{"role": "user", "content": "今天在群聊里聊到目标用户的事情"}],
                "group_id": "123",
            },
            config,
        )
        self.assertFalse(result.matched)

    def test_prompt_match_fires_with_name_in_private_text(self):
        config = load_config(RAW_CONFIG)
        matcher = Matcher(config, SessionTracker())
        result = matcher._match_by_prompt(
            {
                "session_id": "qq_private_123456789",
                "messages": [{"role": "user", "content": "目标用户今天过得怎么样"}],
            },
            config,
        )
        self.assertTrue(result.matched)
        self.assertEqual(result.reason, "prompt text matched")

    def test_prompt_match_fires_with_items_payload(self):
        """1.2.x 的 items（ContextItem 快照）载荷也能走 prompt 文本兜底。"""
        config = load_config(RAW_CONFIG)
        matcher = Matcher(config, SessionTracker())
        result = matcher._match_by_prompt(
            {
                "session_id": "qq_private_123456789",
                "items": [
                    {
                        "item_type": "SystemMessageItem",
                        "parts": [{"type": "text", "text": "你是麦麦"}],
                    },
                    {
                        "item_type": "UserMessageItem",
                        "parts": [{"type": "text", "text": "目标用户今天过得怎么样"}],
                    },
                ],
            },
            config,
        )
        self.assertTrue(result.matched)
        self.assertEqual(result.reason, "prompt text matched")

    def test_prompt_match_items_payload_still_rejects_group(self):
        config = load_config(RAW_CONFIG)
        matcher = Matcher(config, SessionTracker())
        result = matcher._match_by_prompt(
            {
                "session_id": "qq_group_1049246517",
                "items": [
                    {
                        "item_type": "UserMessageItem",
                        "parts": [{"type": "text", "text": "目标用户今天在群里说了什么"}],
                    }
                ],
            },
            config,
        )
        self.assertFalse(result.matched)


class ContextFunctionTest(unittest.TestCase):
    """Test pure context extraction functions."""

    def test_extract_chat_fields_flat(self):
        fields = extract_chat_fields({"platform": "qq", "user_id": "u1", "chat_type": "private"})
        self.assertEqual(fields["platform"], "qq")
        self.assertEqual(fields["user_id"], "u1")
        self.assertEqual(fields["chat_type"], "private")

    def test_extract_chat_fields_missing(self):
        fields = extract_chat_fields({"some_other_key": "x"})
        self.assertEqual(fields["platform"], "")
        self.assertEqual(fields["user_id"], "")
        self.assertEqual(fields["chat_type"], "")

    def test_extract_chat_fields_from_messages(self):
        fields = extract_chat_fields({
            "messages": [{"user_id": "u1", "chat_type": "private"}],
        })
        self.assertEqual(fields["user_id"], "u1")

    def test_extract_chat_fields_multiple_sources(self):
        fields = extract_chat_fields({
            "message": {"user_id": "from_msg"},
            "metadata": {"user_id": "from_meta"},
        })
        self.assertEqual(fields["user_id"], "from_msg")

    def test_extract_last_user_message_legacy_format(self):
        messages = [
            {"role": "system", "content": "system"},
            {"role": "assistant", "content": "回复"},
            {"role": "user", "content": "晚上好呀"},
        ]
        self.assertEqual(extract_last_user_message(messages), "晚上好呀")

    def test_extract_last_user_message_context_item_snapshot(self):
        messages = [
            {"item_type": "SystemMessageItem", "parts": [{"type": "text", "text": "system"}]},
            {"item_type": "AssistantMessageItem", "parts": [{"type": "text", "text": "回复"}]},
            {
                "item_type": "UserMessageItem",
                "parts": [
                    {"type": "image", "image_base64": "xxx", "image_format": "png"},
                    {"type": "text", "text": " 晚上好呀 "},
                ],
            },
        ]
        self.assertEqual(extract_last_user_message(messages), "晚上好呀")

    def test_extract_last_user_message_mixed_skips_non_user(self):
        messages = [
            {"item_type": "UserMessageItem", "parts": [{"type": "text", "text": "旧消息"}]},
            {"role": "assistant", "content": "最后一条不是用户"},
        ]
        self.assertEqual(extract_last_user_message(messages), "旧消息")

    def test_extract_message_text_legacy(self):
        messages = [
            {"role": "system", "content": "系统提示"},
            {"role": "user", "content": "目标用户你好"},
        ]
        self.assertIn("系统提示", extract_message_text(messages))
        self.assertIn("目标用户你好", extract_message_text(messages))

    def test_extract_message_text_items_snapshot(self):
        messages = [
            {
                "item_type": "SystemMessageItem",
                "parts": [
                    {"type": "text", "text": "系统提示"},
                    {"type": "image", "image_base64": "x", "image_format": "png"},
                ],
            },
            {
                "item_type": "UserMessageItem",
                "parts": [{"type": "text", "text": "目标用户今天过得怎么样"}],
            },
        ]
        text = extract_message_text(messages)
        self.assertIn("系统提示", text)
        self.assertIn("目标用户今天过得怎么样", text)
        self.assertNotIn("image_base64", text)

    def test_extract_message_text_mixed_and_empty(self):
        self.assertEqual(extract_message_text(None), "")
        self.assertEqual(extract_message_text([]), "")
        self.assertEqual(
            extract_message_text(
                [
                    {"item_type": "ReasoningItem", "text_parts": ["思考"]},
                    {"role": "user", "content": "普通消息"},
                ]
            ),
            "普通消息",
        )


class ItemsInjectionTest(unittest.TestCase):
    """v1.2.x ContextItem 快照（items 载荷）注入测试。"""

    @staticmethod
    def _plugin_cls():
        from plugin import PrivateHumanizerPlugin

        return PrivateHumanizerPlugin

    def _system_items(self) -> list[dict]:
        return [
            {
                "item_type": "SystemMessageItem",
                "meta": {
                    "item_id": "a" * 32,
                    "logical_turn_id": None,
                    "timestamp": "2026-08-28T01:00:00+00:00",
                },
                "parts": [{"type": "text", "text": "你是麦麦"}],
            },
            {
                "item_type": "UserMessageItem",
                "meta": {
                    "item_id": "b" * 32,
                    "logical_turn_id": None,
                    "timestamp": "2026-08-28T01:00:01+00:00",
                },
                "parts": [{"type": "text", "text": "在吗"}],
            },
        ]

    def test_inject_items_appends_to_existing_system_item(self):
        cls = self._plugin_cls()
        prompt = "[Private Humanizer 私聊增强约束]\n约束内容"
        injected = cls._inject_items(self._system_items(), prompt, "[Private Humanizer 私聊增强约束]")
        self.assertEqual(len(injected), 2)
        self.assertEqual(injected[0]["item_type"], "SystemMessageItem")
        texts = [p["text"] for p in injected[0]["parts"] if p.get("type") == "text"]
        self.assertEqual(len(texts), 2)
        self.assertTrue(texts[-1].startswith("[Private Humanizer 私聊增强约束]"))

    def test_inject_items_is_idempotent(self):
        cls = self._plugin_cls()
        prompt = "[Private Humanizer 私聊增强约束]\n约束内容"
        once = cls._inject_items(self._system_items(), prompt, "[Private Humanizer 私聊增强约束]")
        twice = cls._inject_items(once, prompt, "[Private Humanizer 私聊增强约束]")
        texts = [p["text"] for p in twice[0]["parts"] if p.get("type") == "text"]
        self.assertEqual(
            sum(t.startswith("[Private Humanizer 私聊增强约束]") for t in texts),
            1,
        )

    def test_inject_items_prepends_when_no_system_item(self):
        cls = self._plugin_cls()
        items = [item for item in self._system_items() if item["item_type"] != "SystemMessageItem"]
        injected = cls._inject_items(items, "约束内容", "[Private Humanizer 私聊增强约束]")
        self.assertEqual(injected[0]["item_type"], "SystemMessageItem")
        self.assertEqual(len(injected), 2)
        meta = injected[0]["meta"]
        self.assertTrue(meta["item_id"])
        self.assertIsNone(meta["logical_turn_id"])

    def test_inject_items_rejects_non_list(self):
        cls = self._plugin_cls()
        self.assertIsNone(cls._inject_items(None, "x", "m"))
        self.assertIsNone(cls._inject_items({"role": "system", "content": "x"}, "x", "m"))

    def test_find_items_only_matches_items_key(self):
        cls = self._plugin_cls()
        items = self._system_items()
        self.assertIs(cls._find_items({"items": items, "session_id": "s1"}), items)
        self.assertIsNone(cls._find_items({"messages": items, "session_id": "s1"}))


if __name__ == "__main__":
    unittest.main()
