"""端到端：直接调用 _run_codex 验证 codex 生成与编辑（真实出图，需本机代理）。

运行：python tests/test_codex_e2e.py
"""

from pathlib import Path
from types import SimpleNamespace

import asyncio
import logging
import sys

PLUGIN_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PLUGIN_DIR))

import plugin  # noqa: E402


def _make_plugin() -> plugin.CodexDrawPlugin:
    p = plugin.create_plugin()
    p.set_plugin_config(
        {
            "plugin": {"enabled": True, "config_version": "1"},
            "codex": {
                "codex_path": "codex",
                "proxy_url": "127.0.0.1:7890",
                "model": "",
                "timeout_seconds": 240,
                "generated_dir": "",
            },
            "compliance": {"enabled": True, "review_model": "vlm", "timeout_ms": 60000},
        }
    )
    p._set_context(SimpleNamespace(logger=logging.getLogger("codex-draw-e2e")))
    return p


async def main() -> None:
    p = _make_plugin()

    # 1) 纯生成
    gen_bytes, gen_mime = await p._run_codex(
        "Generate a single image of a red cube on a plain white background. "
        "Only produce the image, do not write any code.",
        None,
    )
    print(f"[generate] ok mime={gen_mime} bytes={len(gen_bytes)}")
    assert gen_bytes[:8] == b"\x89PNG\r\n\x1a\n" or gen_bytes[:3] == b"\xff\xd8\xff", "not an image"

    # 2) 用产物作为参考图做编辑
    ref = plugin.ReferenceImage(
        content=gen_bytes,
        suffix=plugin.CodexDrawPlugin._detect_image_format(gen_bytes)[0],
        mime_type=gen_mime,
    )
    edit_bytes, edit_mime = await p._run_codex(
        "把这张图里的立方体的背景改成深蓝色，其余保持不变。只产出图片。",
        ref,
    )
    print(f"[edit]     ok mime={edit_mime} bytes={len(edit_bytes)}")
    assert edit_bytes, "empty edit output"
    print("\nCODEX E2E PASSED")


if __name__ == "__main__":
    asyncio.run(main())
