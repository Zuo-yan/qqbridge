from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Any

from .config import HumanizerConfig, TargetProfile


FACT_PATTERNS = [
    r"你最(爱|喜欢|讨厌|常|习惯|擅长|怕|在意)",
    r"我记得你(最|之前|一直|曾经|说过|喜欢|讨厌)",
    r"你之前说(过)?",
    r"我们(相遇|认识|在一起|的纪念日|第一次|上次|以前)",
    r"我(给你)?(准备|买|做|带|留|挑)了",
    r"你送我",
    r"你一直",
    r"你的(口味|习惯|生日|纪念日|爱好|性格|脾气)",
    r"你(很喜欢|肯定喜欢|应该喜欢|一定喜欢)",
    r"我猜你",
    r"你肯定是",
    r"我记得我们",
    r"我们(下次|改天|以后|到时候)",
    r"每次你(都)?",
    r"你和(我|以前|别人).*不",
    r"你(小时候|从小|以前|过去)",
    r"你(性格|脾气).*(就是|一直|总是)",
    r"这是你(最|第)",
]

ANNIVERSARY_PATTERNS = [
    r"今天.*(纪念日|什么日子|特殊日子|生日)",
    r"明天.*(纪念日|什么日子|特殊日子|生日)",
    r"这周[一二三四五六日天].*(纪念日|什么日子|特殊日子)",
    r"(相识|认识|在一起).*(第?\d+|多少).*(天|日|个月|年)",
    r"第\d+.*(天|日|周年|个年头)",
    r"已经.*(天|日|个月|年).*(没|不)?.*见",
    r"(还记|记得).*那天",
    r"(去年|前年|上个月|上个星期).*(我们|你)",
]

SCENE_WORDS = [
    "怀里",
    "抱着",
    "靠在",
    "脸颊",
    "指尖",
    "耳边",
    "轻轻",
    "悄悄",
    "暖洋洋",
    "睡着",
    "窝在",
    "温柔地",
    "轻柔地",
    "微微一笑",
    "伸手",
    "握住",
    "靠过来",
    "贴近",
    "耳畔",
    "低语",
    "耳语",
    "抚摸",
    "依偎",
]

INTIMATE_TERMS = [
    "做爱",
    "肉棒",
    "小穴",
    "精液",
    "塞满",
    "硬了",
    "想要你",
    "插进",
    "进去了",
    "受不了了",
    "射了",
    "射在",
    "射进",
    "射到",
    "射出来",
    "舔我",
    "舔你",
    "舔干净",
    "舔着",
    "舔弄",
    "含住",
    "吸吮",
]

TOPIC_SHIFT_PATTERNS = [
    r"(中午|午饭|晚饭|吃饭|吃点|点些|煮点|开胃|饭|菜|外卖|下厨)",
    r"(天气|下雨|太阳|出门|上班|工作|日程|安排|加班|下班)",
    r"(喝水|口渴|洗漱|帮忙|打下手|家务|打扫|收拾)",
    r"(睡觉|困了|晚安|早点休息|快睡)",
    r"(明天.*(干嘛|做什么|打算|计划))",
]

INTIMATE_BRIDGE_FALLBACKS = [
    "别急着把话题带远呀，我还在认真听你说呢。",
    "嗯，我知道你是在逗我，也知道你想听我更认真一点。",
    "嗯，我在呢，刚才那句话我接住了，不会突然跳开。",
    "你说的我收到了，不会突然跳到别的事上。",
    "别急着岔开嘛，刚才你说的话我还想再听一会儿。",
    "我收到你说的了，不会假装没听见跑去聊别的。",
    "你刚才说的我接住了，不用这么快切换到日常。",
    "嗯，我在认真听，不走。",
]


@dataclass(slots=True)
class GuardResult:
    changed: bool
    text: str
    risk_types: list[str] = field(default_factory=list)
    evidence: str = ""


def is_intimate_context(*texts: str) -> bool:
    combined = "\n".join(text for text in texts if text)
    if not any(term in combined for term in INTIMATE_TERMS):
        return False
    # 排除“发射/火箭发射了”等日常用法对“射了/射在…”的误判：
    # 只有命中词全部来自“发射”词组时才不算亲密。
    cleaned = re.sub(r"发\s*射\w*", "", combined)
    return any(term in cleaned for term in INTIMATE_TERMS)


def _is_topic_shift_reply(text: str) -> bool:
    return any(re.search(pattern, text) for pattern in TOPIC_SHIFT_PATTERNS)


def _intimate_bridge_fallback(context_text: str, reply_text: str) -> str:
    digest = hashlib.sha256((context_text + reply_text).encode("utf-8")).digest()
    seed = int.from_bytes(digest[:8], "big")
    return INTIMATE_BRIDGE_FALLBACKS[seed % len(INTIMATE_BRIDGE_FALLBACKS)]


EVIDENCE_STOP_WORDS = frozenset({
    "未知",
    "不确定",
    "可能",
    "大概",
    "不要",
    "不能",
    "禁止",
    "留空",
    "填写",
    "配置",
    "插件",
    "画像",
    "备注",
    "说明",
    "目标",
    "用户",
    "私聊",
    "对象",
    "称呼",
    "偏好",
    "地区",
    "未填",
    "暂未",
})


def has_verified_evidence(text: str, profile: TargetProfile | None) -> bool:
    if not profile:
        return False
    haystack = "\n".join(block for _, block in profile.verified_blocks())
    if not haystack:
        return False
    compact_text = re.sub(r"\s+", "", text)
    compact_evidence = re.sub(r"\s+", "", haystack)
    # 原实现用 compact_text 提取 token 并检查 token in compact_evidence，
    # 但中文无空格导致正则贪婪匹配把整段变成一个巨型 token，验证永远失败。
    # 改为从证据侧拆分片段，再检查这些片段是否在回复文本中出现。
    fragments = [f for f in re.split(r"[：:；;，,。.！!？?\n/、｜|—…]+", compact_evidence) if f.strip()]
    evidence_candidates = {
        candidate
        for candidate in fragments
        if len(candidate) >= 3 and candidate not in EVIDENCE_STOP_WORDS
    }
    return any(candidate in compact_text for candidate in evidence_candidates)


def _risk_matches(patterns: list[str], text: str) -> bool:
    return any(re.search(pattern, text) for pattern in patterns)


def _compress_style(text: str, hard_limit: int) -> str:
    cleaned = re.sub(r"（[^）]{0,60}）", "", text)
    cleaned = re.sub(r"\*[^*]{0,80}\*", "", cleaned)
    cleaned = re.sub(r"。{2,}", "。", cleaned)
    sentences = re.split(r"(?<=[。！？!?])", cleaned)
    kept: list[str] = []
    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue
        if any(word in sentence for word in SCENE_WORDS) and len(kept) >= 1:
            continue
        kept.append(sentence)
        if sum(len(item) for item in kept) >= hard_limit:
            break
    result = "".join(kept).strip() or cleaned.strip()
    return result[:hard_limit].rstrip("，,；;、") if len(result) > hard_limit else result


def _fallback_for_fact(text: str) -> str:
    if "准备" in text or "买" in text or "做" in text or "带" in text:
        return "这个我不敢直接说已经准备好了，怕把没发生的事说成真的。你想要什么可以告诉我。"
    if "纪念日" in text or "什么日子" in text or "生日" in text:
        return "我不敢乱猜重要日子，怕把你不在意的事记错。你提醒我一下就好。"
    if "最" in text or "习惯" in text or "口味" in text:
        return "这个我还没有可靠依据，不想替你下结论。你愿意说的话，我会认真听。"
    if "我们" in text and ("第" in text or "天" in text or "年" in text):
        return "我不敢乱算日子，怕记错让你失望。你想让我记住的话跟我说一声。"
    if "记得" in text or "以前" in text or "上次" in text:
        return "我怕记混了。你能再跟我说一次吗？这次我认真记住。"
    return "这个我没有把握，不想乱猜。你告诉我一点，我再认真回应。"


def guard_reply_text(
    text: str,
    config: HumanizerConfig,
    profile: TargetProfile | None = None,
    context_text: str = "",
) -> GuardResult:
    original = text or ""
    revised = original.strip()
    risks: list[str] = []

    if config.guard.fact_guard_enabled and _risk_matches(FACT_PATTERNS, revised):
        if not has_verified_evidence(revised, profile):
            risks.append("unsupported_fact")
            revised = _fallback_for_fact(revised)

    if config.guard.anniversary_guard_enabled and _risk_matches(ANNIVERSARY_PATTERNS, revised):
        if not has_verified_evidence(revised, profile):
            risks.append("anniversary_guess")
            revised = _fallback_for_fact(revised)

    scene_score = sum(revised.count(word) for word in SCENE_WORDS)
    if config.guard.style_guard_enabled:
        too_long = len(revised) > config.guard.max_reply_chars_hard
        too_scenic = scene_score >= 3 and len(revised) > config.guard.max_reply_chars_soft
        if too_long or too_scenic:
            risks.append("novelistic_style")
            revised = _compress_style(revised, config.guard.max_reply_chars_hard)

    if config.guard.style_guard_enabled and is_intimate_context(context_text) and _is_topic_shift_reply(revised):
        risks.append("intimate_topic_shift")
        revised = _intimate_bridge_fallback(context_text, revised)

    return GuardResult(
        changed=revised != original.strip(),
        text=revised,
        risk_types=risks,
        evidence="verified profile matched" if risks and has_verified_evidence(original, profile) else "no verified evidence found",
    )


def guard_memory_items(items: Any, config: HumanizerConfig) -> tuple[Any, list[str]]:
    if not config.guard.memory_guard_enabled:
        return items, []

    blocked: list[str] = []

    def risky(value: Any) -> bool:
        text = str(value)
        return (
            _risk_matches(FACT_PATTERNS, text)
            or any(
                word in text
                for word in (
                    "纪念日", "生日", "最爱", "最喜欢", "礼物", "共同经历",
                    "第一次", "相遇", "认识那天", "从小就", "一直都",
                    "每次都会", "从来不会", "天生", "性格就是",
                    "用户喜欢", "用户爱", "用户讨厌", "用户偏好", "用户习惯", "用户口味",
                )
            )
        )

    if isinstance(items, list):
        kept = []
        for item in items:
            if risky(item):
                blocked.append(str(item))
            else:
                kept.append(item)
        return kept, blocked

    if isinstance(items, dict):
        filtered = {}
        for key, value in items.items():
            if risky(value):
                blocked.append(f"{key}: {value}")
            else:
                filtered[key] = value
        return filtered, blocked

    if risky(items):
        return None, [str(items)]
    return items, []
