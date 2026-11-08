"""梗百科 —— MaiBot 插件。

内置 6668 条网络梗词条（随插件分发的 SQLite 词库），提供：
- ``search_meme_wiki`` 工具：模型可自主调用查梗
- ``/梗 <词>`` 命令：人工查询

移植自 AstrBot 插件 ``in1t1a1/astrbot_plugin_memewiki``，词库（data/memes.db）沿用原项目。
"""
from __future__ import annotations

import asyncio
import logging
import sqlite3
from pathlib import Path
from typing import Any

from maibot_sdk import Command, MaiBotPlugin, Tool
from maibot_sdk.types import ToolParameterInfo, ToolParamType

PLUGIN_DIR = Path(__file__).resolve().parent
DB_PATH = PLUGIN_DIR / "data" / "memes.db"

CLIENT_TYPE = "github.beichen24a1.memewiki"

log = logging.getLogger("maibot.plugin.memewiki")

MAX_USAGE_CHARS = 400
MAX_ORIGIN_CHARS = 200


def _query_row(query: str) -> dict[str, Any] | None:
    """在本地词库里查一条：先精确命中标题，再取「消息中包含的最长标题」。"""
    q = (query or "").strip()
    if not q or not DB_PATH.exists():
        return None
    con = sqlite3.connect(str(DB_PATH))
    try:
        cur = con.execute(
            "SELECT title, tags, usage, origin, other, summary FROM memes WHERE title = ?", (q,)
        )
        row = cur.fetchone()
        if row is None:
            cur = con.execute(
                "SELECT title, tags, usage, origin, other, summary FROM memes "
                "WHERE length(title) >= 2 AND instr(?, title) > 0 "
                "ORDER BY length(title) DESC LIMIT 1",
                (q,),
            )
            row = cur.fetchone()
    finally:
        con.close()
    if row is None:
        return None
    title, tags, usage, origin, other, summary = row
    return {
        "title": title,
        "tags": [t for t in (tags or "").replace(",", "、").split("、") if t],
        "usage": usage or "",
        "origin": origin or "",
        "other": other or "",
        "summary": summary or "",
    }


def _format(entry: dict[str, Any]) -> str:
    """把词条排成「先会接，再解释」的短格式。"""
    lines = [f"【梗】{entry['title']}"]
    if entry["tags"]:
        lines.append("【标签】" + "、".join(entry["tags"][:6]))
    usage = entry["usage"].strip()
    if usage:
        lines.append("【怎么用】" + usage[:MAX_USAGE_CHARS])
    origin = entry["origin"].strip()
    if origin:
        lines.append("【出处】" + origin[:MAX_ORIGIN_CHARS])
    if not usage and not origin:
        fallback = (entry["summary"] or entry["other"]).strip()
        if fallback:
            lines.append("【说明】" + fallback[:MAX_USAGE_CHARS])
    return "\n".join(lines)


def _miss_hint(query: str) -> str:
    return f"词库里没有「{query}」这条梗。别硬编，可以说自己没听过，或者反问对方这是什么梗、怎么用。"


async def lookup_meme(query: str) -> str:
    entry = await asyncio.to_thread(_query_row, query)
    if entry is None:
        return _miss_hint(query)
    return _format(entry)


class MemeWikiPlugin(MaiBotPlugin):
    def __init__(self) -> None:
        super().__init__()

    async def on_load(self) -> None:
        n = 0
        if DB_PATH.exists():
            def _count() -> int:
                con = sqlite3.connect(str(DB_PATH))
                try:
                    return int(con.execute("SELECT count(*) FROM memes").fetchone()[0])
                finally:
                    con.close()
            try:
                n = await asyncio.to_thread(_count)
            except Exception as exc:  # noqa: BLE001
                log.error("读取梗词库失败: %s", exc)
        else:
            log.error("梗词库缺失: %s（请确认 data/memes.db 随插件一起分发）", DB_PATH)
        log.info("梗百科已加载，本地词条=%d", n)

    async def on_unload(self) -> None:
        return None

    async def on_config_update(self, scope: str, config_data: dict, version: str) -> None:
        return None

    # ---------------- 模型可调用的工具 ----------------
    @Tool(
        "search_meme_wiki",
        description="查询网络梗 / 黑话 / 缩写的含义与用法。当遇到没把握的新词、梗、缩写时先查它，别硬猜。",
        brief_description="查网络梗/黑话含义与用法",
        detailed_description=(
            "返回词条的【怎么用】【出处】【标签】。查到之后先照着用法接一句，"
            "像本来就会；只有对方明确问「这是什么梗」才解释出处，一两句即可。"
            "查不到就直说没听过，不要编。"
        ),
        parameters=[
            ToolParameterInfo(
                name="query",
                param_type=ToolParamType.STRING,
                description="要查的梗、黑话或缩写，例如「绝绝子」「打工人」",
                required=True,
            ),
        ],
    )
    async def handle_search_meme_wiki(self, query: str = "", **kwargs: Any) -> str:
        return await lookup_meme(query)

    # ---------------- 人工查询命令 ----------------
    @Command(
        "meme",
        description="查询梗百科（/梗 <词>）",
        pattern=r"^/梗\s+(.+)",
    )
    async def handle_meme_command(self, **kwargs: Any) -> str:
        text = str(kwargs.get("text") or "").strip()
        stream_id = str(kwargs.get("stream_id") or "")
        query = text
        for prefix in ("/梗", "／梗"):
            if query.startswith(prefix):
                query = query[len(prefix):].strip()
                break
        if not query:
            result = "用法：/梗 <词>，例如 /梗 绝绝子"
        else:
            result = await lookup_meme(query)
        if stream_id:
            try:
                await self.ctx.send.text(result, stream_id)
                return ""
            except Exception as exc:  # noqa: BLE001
                log.warning("梗百科回复失败: %s", exc)
        return result


def create_plugin() -> MaiBotPlugin:
    return MemeWikiPlugin()
