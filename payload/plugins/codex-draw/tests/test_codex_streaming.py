"""Codex 出图进程与产物监听回归测试（不调用真实 Codex 或图片模型）。"""

from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List
from unittest.mock import Mock, patch

import asyncio
import base64
import os
import pytest
import signal
import sys
import time

PLUGIN_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PLUGIN_DIR))

import plugin  # noqa: E402


_TINY_PNG_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJ"
    "AAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


def _make_plugin(
    output_dir: Path, *, max_concurrent_jobs: int = 4
) -> plugin.CodexDrawPlugin:
    instance = plugin.create_plugin()
    instance.set_plugin_config(
        {
            "plugin": {"enabled": True, "config_version": "1"},
            "codex": {
                "codex_path": "codex",
                "proxy_url": "",
                "model": "",
                "timeout_seconds": 10,
                "max_concurrent_jobs": max_concurrent_jobs,
                "generated_dir": str(output_dir),
            },
            "compliance": {"enabled": False, "review_model": "vlm", "timeout_ms": 60000},
        }
    )
    instance._set_context(SimpleNamespace(logger=Mock()))
    return instance


@pytest.mark.parametrize("activity", ["stdout", "session", "image"])
def test_active_job_survives_original_timeout(tmp_path: Path, activity: str) -> None:
    """事件、wait 会话记录或分段图片写入应分别支持超过原总时长上限。"""
    _exercise_waiting_process(tmp_path, activity, expect_timeout=False)


@pytest.mark.parametrize("activity", ["stdout", "session", "image"])
def test_active_job_is_killed_at_hard_deadline(tmp_path: Path, activity: str) -> None:
    """持续事件、会话记录和分段图片写入均不得延长总时长上限。"""
    with patch.object(plugin, "_MAX_JOB_DURATION_SECONDS", 1.0):
        _exercise_waiting_process(tmp_path, activity, expect_timeout=False, hard_timeout=True)


@pytest.mark.parametrize(
    "activity", ["silent", "no-thread", "noise", "stalled-session", "session-then-stall", "other-session"]
)
def test_inactive_job_times_out(tmp_path: Path, activity: str) -> None:
    """活进程、噪声、停止更新的记录和其他会话的活动均不能无限续期。"""
    _exercise_waiting_process(tmp_path, activity, expect_timeout=True)


def test_waiting_job_can_be_cancelled(tmp_path: Path) -> None:
    """长任务取消时应释放进程和管道。"""
    _exercise_waiting_process(tmp_path, "session", expect_timeout=False, cancel=True)


def test_failed_process_reports_original_error(tmp_path: Path) -> None:
    """子进程失败应立即暴露真实错误，不进入持续等待。"""
    _exercise_waiting_process(tmp_path, "failed", expect_timeout=False)


@pytest.mark.skipif(sys.platform != "linux", reason="通过 /proc 检查派生进程是否仍在运行")
@pytest.mark.parametrize("exit_code", [0, 7])
@pytest.mark.parametrize("inherit_pipes", [False, True])
def test_exited_process_cleans_up_children(tmp_path: Path, exit_code: int, inherit_pipes: bool) -> None:
    """主进程退出后，应清理忽略 SIGTERM 的子进程，同时保留图片或原始错误。"""
    instance = _make_plugin(tmp_path / "images")
    real_create = asyncio.create_subprocess_exec
    processes: List[asyncio.subprocess.Process] = []
    child_pid_path = tmp_path / "child.pid"
    child_code = (
        "from pathlib import Path\n"
        "import os, signal, sys, time\n"
        "signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
        "Path(sys.argv[1]).write_text(str(os.getpid()))\n"
        "time.sleep(30)\n"
    )
    helper_code = (
        "from pathlib import Path\n"
        "import base64, json, subprocess, sys, time\n"
        "root = Path(sys.argv[1])\n"
        "exit_code = int(sys.argv[2])\n"
        "sys.stdin.read()\n"
        "thread = 'exited-test-thread'\n"
        "print(json.dumps({'type': 'thread.started', 'thread_id': thread}), flush=True)\n"
        "output = None if sys.argv[3] == 'True' else subprocess.DEVNULL\n"
        f"subprocess.Popen([sys.executable, '-c', {child_code!r}, str(root / 'child.pid')], "
        "stdin=subprocess.DEVNULL, stdout=output, stderr=output)\n"
        "while not (root / 'child.pid').exists(): time.sleep(0.01)\n"
        "if exit_code == 0:\n"
        "    image_dir = root / 'images' / thread\n"
        "    image_dir.mkdir(parents=True)\n"
        f"    (image_dir / 'result.png').write_bytes(base64.b64decode({_TINY_PNG_B64!r}))\n"
        "else:\n"
        "    print('specific-render-failure', file=sys.stderr, flush=True)\n"
        "sys.exit(exit_code)\n"
    )

    async def fake_create(*args: Any, **kwargs: Any) -> asyncio.subprocess.Process:
        del args
        proc = await real_create(
            sys.executable, "-c", helper_code, str(tmp_path), str(exit_code), str(inherit_pipes), **kwargs
        )
        processes.append(proc)
        return proc

    async def execute() -> None:
        try:
            with patch.object(plugin.asyncio, "create_subprocess_exec", new=fake_create):
                if exit_code:
                    with pytest.raises(RuntimeError, match="specific-render-failure"):
                        await asyncio.wait_for(instance._run_codex("画一只猫", None), 5)
                else:
                    result = await asyncio.wait_for(instance._run_codex("画一只猫", None), 5)
                    assert result == (base64.b64decode(_TINY_PNG_B64), "image/png")

            assert processes[0].returncode == exit_code
            # 被终止的孤儿进程可能短暂处于僵尸态，不能只用 kill(pid, 0) 判断存活。
            child_pid = int(child_pid_path.read_text())
            child_stat = Path(f"/proc/{child_pid}/stat")
            deadline = asyncio.get_running_loop().time() + 1
            while True:
                try:
                    state = child_stat.read_text().rsplit(")", 1)[1].split()[0]
                except FileNotFoundError:
                    break
                if state == "Z":
                    break
                assert asyncio.get_running_loop().time() < deadline, "主进程退出后子进程仍在运行"
                await asyncio.sleep(0.01)
        finally:
            # 即使回归断言失败，也不能让测试留下后台进程。
            for proc in processes:
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                await proc.wait()

    asyncio.run(execute())


def _exercise_waiting_process(
    tmp_path: Path, activity: str, *, expect_timeout: bool, cancel: bool = False, hard_timeout: bool = False
) -> None:
    instance = _make_plugin(tmp_path / "images")
    # 仅在测试中缩短时间尺度，生产配置仍维持至少 10 秒的校验。
    instance.config.codex = instance.config.codex.model_copy(update={"timeout_seconds": 0.8})
    real_create = asyncio.create_subprocess_exec
    processes: List[asyncio.subprocess.Process] = []
    helper_code = (
        "from pathlib import Path\n"
        "import base64, json, os, sys, time\n"
        "root = Path(sys.argv[1])\n"
        "mode = sys.argv[2]\n"
        "sys.stdin.read()\n"
        "if mode == 'no-thread': time.sleep(30)\n"
        "thread = 'waiting-test-thread'\n"
        "# 故意拆分首个 JSON 事件，验证管道分块解析。\n"
        "event = json.dumps({'type': 'thread.started', 'thread_id': thread}) + '\\n'\n"
        "sys.stdout.write(event[:12]); sys.stdout.flush(); time.sleep(0.02)\n"
        "sys.stdout.write(event[12:]); sys.stdout.flush()\n"
        "if mode == 'failed':\n"
        "    print('specific-render-failure', file=sys.stderr, flush=True)\n"
        "    sys.exit(7)\n"
        "session = root / 'sessions' / '2026' / '09' / '15'\n"
        "session.mkdir(parents=True)\n"
        "record_thread = 'other-thread' if mode == 'other-session' else thread\n"
        "record = session / ('rollout-test-' + record_thread + '.jsonl')\n"
        "image_dir = root / 'images' / thread\n"
        "image_dir.mkdir(parents=True)\n"
        f"content = base64.b64decode({_TINY_PNG_B64!r})\n"
        "if mode == 'stalled-session': record.write_text('{}\\n')\n"
        "for index in range(5):\n"
        "    if mode == 'stdout':\n"
        "        print(json.dumps({'type': 'item.completed', 'item': {'id': str(index), 'type': 'agent_message', 'text': '等待生成'}}), flush=True)\n"
        "    elif mode in ('session', 'session-then-stall', 'other-session'):\n"
        "        with record.open('a') as log:\n"
        "            log.write(json.dumps({'type': 'response_item', 'payload': {'type': 'function_call_output', 'output': 'Script running with cell ID 1'}}) + '\\n')\n"
        "    elif mode == 'image':\n"
        "        (image_dir / 'result.png').write_bytes(content[:12 + index * 8])\n"
        "    elif mode == 'noise':\n"
        "        print('ordinary output\\n[]\\n{broken json', flush=True)\n"
        "        print(json.dumps({'type': 'error', 'message': 'retrying'}), flush=True)\n"
        "        print('still alive', file=sys.stderr, flush=True)\n"
        "    time.sleep(0.3)\n"
        "if mode == 'session-then-stall': time.sleep(30)\n"
        "(image_dir / 'result.png').write_bytes(content)\n"
        "time.sleep(30)\n"
    )

    async def fake_create(*args: Any, **kwargs: Any) -> asyncio.subprocess.Process:
        del args
        proc = await real_create(sys.executable, "-c", helper_code, str(tmp_path), activity, **kwargs)
        processes.append(proc)
        return proc

    async def execute() -> None:
        with (
            patch.dict(os.environ, {"CODEX_HOME": str(tmp_path)}),
            patch.object(plugin.asyncio, "create_subprocess_exec", new=fake_create),
            patch.object(plugin, "_IMAGE_POLL_INTERVAL_SECONDS", 0.02),
            patch.object(plugin, "_PROGRESS_POLL_INTERVAL_SECONDS", 0.05),
        ):
            task = asyncio.create_task(instance._run_codex("复杂绘图", None))
            if cancel:
                await asyncio.sleep(0.4)
                task.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await task
            elif hard_timeout:
                with pytest.raises(asyncio.TimeoutError, match="达到总时长上限.*已终止进程组"):
                    await asyncio.wait_for(task, 5)
            elif expect_timeout:
                with pytest.raises(asyncio.TimeoutError, match="连续 0.8 秒无活动"):
                    await asyncio.wait_for(task, 5)
            elif activity == "failed":
                with pytest.raises(RuntimeError, match="specific-render-failure"):
                    await asyncio.wait_for(task, 5)
            else:
                result = await asyncio.wait_for(task, 5)
                assert result == (base64.b64decode(_TINY_PNG_B64), "image/png")

    started_at = time.monotonic()
    asyncio.run(execute())
    if hard_timeout:
        assert any("总时长超限" in call.args for call in instance.ctx.logger.info.call_args_list)
        assert processes[0].returncode < 0
        image_path = tmp_path / "images" / "waiting-test-thread" / "result.png"
        assert instance._read_complete_image(image_path) is None
    if not (expect_timeout or cancel or hard_timeout or activity == "failed"):
        assert time.monotonic() - started_at > 0.8
        assert any("继续轮询等待" in call.args[0] for call in instance.ctx.logger.info.call_args_list)
    assert processes and processes[0].returncode is not None


def test_complete_image_validation(tmp_path: Path) -> None:
    instance = _make_plugin(tmp_path)
    image_content = base64.b64decode(_TINY_PNG_B64)

    complete_path = tmp_path / "complete.png"
    complete_path.write_bytes(image_content)
    assert instance._read_complete_image(complete_path) == (image_content, "image/png")

    incomplete_path = tmp_path / "incomplete.png"
    incomplete_path.write_bytes(image_content[:-4])
    assert instance._read_complete_image(incomplete_path) is None


def test_run_codex_returns_image_before_agent_exit(tmp_path: Path) -> None:
    """图片落盘后应立即返回，并终止仍在执行后续工作的 Codex 进程。"""
    instance = _make_plugin(tmp_path)
    image_content = base64.b64decode(_TINY_PNG_B64)
    process_holder: Dict[str, Any] = {}
    real_create_subprocess_exec = asyncio.create_subprocess_exec
    helper_code = (
        "from pathlib import Path\n"
        "import base64, json, sys, time\n"
        "output_dir = Path(sys.argv[1])\n"
        "(output_dir / 'received_prompt.txt').write_text(sys.stdin.read(), encoding='utf-8')\n"
        "thread_id = 'streaming-test-thread'\n"
        "print(json.dumps({'type': 'thread.started', 'thread_id': thread_id}), flush=True)\n"
        "image_dir = output_dir / thread_id\n"
        "image_dir.mkdir(parents=True, exist_ok=True)\n"
        f"(image_dir / 'result.png').write_bytes(base64.b64decode({_TINY_PNG_B64!r}))\n"
        "time.sleep(30)\n"
    )

    async def fake_create_subprocess_exec(*args: Any, **kwargs: Any) -> asyncio.subprocess.Process:
        assert args[args.index("--config") + 1] == 'model_reasoning_effort="medium"'
        proc = await real_create_subprocess_exec(
            sys.executable,
            "-c",
            helper_code,
            str(tmp_path),
            stdout=kwargs["stdout"],
            stderr=kwargs["stderr"],
            stdin=kwargs["stdin"],
            cwd=kwargs["cwd"],
            env=kwargs["env"],
            start_new_session=kwargs["start_new_session"],
        )
        process_holder["proc"] = proc
        return proc

    async def execute() -> tuple[bytes, str]:
        with patch.object(plugin.asyncio, "create_subprocess_exec", new=fake_create_subprocess_exec):
            return await instance._run_codex("画一只猫", None)

    started_at = time.monotonic()
    result = asyncio.run(execute())
    elapsed = time.monotonic() - started_at

    assert result == (image_content, "image/png")
    assert elapsed < 5
    assert process_holder["proc"].returncode is not None
    received_prompt = (tmp_path / "received_prompt.txt").read_text(encoding="utf-8")
    assert received_prompt.startswith("$imagegen\n")
    assert "画一只猫" in received_prompt


def test_draw_job_sends_generated_image(tmp_path: Path) -> None:
    """审核通过后应先提示绘制中，再把生成的图片发送到原聊天流。"""
    instance = _make_plugin(tmp_path)
    image_content = base64.b64decode(_TINY_PNG_B64)
    sent_messages: List[str] = []
    sent_images: List[Dict[str, str]] = []

    async def send_text(text: str, stream_id: str) -> bool:
        assert stream_id == "stream-1"
        sent_messages.append(text)
        return True

    async def send_image(image_data: str, stream_id: str) -> bool:
        sent_images.append({"image_data": image_data, "stream_id": stream_id})
        return True

    async def fake_run_codex(prompt: str, ref: plugin.ReferenceImage | None) -> tuple[bytes, str]:
        del prompt, ref
        return image_content, "image/png"

    context = SimpleNamespace(
        send=SimpleNamespace(image=send_image, text=send_text),
        logger=SimpleNamespace(error=lambda *args, **kwargs: None),
    )
    instance._set_context(context)

    async def execute() -> None:
        with patch.object(instance, "_run_codex", new=fake_run_codex):
            await instance._run_draw_job("stream-1", "画一只猫", None)

    asyncio.run(execute())

    assert sent_messages == ["GPT-image2绘制中"]
    assert len(sent_images) == 1
    assert sent_images[0]["stream_id"] == "stream-1"
    assert base64.b64decode(sent_images[0]["image_data"]) == image_content


def test_draw_job_silently_rejects_noncompliant_prompt(tmp_path: Path) -> None:
    """审核拒绝时不应发送文字或图片，也不应启动 Codex。"""
    instance = _make_plugin(tmp_path)
    sent_messages: List[str] = []
    sent_images: List[str] = []
    codex_called = False

    async def send_text(text: str, stream_id: str) -> bool:
        del stream_id
        sent_messages.append(text)
        return True

    async def send_image(image_data: str, stream_id: str) -> bool:
        del stream_id
        sent_images.append(image_data)
        return True

    async def reject_prompt(prompt: str, ref: plugin.ReferenceImage | None) -> None:
        del prompt, ref
        raise plugin.ComplianceRejected("内容不合规")

    async def fake_run_codex(prompt: str, ref: plugin.ReferenceImage | None) -> tuple[bytes, str]:
        nonlocal codex_called
        del prompt, ref
        codex_called = True
        return b"", "image/png"

    context = SimpleNamespace(
        send=SimpleNamespace(image=send_image, text=send_text),
        logger=SimpleNamespace(error=lambda *args, **kwargs: None),
    )
    instance._set_context(context)

    async def execute() -> None:
        with (
            patch.object(instance, "_compliance_check", new=reject_prompt),
            patch.object(instance, "_run_codex", new=fake_run_codex),
        ):
            await instance._run_draw_job("stream-1", "违规提示词", None)

    asyncio.run(execute())

    assert sent_messages == []
    assert sent_images == []
    assert codex_called is False


def test_spawn_draw_job_drops_request_when_concurrency_is_full(tmp_path: Path) -> None:
    """并发已满时不创建等待任务；已有任务结束后应立即恢复受理。"""
    instance = _make_plugin(tmp_path, max_concurrent_jobs=2)
    started_prompts: List[str] = []

    async def execute() -> None:
        release_jobs = asyncio.Event()

        async def fake_run_draw_job(
            stream_id: str,
            prompt: str,
            ref: plugin.ReferenceImage | None,
        ) -> None:
            del stream_id, ref
            started_prompts.append(prompt)
            await release_jobs.wait()

        with patch.object(instance, "_run_draw_job", new=fake_run_draw_job):
            assert instance._spawn_draw_job("stream-1", "任务一", None) is True
            assert instance._spawn_draw_job("stream-2", "任务二", None) is True
            assert instance._spawn_draw_job("stream-3", "不会排队", None) is False
            await asyncio.sleep(0)

            assert started_prompts == ["任务一", "任务二"]
            assert len(instance._background_tasks) == 2

            release_jobs.set()
            await asyncio.gather(*list(instance._background_tasks))
            await asyncio.sleep(0)
            assert not instance._background_tasks

            assert instance._spawn_draw_job("stream-4", "任务四", None) is True
            await asyncio.gather(*list(instance._background_tasks))

    asyncio.run(execute())
