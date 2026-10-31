#!/usr/bin/env python3
from __future__ import annotations

import argparse
import getpass
import hashlib
import ipaddress
import json
import os
import platform
import pwd
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from contextlib import contextmanager
from pathlib import Path, PurePosixPath


PACKAGE_ROOT = Path(__file__).resolve().parent.parent
STATE_FILE = Path(
    os.environ.get("QQBRIDGE_STATE_FILE", "/var/lib/qqbridge/install-state.json")
)
DOCKER_INSTALL_URL = "https://get.docker.com"
QQ_RE = re.compile(r"^\d{5,12}$")
BACKUP_ID_RE = re.compile(r"^[0-9TZ-]+$")


def log(message: str) -> None:
    print(f"[QQBridge] {message}", flush=True)


def warn(message: str) -> None:
    print(f"[QQBridge] WARNING: {message}", file=sys.stderr, flush=True)


def fail(message: str) -> None:
    print(f"[QQBridge] ERROR: {message}", file=sys.stderr, flush=True)
    raise SystemExit(1)


def run(
    command: list[str],
    *,
    check: bool = True,
    capture: bool = True,
    cwd: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        command,
        cwd=cwd,
        text=True,
        errors="replace",
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.STDOUT if capture else None,
    )
    if check and result.returncode != 0:
        output = (result.stdout or "").strip()
        suffix = f"\n{output}" if output else ""
        fail(f"command failed ({result.returncode}): {' '.join(command)}{suffix}")
    return result


def ensure_linux() -> None:
    if platform.system() != "Linux":
        fail("native Linux entrypoints require Linux")
    if platform.machine().lower() not in {"x86_64", "amd64"}:
        fail("only Linux x86_64 is supported")
    if sys.version_info < (3, 10):
        fail("Python 3.10 or newer is required")


def elevate_if_needed(args: argparse.Namespace) -> None:
    if os.geteuid() == 0:
        return
    sudo = shutil.which("sudo")
    if not sudo:
        fail("this operation needs root privileges and sudo is not installed")
    command = [sudo, sys.executable, str(Path(__file__).resolve())] + sys.argv[1:]
    if getattr(args, "target_user", None):
        log(f"requesting sudo for target user {args.target_user}")
    os.execvp(sudo, command)


def target_user_name(requested: str | None) -> str:
    if requested:
        name = requested
    elif os.environ.get("SUDO_USER"):
        name = os.environ["SUDO_USER"]
    elif os.geteuid() == 0:
        name = "root"
    else:
        name = pwd.getpwuid(os.getuid()).pw_name
    try:
        pwd.getpwnam(name)
    except KeyError:
        fail(f"target user does not exist: {name}")
    return name


def target_home(user: str) -> Path:
    return Path(pwd.getpwnam(user).pw_dir)


def resolve_install_root(value: str | None, user: str) -> Path:
    home = target_home(user)
    if not value:
        return home / "qqbridge"
    if value == "~":
        return home
    if value.startswith("~/"):
        return home / value[2:]
    path = Path(value)
    if not path.is_absolute():
        fail("install root must be an absolute path or start with ~/")
    return path


def read_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] == "'":
            value = value[1:-1]
        values[key.strip()] = value
    return values


def load_state() -> dict[str, object]:
    if not STATE_FILE.is_file():
        fail(f"installation state not found: {STATE_FILE}")
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        fail(f"cannot read installation state: {exc}")


def save_state(state: dict[str, object]) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(STATE_FILE.parent, 0o700)
    temporary = STATE_FILE.with_name(
        f".{STATE_FILE.name}.{os.getpid()}.{os.urandom(4).hex()}"
    )
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(state, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(temporary, STATE_FILE)
        os.chmod(STATE_FILE, 0o600)
    finally:
        temporary.unlink(missing_ok=True)


def context_from_state() -> dict[str, object]:
    state = load_state()
    for key in ("install_root", "target_user"):
        if not state.get(key):
            fail(f"installation state is missing {key}")
    root = Path(str(state["install_root"]))
    if not root.is_absolute() or not root.is_dir():
        fail(f"install root is unavailable: {root}")
    return state


def current_release(install_root: Path) -> Path:
    current = install_root / "current"
    if not current.exists():
        fail(f"current release is missing: {current}")
    release = current.resolve()
    if not (release / "manifest.json").is_file():
        fail(f"current release is invalid: {release}")
    return release


def package_version(root: Path) -> str:
    value = (root / "VERSION").read_text(encoding="utf-8").strip()
    if not re.fullmatch(r"\d+\.\d+\.\d+", value):
        fail(f"invalid package version: {value}")
    return value


def version_tuple(value: str) -> tuple[int, int, int]:
    if not re.fullmatch(r"\d+\.\d+\.\d+", value):
        fail(f"invalid version: {value}")
    return tuple(int(part) for part in value.split("."))  # type: ignore[return-value]


def verify_package(root: Path) -> None:
    verifier = root / "wsl" / "package_verify.py"
    if not verifier.is_file():
        fail(f"package verifier is missing: {verifier}")
    result = run([sys.executable, str(verifier), "--root", str(root)], capture=False)
    if result.returncode != 0:
        fail("package integrity verification failed")


def ask(
    label: str,
    *,
    default: str = "",
    required: bool = False,
    secret: bool = False,
) -> str:
    prompt = f"{label}"
    if default:
        prompt += f" [{default}]"
    prompt += ": "
    while True:
        value = getpass.getpass(prompt) if secret else input(prompt)
        value = value.strip()
        if not value and default:
            value = default
        if value or not required:
            if any(ord(char) < 32 for char in value):
                warn("输入包含控制字符，请重新输入。")
                continue
            return value
        warn("此项不能为空。")


def ask_choice(label: str, choices: set[str], default: str) -> str:
    while True:
        value = ask(label, default=default).lower()
        if value in choices:
            return value
        warn(f"可选值：{', '.join(sorted(choices))}")


def ask_port(
    label: str,
    default: int,
    bind_address: str,
    *,
    current: int | None = None,
) -> int:
    while True:
        raw = ask(label, default=str(default))
        try:
            value = int(raw)
        except ValueError:
            warn("端口必须是整数。")
            continue
        if not 1024 <= value <= 65535:
            warn("端口必须在 1024-65535 之间。")
            continue
        if value != current and not port_available(value, bind_address):
            warn(f"端口 {value} 已被占用或当前不可绑定。")
            continue
        return value


def port_available(port: int, bind_address: str) -> bool:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind((bind_address, port))
        return True
    except OSError:
        return False
    finally:
        sock.close()


@contextmanager
def answers_file(answers: dict[str, object]):
    descriptor, name = tempfile.mkstemp(prefix="qqbridge-answers-", suffix=".json")
    os.fchmod(descriptor, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(answers, handle, ensure_ascii=False)
        yield Path(name)
    finally:
        Path(name).unlink(missing_ok=True)


def distro_name() -> str:
    release = Path("/etc/os-release")
    if not release.is_file():
        return "Linux"
    values: dict[str, str] = {}
    for line in release.read_text(encoding="utf-8", errors="replace").splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            values[key] = value.strip().strip('"')
    return values.get("PRETTY_NAME") or values.get("NAME") or "Linux"


def ensure_docker_installed() -> None:
    if not shutil.which("docker"):
        print()
        warn("Docker Engine 未安装。")
        confirmation = ask(
            "使用 Docker 官方 get.docker.com 脚本安装 Docker Engine？[Y/n]",
            default="Y",
        ).lower()
        if confirmation not in {"y", "yes", "是"}:
            fail("请先安装 Docker Engine 和 Docker Compose 插件后重试。")
        with tempfile.NamedTemporaryFile(
            prefix="qqbridge-docker-install-", suffix=".sh", delete=False
        ) as handle:
            installer = Path(handle.name)
        try:
            log("downloading Docker official installation script")
            with urllib.request.urlopen(DOCKER_INSTALL_URL, timeout=60) as response:
                installer.write_bytes(response.read())
            os.chmod(installer, 0o700)
            run(["/bin/sh", str(installer)], capture=False)
        except OSError as exc:
            fail(f"cannot install Docker Engine: {exc}")
        finally:
            installer.unlink(missing_ok=True)

    systemctl = shutil.which("systemctl")
    if systemctl:
        run([systemctl, "enable", "--now", "docker"], check=False)
    elif shutil.which("service"):
        run([shutil.which("service") or "service", "docker", "start"], check=False)

    compose_probe = run(["docker", "compose", "version"], check=False)
    if compose_probe.returncode != 0:
        fail("Docker Compose v2 plugin is missing; install docker-compose-plugin")

    started = False
    for _ in range(30):
        if run(["docker", "info"], check=False).returncode == 0:
            started = True
            break
        import time

        time.sleep(2)
    if not started:
        fail("Docker daemon is not reachable after startup")


def ensure_docker_access(user: str) -> None:
    if user == "root":
        return
    group = run(["getent", "group", "docker"], check=False)
    if group.returncode != 0:
        run(["groupadd", "docker"], check=False)
    run(["usermod", "-aG", "docker", user])
    check = as_user(user, ["docker", "info"])
    if check.returncode != 0:
        fail(
            f"target user {user} cannot access Docker after joining the docker group; "
            "log out and back in, then rerun the installer"
        )


def as_user(user: str, command: list[str], *, capture: bool = True) -> subprocess.CompletedProcess[str]:
    if os.geteuid() != 0 or user == "root":
        return run(command, check=False, capture=capture)
    return run(["runuser", "-u", user, "--"] + command, check=False, capture=capture)


def detect_lan_ip(explicit: str | None) -> str:
    if explicit:
        try:
            address = ipaddress.ip_address(explicit)
        except ValueError:
            fail(f"invalid IPv4 address: {explicit}")
        if address.version != 4 or address.is_loopback or address.is_unspecified:
            fail("LAN bind address must be a non-loopback IPv4 address")
        return str(address)
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("1.1.1.1", 80))
        address = sock.getsockname()[0]
    except OSError:
        address = ""
    finally:
        sock.close()
    if not address:
        try:
            address = socket.gethostbyname(socket.gethostname())
        except OSError:
            address = ""
    try:
        parsed = ipaddress.ip_address(address)
    except ValueError:
        fail("cannot detect a LAN IPv4 address; pass --lan-bind-ip")
    if parsed.is_loopback or parsed.is_unspecified:
        fail("cannot detect a LAN IPv4 address; pass --lan-bind-ip")
    return str(parsed)


def detect_lan_cidrs(explicit: list[str] | None) -> list[str]:
    if explicit:
        result = []
        for value in explicit:
            try:
                result.append(str(ipaddress.ip_network(value, strict=False)))
            except ValueError:
                fail(f"invalid LAN CIDR: {value}")
        return sorted(set(result))
    result = []
    ip_command = shutil.which("ip")
    if not ip_command:
        return result
    output = run([ip_command, "-o", "-4", "addr", "show", "scope", "global"], check=False)
    for line in (output.stdout or "").splitlines():
        match = re.search(r"^\d+:\s+(\S+)\s+inet\s+([0-9.]+/\d+)", line)
        if not match:
            continue
        interface, cidr = match.groups()
        if interface == "lo" or interface.startswith(("docker", "br-", "veth")):
            continue
        try:
            network = ipaddress.ip_interface(cidr).network
        except ValueError:
            continue
        if not network.is_loopback:
            result.append(str(network))
    return sorted(set(result))


def firewall_backend() -> str | None:
    if shutil.which("ufw"):
        status = run(["ufw", "status"], check=False)
        if "Status: active" in (status.stdout or ""):
            return "ufw"
    if shutil.which("firewall-cmd"):
        status = run(["firewall-cmd", "--state"], check=False)
        if (status.stdout or "").strip() == "running":
            return "firewalld"
    return None


def remove_firewall_rules(rules: list[dict[str, object]]) -> None:
    for rule in rules:
        backend = rule.get("backend")
        spec = rule.get("spec")
        if not isinstance(spec, list):
            continue
        if backend == "ufw" and shutil.which("ufw"):
            run(["ufw", "delete"] + [str(value) for value in spec], check=False)
        elif backend == "firewalld" and shutil.which("firewall-cmd"):
            rich_rule = str(rule.get("rich_rule", ""))
            if rich_rule:
                run(
                    ["firewall-cmd", "--permanent", f"--remove-rich-rule={rich_rule}"],
                    check=False,
                )
                run(
                    ["firewall-cmd", f"--remove-rich-rule={rich_rule}"],
                    check=False,
                )
    if shutil.which("firewall-cmd"):
        run(["firewall-cmd", "--reload"], check=False)


def apply_firewall_rules(
    bind_ip: str,
    cidrs: list[str],
    ports: list[int],
    previous_rules: list[dict[str, object]],
) -> list[dict[str, object]]:
    remove_firewall_rules(previous_rules)
    backend = firewall_backend()
    if not backend:
        warn(
            f"未检测到活动 UFW/firewalld；端口只绑定到 {bind_ip}，"
            "请在上游路由器或主机防火墙继续限制来源网段。"
        )
        return []
    if not cidrs:
        warn("未检测到局域网 CIDR；未添加来源网段防火墙规则。")
        return []

    added: list[dict[str, object]] = []
    try:
        for cidr in cidrs:
            for port in ports:
                if backend == "ufw":
                    spec = [
                        "allow",
                        "from",
                        cidr,
                        "to",
                        "any",
                        "port",
                        str(port),
                        "proto",
                        "tcp",
                    ]
                    run(["ufw"] + spec)
                    added.append({"backend": backend, "spec": spec})
                else:
                    rich = (
                        'rule family="ipv4" '
                        f'source address="{cidr}" port port="{port}" '
                        'protocol="tcp" accept'
                    )
                    run(["firewall-cmd", "--permanent", f"--add-rich-rule={rich}"])
                    run(["firewall-cmd", f"--add-rich-rule={rich}"])
                    added.append(
                        {"backend": backend, "rich_rule": rich, "spec": [rich]}
                    )
        if backend == "firewalld":
            run(["firewall-cmd", "--reload"])
    except SystemExit:
        warn("部分防火墙规则添加失败，正在撤销本次新增规则。")
        remove_firewall_rules(added)
        return []
    log(f"已添加 {len(added)} 条仅限局域网来源的防火墙规则。")
    return added


def prompt_core_answers(
    *,
    bind_address: str,
    default_ports: tuple[int, int, int] | None = None,
) -> dict[str, object]:
    print()
    print("配置主聊天模型")
    base_url = ask(
        "OpenAI 兼容 Base URL",
        default="https://api.openai.com/v1",
        required=True,
    )
    model = ask("模型标识（例如 gpt-4.1-mini / deepseek-chat）", required=True)
    api_key = ask("API Key（输入不会回显）", required=True, secret=True)
    print("客户端类型：1) openai  2) openai_responses  3) gemini")
    client = ask_choice("选择", {"1", "2", "3"}, "1")
    client_type = {
        "1": "openai",
        "2": "openai_responses",
        "3": "gemini",
    }[client]
    owner = ask("管理员/群主 QQ（可留空）")
    while owner and not QQ_RE.fullmatch(owner):
        warn("QQ 号格式无效。")
        owner = ask("管理员/群主 QQ（可留空）")
    owner_name = ask("群主称呼", default="群主", required=True)
    bot = ask("机器人 QQ（登录后也可再填，可留空）")
    while bot and not QQ_RE.fullmatch(bot):
        warn("QQ 号格式无效。")
        bot = ask("机器人 QQ（登录后也可再填，可留空）")
    timezone = ask(
        "时区",
        default=(
            Path("/etc/timezone").read_text(encoding="utf-8").strip()
            if Path("/etc/timezone").is_file()
            else "Asia/Shanghai"
        ),
        required=True,
    )
    ports = default_ports or (18001, 6099, 3001)
    mai_port = ask_port("MaiBot WebUI 端口", ports[0], bind_address)
    nap_port = ask_port("NapCat WebUI 端口", ports[1], bind_address)
    while nap_port == mai_port:
        warn("NapCat 与 MaiBot 端口不能相同。")
        nap_port = ask_port("NapCat WebUI 端口", ports[1], bind_address)
    one_port = ask_port("OneBot 本机端口", ports[2], "127.0.0.1")
    while one_port in {mai_port, nap_port}:
        warn("OneBot 端口不能与 WebUI 端口相同。")
        one_port = ask_port("OneBot 本机端口", ports[2], "127.0.0.1")
    return {
        "llm_base_url": base_url,
        "llm_api_key": api_key,
        "llm_model": model,
        "llm_client_type": client_type,
        "owner_qq": owner,
        "owner_name": owner_name,
        "bot_qq": bot,
        "maibot_port": mai_port,
        "napcat_port": nap_port,
        "onebot_port": one_port,
        "maibot_bind": bind_address,
        "napcat_bind": bind_address,
        "timezone": timezone,
        "allowed_groups": [],
        "allowed_users": [owner] if owner else [],
    }


def command_install(args: argparse.Namespace) -> None:
    verify_package(PACKAGE_ROOT)
    log(f"Linux: {distro_name()} ({platform.machine()})")
    if args.local_only and args.lan:
        fail("--local-only and --lan cannot be used together")
    user = target_user_name(args.target_user)
    install_root = resolve_install_root(args.install_root, user)
    if install_root.exists() and any(install_root.iterdir()):
        fail(f"install root is not empty: {install_root}")
    if args.install_root is None:
        default = str(target_home(user) / "qqbridge")
    else:
        default = str(install_root)
    install_root = resolve_install_root(
        ask("安装目录", default=default, required=True), user
    )
    if install_root.exists() and any(install_root.iterdir()):
        fail(f"install root is not empty: {install_root}")

    ensure_docker_installed()
    ensure_docker_access(user)

    local_only = not args.lan
    bind_address = "127.0.0.1"
    lan_cidrs: list[str] = []
    if not local_only:
        bind_address = detect_lan_ip(args.lan_bind_ip)
        lan_cidrs = detect_lan_cidrs(args.lan_cidr)
        log(f"LAN 绑定地址：{bind_address}")
        log(f"LAN 来源网段：{', '.join(lan_cidrs) if lan_cidrs else '未检测到'}")

    answers = prompt_core_answers(bind_address=bind_address)
    answers["restart_policy"] = "no" if args.disable_autostart else "unless-stopped"
    answers["compose_project_name"] = os.environ.get(
        "QQBRIDGE_COMPOSE_PROJECT_NAME", "qqbridge"
    )
    for env_name, answer_name in (
        ("QQBRIDGE_MAIBOT_MEMORY_LIMIT", "maibot_memory_limit"),
        ("QQBRIDGE_NAPCAT_MEMORY_LIMIT", "napcat_memory_limit"),
    ):
        if os.environ.get(env_name):
            answers[answer_name] = os.environ[env_name]

    user_record = pwd.getpwnam(user)
    with answers_file(answers) as answer_path:
        run(
            [
                "bash",
                str(PACKAGE_ROOT / "wsl" / "install.sh"),
                "--package",
                str(PACKAGE_ROOT),
                "--install-root",
                str(install_root),
                "--answers",
                str(answer_path),
                "--target-user",
                user,
                "--napcat-uid",
                str(user_record.pw_uid),
                "--napcat-gid",
                str(user_record.pw_gid),
                "--platform",
                "linux",
            ],
            capture=False,
        )

    firewall_rules: list[dict[str, object]] = []
    if not local_only:
        firewall_rules = apply_firewall_rules(
            bind_address,
            lan_cidrs,
            [int(answers["maibot_port"]), int(answers["napcat_port"])],
            [],
        )

    state = {
        "schema_version": 1,
        "platform": "linux",
        "package_version": package_version(PACKAGE_ROOT),
        "install_root": str(install_root),
        "target_user": user,
        "instance": "default",
        "local_only": local_only,
        "lan_bind_ip": "" if local_only else bind_address,
        "lan_cidrs": lan_cidrs,
        "maibot_port": answers["maibot_port"],
        "napcat_port": answers["napcat_port"],
        "onebot_port": answers["onebot_port"],
        "firewall_rules": firewall_rules,
    }
    save_state(state)
    log("installation complete")
    print_urls(state)
    log("下一步：在 NapCat WebUI 扫码登录，然后运行 ./configure-linux.sh --discover-groups")


def print_urls(state: dict[str, object]) -> None:
    bind = "127.0.0.1" if state.get("local_only") else str(state.get("lan_bind_ip"))
    print(f"NapCat WebUI: http://{bind}:{state.get('napcat_port')}")
    print(f"MaiBot WebUI: http://{bind}:{state.get('maibot_port')}")


def prompt_basic_updates(
    env: dict[str, str],
    bind_address: str,
) -> dict[str, object]:
    answers: dict[str, object] = {}
    print()
    print("基础配置（直接回车表示保留）")
    print(
        f"当前模型: {env.get('LLM_MODEL', '')} @ "
        f"{env.get('LLM_BASE_URL', '')} ({env.get('LLM_CLIENT_TYPE', 'openai')})"
    )
    base = ask("新的 Base URL")
    if base:
        answers["llm_base_url"] = base
    model = ask("新的模型标识")
    if model:
        answers["llm_model"] = model
    print("客户端类型：1) openai  2) openai_responses  3) gemini  空) 保留")
    client = ask("选择")
    if client in {"1", "2", "3"}:
        answers["llm_client_type"] = {
            "1": "openai",
            "2": "openai_responses",
            "3": "gemini",
        }[client]
    new_key = ask("新的 API Key（回车保留，输入不会回显）", secret=True)
    if new_key:
        answers["llm_api_key"] = new_key

    print(f"群主 QQ: {'已设置' if env.get('OWNER_QQ') else '未设置'}")
    owner = ask("新的群主 QQ（输入 - 可清空）")
    if owner == "-":
        answers["owner_qq"] = ""
    elif owner:
        if not QQ_RE.fullmatch(owner):
            fail("QQ 号格式无效")
        answers["owner_qq"] = owner
    owner_name = ask("新的群主称呼")
    if owner_name:
        answers["owner_name"] = owner_name
    print(f"机器人 QQ: {'已设置' if env.get('BOT_QQ') else '未设置'}")
    bot = ask("新的机器人 QQ（输入 - 可清空）")
    if bot == "-":
        answers["bot_qq"] = ""
    elif bot:
        if not QQ_RE.fullmatch(bot):
            fail("QQ 号格式无效")
        answers["bot_qq"] = bot

    if ask("是否修改端口？[y/N]", default="N").lower() in {"y", "yes", "是"}:
        current = (
            int(env.get("MAIBOT_PORT", "18001")),
            int(env.get("NAPCAT_PORT", "6099")),
            int(env.get("ONEBOT_PORT", "3001")),
        )
        mai_port = ask_port(
            "MaiBot 端口", current[0], bind_address, current=current[0]
        )
        nap_port = ask_port(
            "NapCat 端口", current[1], bind_address, current=current[1]
        )
        while nap_port == mai_port:
            warn("NapCat 与 MaiBot 端口不能相同。")
            nap_port = ask_port(
                "NapCat 端口", current[1], bind_address, current=current[1]
            )
        one_port = ask_port(
            "OneBot 本机端口",
            current[2],
            "127.0.0.1",
            current=current[2],
        )
        while one_port in {mai_port, nap_port}:
            warn("OneBot 端口不能与 WebUI 端口相同。")
            one_port = ask_port(
                "OneBot 本机端口",
                current[2],
                "127.0.0.1",
                current=current[2],
            )
        answers.update(
            {
                "maibot_port": mai_port,
                "napcat_port": nap_port,
                "onebot_port": one_port,
            }
        )
    return answers


def prompt_advanced(answers: dict[str, object]) -> None:
    print()
    print("高级外部服务（直接回车表示跳过/保留）")
    search_base = ask("搜索服务 Base URL")
    search_model = ask("搜索服务模型")
    search_key = ask("搜索服务 API Key（不会回显）", secret=True)
    if search_base or search_model or search_key:
        if not (search_base and search_model and search_key):
            fail("启用搜索插件时，Base URL、模型和 API Key 必须同时填写")
        answers.update(
            {
                "search_base_url": search_base,
                "search_model": search_model,
                "search_api_key": search_key,
            }
        )
    tts_key = ask("小米 MiMo TTS API Key（留空跳过，不会回显）", secret=True)
    if tts_key:
        answers["tts_api_key"] = tts_key
        answers["tts_api_url"] = ask(
            "TTS API URL",
            default="https://api.xiaomimimo.com/v1/chat/completions",
        )
        answers["tts_model"] = ask("TTS 模型", default="mimo-v2.5-tts")
        answers["tts_voice"] = ask("默认音色", default="冰糖")
    codex_path = ask("Codex CLI 容器内绝对路径")
    if codex_path:
        answers["codex_path"] = codex_path
    proxy = ask("链接解析代理（例如 http://172.17.0.1:7890）")
    if proxy:
        answers["http_proxy"] = proxy
    for prompt, key in (
        ("知乎 Cookie", "zhihu_cookie"),
        ("YouTube Cookie", "youtube_cookie"),
        ("Pixiv Cookie", "pixiv_cookie"),
        ("抖音 Cookie", "douyin_cookie"),
        ("小红书 Cookie", "xhs_cookie"),
        ("Bilibili Cookie", "bilibili_cookie"),
        ("萌娘百科 Cookie", "moegirl_cookie"),
    ):
        value = ask(f"{prompt}（留空跳过）", secret=True)
        if value:
            answers[key] = value


def discover_groups(
    package: Path,
    instance: Path,
    env: dict[str, str],
) -> dict[str, object]:
    log("正在从 NapCat/OneBot 读取群列表；请确认机器人 QQ 已扫码登录。")
    result = run(
        [
            sys.executable,
            str(package / "wsl" / "onebot.py"),
            "--instance",
            str(instance),
            "--action",
            "get_group_list",
        ],
        check=False,
    )
    if result.returncode != 0:
        fail("读取群列表失败；请先在 NapCat WebUI 完成 QQ 登录")
    try:
        groups = json.loads((result.stdout or "").strip())
    except json.JSONDecodeError:
        fail("OneBot 返回了无法解析的群列表")
    if not isinstance(groups, list) or not groups:
        fail("机器人当前没有可用群列表")
    for index, group in enumerate(groups, start=1):
        print(f"{index:3}. {group.get('group_name', '')} ({group.get('group_id', '')})")
    selection = ask("输入允许的群序号（逗号分隔，或 all）", required=True)
    selected: list[str] = []
    if selection.lower() == "all":
        selected = [str(group["group_id"]) for group in groups]
    else:
        for item in selection.split(","):
            try:
                index = int(item.strip())
            except ValueError:
                fail(f"群序号无效: {item}")
            if index < 1 or index > len(groups):
                fail(f"群序号超出范围: {index}")
            selected.append(str(groups[index - 1]["group_id"]))
    owner = env.get("OWNER_QQ", "")
    private_text = ask(
        "允许私聊的 QQ（逗号分隔，可留空）",
        default=owner,
    )
    users = [value.strip() for value in private_text.split(",") if value.strip()]
    for qq in users:
        if not QQ_RE.fullmatch(qq):
            fail(f"QQ 号无效: {qq}")
    return {
        "allowed_groups": sorted(set(selected)),
        "allowed_users": sorted(set(users)),
    }


def command_configure(args: argparse.Namespace) -> None:
    state = context_from_state()
    if not re.fullmatch(r"[A-Za-z0-9_-]+", args.instance):
        fail("invalid instance name")
    install_root = Path(str(state["install_root"]))
    user = str(state["target_user"])
    instance = install_root / "instances" / args.instance
    env_path = instance / ".env"
    if not env_path.is_file():
        fail(f"instance not found: {instance}")
    package = current_release(install_root)
    verify_package(package)
    env = read_env(env_path)
    bind_address = env.get("MAIBOT_BIND", "127.0.0.1")
    answers = prompt_basic_updates(env, bind_address)
    if args.advanced:
        prompt_advanced(answers)
    if args.discover_groups:
        answers.update(discover_groups(package, instance, env))
    if not answers:
        log("没有需要修改的配置。")
        return

    with answers_file(answers) as answer_path:
        run(
            [
                "bash",
                str(package / "wsl" / "configure.sh"),
                "--package",
                str(package),
                "--install-root",
                str(install_root),
                "--answers",
                str(answer_path),
                "--target-user",
                user,
                "--instance",
                args.instance,
            ],
            capture=False,
        )

    old_mai = int(state.get("maibot_port", env.get("MAIBOT_PORT", "18001")))
    old_nap = int(state.get("napcat_port", env.get("NAPCAT_PORT", "6099")))
    new_mai = int(answers.get("maibot_port", old_mai))
    new_nap = int(answers.get("napcat_port", old_nap))
    if not state.get("local_only") and (new_mai != old_mai or new_nap != old_nap):
        previous_rules = state.get("firewall_rules", [])
        if not isinstance(previous_rules, list):
            previous_rules = []
        state["firewall_rules"] = apply_firewall_rules(
            str(state.get("lan_bind_ip", bind_address)),
            list(state.get("lan_cidrs", [])),
            [new_mai, new_nap],
            previous_rules,
        )
    state["maibot_port"] = new_mai
    state["napcat_port"] = new_nap
    state["onebot_port"] = int(
        answers.get("onebot_port", env.get("ONEBOT_PORT", "3001"))
    )
    save_state(state)
    log("配置已应用。")
    print_urls(state)


def command_verify(args: argparse.Namespace) -> None:
    state = context_from_state()
    if not re.fullmatch(r"[A-Za-z0-9_-]+", args.instance):
        fail("invalid instance name")
    install_root = Path(str(state["install_root"]))
    package = current_release(install_root)
    verify_package(package)
    result = run(
        [
            "bash",
            str(package / "wsl" / "verify.sh"),
            "--install-root",
            str(install_root),
            "--instance",
            args.instance,
            "--target-user",
            str(state["target_user"]),
        ],
        capture=False,
    )
    if result.returncode != 0:
        fail("verification failed")
    if not state.get("local_only"):
        backend = firewall_backend() or "none"
        log(f"LAN bind: {state.get('lan_bind_ip')} / firewall backend: {backend}")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_zip_digest(zip_path: Path) -> None:
    candidates = [
        Path(str(zip_path) + ".sha256"),
        zip_path.with_suffix(".sha256"),
    ]
    digest_file = next((path for path in candidates if path.is_file()), None)
    if digest_file is None:
        fail("upgrade ZIP requires a same-name .sha256 file")
    expected = digest_file.read_text(encoding="utf-8").strip().split()[0].lower()
    if not re.fullmatch(r"[0-9a-f]{64}", expected):
        fail(f"invalid SHA-256 file: {digest_file}")
    if sha256_file(zip_path) != expected:
        fail("upgrade ZIP SHA-256 verification failed")
    log("ZIP SHA-256 校验通过。")


def safe_extract_zip(zip_path: Path, destination: Path) -> None:
    total_size = 0
    seen: set[str] = set()
    with zipfile.ZipFile(zip_path) as archive:
        for info in archive.infolist():
            relative = PurePosixPath(info.filename)
            if relative.is_absolute() or ".." in relative.parts:
                fail(f"unsafe ZIP path: {info.filename}")
            normalized = relative.as_posix()
            if normalized in seen:
                fail(f"duplicate ZIP entry: {info.filename}")
            seen.add(normalized)
            if ((info.external_attr >> 16) & 0o170000) == 0o120000:
                fail(f"symbolic links are not allowed in upgrade ZIP: {info.filename}")
            total_size += info.file_size
            if total_size > 2 * 1024 * 1024 * 1024:
                fail("upgrade ZIP expands beyond the 2 GiB safety limit")
            target = destination.joinpath(*relative.parts)
            if info.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(info) as source, target.open("wb") as output:
                shutil.copyfileobj(source, output)


def package_root_from_extracted(directory: Path) -> Path:
    if (directory / "manifest.json").is_file():
        return directory
    children = [path for path in directory.iterdir() if path.is_dir()]
    if len(children) == 1 and (children[0] / "manifest.json").is_file():
        return children[0]
    fail("cannot identify the package root inside the upgrade ZIP")


def command_upgrade(args: argparse.Namespace) -> None:
    state = context_from_state()
    ensure_docker_installed()
    ensure_docker_access(str(state["target_user"]))
    source = Path(args.package_path).expanduser().resolve()
    if not source.is_file() or source.suffix.lower() != ".zip":
        fail("--package must point to a ZIP file")
    verify_zip_digest(source)
    install_root = Path(str(state["install_root"]))
    current = current_release(install_root)
    old_version = package_version(current)
    temporary = Path(tempfile.mkdtemp(prefix="qqbridge-upgrade-"))
    try:
        safe_extract_zip(source, temporary)
        new_package = package_root_from_extracted(temporary)
        verify_package(new_package)
        new_version = package_version(new_package)
        if version_tuple(new_version) <= version_tuple(old_version):
            fail(
                f"upgrade package version {new_version} must be higher than "
                f"current version {old_version}"
            )
        run(
            [
                "bash",
                str(new_package / "wsl" / "upgrade.sh"),
                "--package",
                str(new_package),
                "--install-root",
                str(install_root),
                "--target-user",
                str(state["target_user"]),
            ],
            capture=False,
        )
        state["package_version"] = new_version
        save_state(state)
        log(f"upgrade complete: {old_version} -> {new_version}")
    finally:
        shutil.rmtree(temporary, ignore_errors=True)


def command_rollback(args: argparse.Namespace) -> None:
    state = context_from_state()
    if args.backup_id and not BACKUP_ID_RE.fullmatch(args.backup_id):
        fail("invalid backup ID")
    install_root = Path(str(state["install_root"]))
    package = current_release(install_root)
    ensure_docker_installed()
    command = [
        "bash",
        str(package / "wsl" / "rollback.sh"),
        "--install-root",
        str(install_root),
        "--target-user",
        str(state["target_user"]),
    ]
    if args.backup_id:
        command.extend(["--backup-id", args.backup_id])
    run(command, capture=False)
    version = package_version(current_release(install_root))
    state["package_version"] = version
    save_state(state)
    log(f"rollback complete; current version is {version}")


def add_target_user(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--target-user",
        help="Linux user that owns the instance and runs Docker Compose",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="QQBridge native Linux installer and operations"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    install = subparsers.add_parser("install", help="install a new instance")
    add_target_user(install)
    install.add_argument("--install-root")
    install.add_argument(
        "--local-only",
        action="store_true",
        help="bind WebUIs to 127.0.0.1 (default)",
    )
    install.add_argument(
        "--lan",
        action="store_true",
        help="bind WebUIs to one detected/explicit LAN IPv4 address",
    )
    install.add_argument("--lan-bind-ip")
    install.add_argument("--lan-cidr", action="append")
    install.add_argument("--disable-autostart", action="store_true")

    configure = subparsers.add_parser("configure", help="update an instance")
    configure.add_argument("--instance", default="default")
    configure.add_argument("--advanced", action="store_true")
    configure.add_argument("--discover-groups", action="store_true")

    verify = subparsers.add_parser("verify", help="verify an installed instance")
    verify.add_argument("--instance", default="default")

    upgrade = subparsers.add_parser("upgrade", help="upgrade from a verified ZIP")
    upgrade.add_argument("--package", dest="package_path", required=True)

    rollback = subparsers.add_parser("rollback", help="restore the newest backup")
    rollback.add_argument("--backup-id")
    return parser


def main() -> None:
    ensure_linux()
    parser = build_parser()
    args = parser.parse_args()
    elevate_if_needed(args)
    commands = {
        "install": command_install,
        "configure": command_configure,
        "verify": command_verify,
        "upgrade": command_upgrade,
        "rollback": command_rollback,
    }
    commands[args.command](args)


if __name__ == "__main__":
    main()
