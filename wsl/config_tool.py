#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import secrets
import shutil
import sys
from pathlib import Path
from typing import Any

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10 fallback; generated files are still checked in CI.
    tomllib = None


PLACEHOLDER_RE = re.compile(r"@@([A-Z0-9_]+)@@")
CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")


def clean_answer_value(value: Any) -> Any:
    if isinstance(value, str):
        return CONTROL_RE.sub("", value).strip()
    if isinstance(value, list):
        return [clean_answer_value(item) for item in value]
    return value


def fail(message: str) -> "NoReturn":
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write_text(path: Path, value: str, mode: int | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8", newline="\n")
    if mode is not None:
        path.chmod(mode)


def load_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] == "'":
            value = value[1:-1]
        elif len(value) >= 2 and value[0] == value[-1] == '"':
            value = json.loads(value)
        values[key] = value
    return values


def save_env(path: Path, values: dict[str, str]) -> None:
    preferred = [
        "INSTANCE_DIR",
        "COMPOSE_PROJECT_NAME",
        "PACKAGE_VERSION",
        "MAIBOT_BASE_IMAGE",
        "NAPCAT_BASE_IMAGE",
        "MAIBOT_IMAGE",
        "MAIBOT_PORT",
        "NAPCAT_PORT",
        "ONEBOT_PORT",
        "MAIBOT_BIND",
        "NAPCAT_BIND",
        "MAIBOT_MEMORY_LIMIT",
        "NAPCAT_MEMORY_LIMIT",
        "TZ",
        "RESTART_POLICY",
        "NAPCAT_UID",
        "NAPCAT_GID",
        "OWNER_QQ",
        "BOT_QQ",
        "WEBUI_TOKEN",
        "ONEBOT_TOKEN",
        "LLM_BASE_URL",
        "LLM_API_KEY",
        "LLM_MODEL",
        "LLM_CLIENT_TYPE",
        "SEARCH_BASE_URL",
        "SEARCH_API_KEY",
        "SEARCH_MODEL",
    ]
    ordered = preferred + sorted(key for key in values if key not in preferred)
    lines: list[str] = []
    for key in ordered:
        value = str(values.get(key, ""))
        if "\n" in value or "\r" in value:
            fail(f"{key} must not contain a newline")
        if "'" in value:
            fail(f"{key} must not contain a single quote")
        lines.append(f"{key}='{value}'")
    write_text(path, "\n".join(lines) + "\n", 0o600)


def render_template(text: str, values: dict[str, str]) -> str:
    missing: set[str] = set()

    def replacement(match: re.Match[str]) -> str:
        key = match.group(1)
        if key not in values:
            missing.add(key)
            return match.group(0)
        return values[key]

    rendered = PLACEHOLDER_RE.sub(replacement, text)
    if missing:
        fail("missing template values: " + ", ".join(sorted(missing)))
    return rendered


def validate_toml(path: Path) -> None:
    if tomllib is None:
        return
    try:
        with path.open("rb") as handle:
            tomllib.load(handle)
    except Exception as exc:
        fail(f"invalid TOML generated at {path}: {exc}")


def plugin_enabled(path: Path) -> bool | None:
    text = read_text(path)
    section = re.search(r"(?ms)^\[plugin\]\s*\n(.*?)(?=^\[|\Z)", text)
    if not section:
        return None
    match = re.search(r"(?m)^\s*enabled\s*=\s*(true|false)\s*(?:#.*)?$", section.group(1))
    return match.group(1) == "true" if match else None


def set_first_enabled(path: Path, enabled: bool) -> None:
    text = read_text(path)
    replacement = f"enabled = {'true' if enabled else 'false'}"
    updated, count = re.subn(
        r"(?m)^(\s*enabled\s*=\s*)(?:true|false)\b",
        replacement,
        text,
        count=1,
    )
    if count != 1:
        fail(f"plugin enabled flag not found in {path}")
    write_text(path, updated)


def set_assignment(text: str, key: str, value: str) -> str:
    encoded = json.dumps(value, ensure_ascii=False)
    updated, count = re.subn(
        rf"(?m)^(\s*{re.escape(key)}\s*=\s*)(?:\"[^\"]*\"|'[^']*'|[^\n#]*)(\s*(?:#.*)?)$",
        lambda match: match.group(1) + encoded + match.group(2),
        text,
        count=1,
    )
    if count != 1:
        fail(f"configuration key {key!r} not found")
    return updated


def set_section_assignment(text: str, section: str, key: str, value: str) -> str:
    pattern = re.compile(
        rf"(?ms)(^\[{re.escape(section)}\]\s*\n)(.*?)(?=^\[|\Z)"
    )
    match = pattern.search(text)
    if not match:
        fail(f"configuration section [{section}] not found")
    body = match.group(2)
    encoded = json.dumps(value, ensure_ascii=False)
    body, count = re.subn(
        rf"(?m)^(\s*{re.escape(key)}\s*=\s*)(?:\"[^\"]*\"|'[^']*'|[^\n#]*)(\s*(?:#.*)?)$",
        lambda item: item.group(1) + encoded + item.group(2),
        body,
        count=1,
    )
    if count != 1:
        fail(f"configuration key [{section}].{key} not found")
    return text[: match.start(2)] + body + text[match.end(2) :]


def render_model(config_dir: Path, package: Path, env: dict[str, str]) -> None:
    for key in ("LLM_BASE_URL", "LLM_API_KEY", "LLM_MODEL", "LLM_CLIENT_TYPE"):
        if any(char in env.get(key, "") for char in "\r\n\"\\") or CONTROL_RE.search(env.get(key, "")):
            fail(f"{key} contains an unsupported character")
    if env.get("LLM_CLIENT_TYPE") not in {"openai", "openai_responses", "gemini"}:
        fail("LLM_CLIENT_TYPE must be openai, openai_responses or gemini")
    template = read_text(package / "payload" / "config" / "model_config.toml.template")
    rendered = render_template(
        template,
        {
            "LLM_BASE_URL": env["LLM_BASE_URL"],
            "LLM_API_KEY": env["LLM_API_KEY"],
            "LLM_MODEL": env["LLM_MODEL"],
            "LLM_CLIENT_TYPE": env.get("LLM_CLIENT_TYPE", "openai"),
        },
    )
    path = config_dir / "model_config.toml"
    write_text(path, rendered, 0o600)
    validate_toml(path)


def render_bot_config(
    config_dir: Path,
    package: Path,
    env: dict[str, str],
    previous_owner_name: str | None = None,
) -> None:
    path = config_dir / "bot_config.toml"
    if path.exists():
        owner_name = env.get("OWNER_NAME", "群主") or "群主"
        text = read_text(path)
        text = text.replace("@@OWNER_NAME@@", owner_name)
        if previous_owner_name and previous_owner_name != owner_name:
            text = text.replace(previous_owner_name, owner_name)
        write_text(path, text, 0o600)
        validate_toml(path)
        return
    template = read_text(package / "payload" / "config" / "bot_config.toml.template")
    owner_name = env.get("OWNER_NAME", "群主") or "群主"
    if any(char in owner_name for char in "\r\n\\\""):
        fail("OWNER_NAME contains an unsupported character")
    rendered = template.replace("@@OWNER_NAME@@", owner_name)
    if "@@" in rendered:
        fail("unresolved placeholder in bot_config.toml")
    write_text(path, rendered, 0o600)
    validate_toml(path)


def render_persona_seed(
    instance: Path,
    env: dict[str, str],
    previous_owner_name: str | None = None,
) -> None:
    path = instance / "plugins" / "persona-manager" / "seed.json"
    if not path.exists():
        return
    owner_name = env.get("OWNER_NAME", "群主") or "群主"
    text = read_text(path).replace("@@OWNER_NAME@@", owner_name)
    if previous_owner_name and previous_owner_name != owner_name:
        text = text.replace(previous_owner_name, owner_name)
    try:
        json.loads(text)
    except json.JSONDecodeError as exc:
        fail(f"invalid persona seed after owner-name rendering: {exc}")
    write_text(path, text, 0o600)
    current = instance / "personas" / "current-hajimi.md"
    if current.exists():
        current_text = read_text(current).replace("@@OWNER_NAME@@", owner_name)
        if previous_owner_name and previous_owner_name != owner_name:
            current_text = current_text.replace(previous_owner_name, owner_name)
        write_text(
            current,
            current_text,
            0o600,
        )


def write_adapter_policy(config_dir: Path, allowed_groups: list[str], allowed_users: list[str]) -> None:
    def toml_list(values: list[str]) -> str:
        clean = sorted({str(value).strip() for value in values if str(value).strip().isdigit()})
        return "[" + ", ".join(json.dumps(value) for value in clean) + "]"

    text = (
        "[defaults.group]\n"
        'default_action = "block"\n'
        f"allow_ids = {toml_list(allowed_groups)}\n\n"
        "[defaults.private]\n"
        'default_action = "block"\n'
        f"allow_ids = {toml_list(allowed_users)}\n"
    )
    path = config_dir / "adapter_policy.toml"
    write_text(path, text, 0o600)
    validate_toml(path)


def render_napcat(instance: Path, package: Path, env: dict[str, str]) -> None:
    napcat = instance / "napcat" / "config"
    napcat.mkdir(parents=True, exist_ok=True)
    write_text(napcat / "napcat.json", read_text(package / "payload" / "napcat" / "napcat.json"), 0o600)

    webui_path = napcat / "webui.json"
    if webui_path.exists():
        webui = json.loads(read_text(webui_path))
    else:
        webui = json.loads(
            render_template(
                read_text(package / "payload" / "napcat" / "webui.json.template"),
                {"WEBUI_TOKEN": env["WEBUI_TOKEN"]},
            )
        )
    webui["host"] = "0.0.0.0"
    webui["port"] = 6099
    webui["token"] = env["WEBUI_TOKEN"]
    if env.get("BOT_QQ"):
        webui["autoLoginAccount"] = env["BOT_QQ"]
    else:
        webui.pop("autoLoginAccount", None)
    write_text(webui_path, json.dumps(webui, ensure_ascii=False, indent=2) + "\n", 0o600)

    onebot_paths = [napcat / "onebot11.json"]
    onebot_paths.extend(sorted(napcat.glob("onebot11_*.json")))
    for onebot_path in onebot_paths:
        if onebot_path.exists():
            onebot = json.loads(read_text(onebot_path))
        else:
            onebot = json.loads(
                render_template(
                    read_text(package / "payload" / "napcat" / "onebot11.json.template"),
                    {"ONEBOT_TOKEN": env["ONEBOT_TOKEN"]},
                )
            )
        network = onebot.setdefault("network", {})
        servers = network.setdefault("websocketServers", [])
        server = servers[0] if servers else {}
        server.update(
            {
                "name": "qqbridge",
                "enable": True,
                "host": "0.0.0.0",
                "port": 3001,
                "messagePostFormat": "array",
                "reportSelfMessage": True,
                "enableForcePushEvent": True,
                "token": env["ONEBOT_TOKEN"],
                "heartInterval": 30000,
                "debug": False,
            }
        )
        if not servers:
            servers.append(server)
        network["websocketServers"] = servers
        write_text(onebot_path, json.dumps(onebot, ensure_ascii=False, indent=2) + "\n", 0o600)


def update_snowluma(instance: Path, env: dict[str, str]) -> None:
    path = instance / "plugins" / "MaiBot-SnowLuma-Adapter" / "config.toml"
    text = read_text(path)
    text = set_section_assignment(text, "client", "server", "napcat")
    text = set_section_assignment(text, "client", "port", "3001")
    text = set_section_assignment(text, "client", "token", env["ONEBOT_TOKEN"])
    write_text(path, text, 0o600)
    validate_toml(path)


def configure_advanced(instance: Path, answers: dict[str, Any], env: dict[str, str]) -> None:
    plugins = instance / "plugins"

    search = plugins / "gemini_web_search" / "config.toml"
    text = read_text(search)
    search_base = str(answers.get("search_base_url", env.get("SEARCH_BASE_URL", ""))).strip()
    search_key = str(answers.get("search_api_key", env.get("SEARCH_API_KEY", ""))).strip()
    search_model = str(answers.get("search_model", env.get("SEARCH_MODEL", ""))).strip()
    if search_base or search_key or search_model:
        if not (search_base and search_key and search_model):
            fail("search configuration requires base URL, API key and model")
        text = set_assignment(text, "base_url", search_base)
        text = set_assignment(text, "api_key", search_key)
        text = set_assignment(text, "model", search_model)
        set_first_enabled(search, True)
    text = read_text(search)
    text = set_assignment(text, "base_url", search_base) if search_base else text
    text = set_assignment(text, "api_key", search_key) if search_key else text
    text = set_assignment(text, "model", search_model) if search_model else text
    write_text(search, text, 0o600)
    validate_toml(search)

    tts = plugins / "xuqian13_tts_voice_plugin" / "config.toml"
    tts_key = str(answers.get("tts_api_key", "")).strip()
    if tts_key:
        text = read_text(tts)
        text = set_assignment(text, "api_key", tts_key)
        if answers.get("tts_api_url"):
            text = set_assignment(text, "api_url", str(answers["tts_api_url"]).strip())
        if answers.get("tts_model"):
            text = set_assignment(text, "model", str(answers["tts_model"]).strip())
        if answers.get("tts_voice"):
            text = set_assignment(text, "default_voice", str(answers["tts_voice"]).strip())
        write_text(tts, text, 0o600)
        set_first_enabled(tts, True)
        validate_toml(tts)

    codex = plugins / "codex-draw" / "config.toml"
    codex_path = str(answers.get("codex_path", "")).strip()
    if codex_path:
        text = read_text(codex)
        text = set_assignment(text, "codex_path", codex_path)
        write_text(codex, text, 0o600)
        set_first_enabled(codex, True)
        validate_toml(codex)

    link_parser = plugins / "com_maibot_link-parser" / "config.toml"
    text = read_text(link_parser)
    proxy = str(answers.get("http_proxy", "")).strip()
    if proxy:
        for section in ("zhihu", "youtube", "twitter", "pixiv"):
            text = set_section_assignment(text, section, "proxy", proxy)
    for key, section in (
        ("zhihu_cookie", "zhihu"),
        ("youtube_cookie", "youtube"),
        ("pixiv_cookie", "pixiv"),
    ):
        value = str(answers.get(key, "")).strip()
        if value:
            text = set_section_assignment(text, section, "cookies", value)
    twitter_key = str(answers.get("twitter_api_key", "")).strip()
    if twitter_key:
        text = set_section_assignment(text, "twitter", "twitter_api_key", twitter_key)
    write_text(link_parser, text, 0o600)
    validate_toml(link_parser)

    parser = plugins / "Color2333_maibot-multi-platform-parser" / "config.toml"
    text = read_text(parser)
    if proxy:
        text = set_section_assignment(text, "network", "proxy", proxy)
    for key in ("douyin", "xhs", "bilibili"):
        value = str(answers.get(f"{key}_cookie", "")).strip()
        if value:
            text = set_section_assignment(text, "cookies", key, value)
    write_text(parser, text, 0o600)
    validate_toml(parser)

    moegirl = plugins / "xxxxx7258_moegirl-wiki-plugin" / "config.toml"
    cookie = str(answers.get("moegirl_cookie", "")).strip()
    if cookie:
        text = read_text(moegirl)
        text = set_section_assignment(text, "auth", "cookie_string", cookie)
        write_text(moegirl, text, 0o600)
        validate_toml(moegirl)


def write_plugin_report(instance: Path, package: Path) -> None:
    reasons = {
        "codex-draw": "Codex CLI 未配置，默认停用。",
        "gemini_web_search": "搜索服务凭据未配置，默认停用。",
        "xuqian13_tts_voice_plugin": "TTS 服务凭据未配置，默认停用。",
        "github_erhan111119_mai-repost-shit": "自动搬运动作需先设置目标群，默认停用。",
    }
    items = []
    plugins = instance / "plugins"
    for directory in sorted(path for path in plugins.iterdir() if path.is_dir()):
        config = directory / "config.toml"
        if not config.exists():
            items.append({"name": directory.name, "enabled": None, "reason": "未发现 config.toml"})
            continue
        enabled = plugin_enabled(config)
        items.append(
            {
                "name": directory.name,
                "enabled": enabled,
                "reason": reasons.get(directory.name, "") if enabled is False else "",
            }
        )
    report = {
        "generated_by": f"qqbridge-{read_text(package / 'VERSION').strip()}",
        "plugins": items,
        "note": "enabled=null 表示插件未显式声明开关，由 MaiBot 插件系统默认处理。",
    }
    write_text(instance / "plugin-report.json", json.dumps(report, ensure_ascii=False, indent=2) + "\n", 0o600)


def load_answers(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {}
    answers = json.loads(read_text(path))
    return {key: clean_answer_value(value) for key, value in answers.items()}


def command_install(args: argparse.Namespace) -> None:
    instance = Path(args.instance)
    package = Path(args.package)
    answers = load_answers(Path(args.answers) if args.answers else None)
    env_path = instance / ".env"
    env = load_env(env_path)
    package_version = read_text(package / "VERSION").strip()
    env.update(
        {
            "INSTANCE_DIR": str(instance),
            "COMPOSE_PROJECT_NAME": str(
                answers.get(
                    "compose_project_name",
                    os.environ.get("QQBRIDGE_COMPOSE_PROJECT_NAME", "qqbridge"),
                )
            ).strip(),
            "PACKAGE_VERSION": package_version,
            "MAIBOT_BASE_IMAGE": "sengokucola/maibot@sha256:02d2d9bdd7b3f22f73c63d0ca7a415a9f4c9d16b3f269ca63d62cedfa01edfda",
            "NAPCAT_BASE_IMAGE": "mlikiowa/napcat-docker@sha256:b101b8968cc31ae428ec0f8e117386e4ced7773b2d8226ed9f7ddfcec55f1b7e",
            "MAIBOT_IMAGE": f"qqbridge-maibot:{package_version}",
        }
    )
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", env["COMPOSE_PROJECT_NAME"]):
        fail("COMPOSE_PROJECT_NAME contains invalid characters")
    env.setdefault("MAIBOT_PORT", str(answers.get("maibot_port", "18001")))
    env.setdefault("NAPCAT_PORT", str(answers.get("napcat_port", "6099")))
    env.setdefault("ONEBOT_PORT", str(answers.get("onebot_port", "3001")))
    env.setdefault("MAIBOT_BIND", str(answers.get("maibot_bind", "0.0.0.0")))
    env.setdefault("NAPCAT_BIND", str(answers.get("napcat_bind", "0.0.0.0")))
    env.setdefault(
        "MAIBOT_MEMORY_LIMIT",
        str(answers.get("maibot_memory_limit", "1024m")),
    )
    env.setdefault(
        "NAPCAT_MEMORY_LIMIT",
        str(answers.get("napcat_memory_limit", "1024m")),
    )
    for memory_key in ("MAIBOT_MEMORY_LIMIT", "NAPCAT_MEMORY_LIMIT"):
        if not re.fullmatch(r"[1-9][0-9]*[mMgG]", env[memory_key]):
            fail(f"{memory_key} must look like 512m or 1g")
    env.setdefault("TZ", str(answers.get("timezone", "Asia/Shanghai")))
    env.setdefault(
        "RESTART_POLICY", str(answers.get("restart_policy", "unless-stopped"))
    )
    if env["RESTART_POLICY"] not in {"unless-stopped", "always", "on-failure", "no"}:
        fail("RESTART_POLICY must be unless-stopped, always, on-failure or no")
    env.setdefault("NAPCAT_UID", str(args.napcat_uid))
    env.setdefault("NAPCAT_GID", str(args.napcat_gid))
    env["OWNER_QQ"] = str(answers.get("owner_qq", env.get("OWNER_QQ", ""))).strip()
    env["OWNER_NAME"] = str(answers.get("owner_name", env.get("OWNER_NAME", "群主"))).strip()
    env["BOT_QQ"] = str(answers.get("bot_qq", env.get("BOT_QQ", ""))).strip()
    if env["OWNER_QQ"] and not env["OWNER_QQ"].isdigit():
        fail("OWNER_QQ must be numeric")
    if env["BOT_QQ"] and not env["BOT_QQ"].isdigit():
        fail("BOT_QQ must be numeric")
    env["LLM_BASE_URL"] = str(answers.get("llm_base_url", env.get("LLM_BASE_URL", ""))).strip()
    env["LLM_API_KEY"] = str(answers.get("llm_api_key", env.get("LLM_API_KEY", ""))).strip()
    env["LLM_MODEL"] = str(answers.get("llm_model", env.get("LLM_MODEL", ""))).strip()
    env["LLM_CLIENT_TYPE"] = str(answers.get("llm_client_type", env.get("LLM_CLIENT_TYPE", "openai"))).strip()
    env["WEBUI_TOKEN"] = env.get("WEBUI_TOKEN") or secrets.token_hex(32)
    env["ONEBOT_TOKEN"] = env.get("ONEBOT_TOKEN") or secrets.token_hex(32)
    for key in ("llm_base_url", "llm_api_key", "llm_model"):
        if not env[key.upper()]:
            fail(f"{key} is required for a new installation")

    config = instance / "config"
    config.mkdir(parents=True, exist_ok=True)
    save_env(env_path, env)
    render_model(config, package, env)
    render_bot_config(config, package, env)
    render_persona_seed(instance, env)
    write_adapter_policy(config, answers.get("allowed_groups", []), answers.get("allowed_users", []))
    render_napcat(instance, package, env)
    update_snowluma(instance, env)
    owner_file = instance / "plugins" / "persona-manager" / "data" / "owner.txt"
    if env["OWNER_QQ"]:
        write_text(owner_file, env["OWNER_QQ"] + "\n", 0o600)
    else:
        owner_file.unlink(missing_ok=True)
    configure_advanced(instance, answers, env)
    write_plugin_report(instance, package)


def command_configure(args: argparse.Namespace) -> None:
    instance = Path(args.instance)
    package = Path(args.package)
    answers = load_answers(Path(args.answers) if args.answers else None)
    env_path = instance / ".env"
    if not env_path.exists():
        fail(f"instance environment not found: {env_path}")
    env = load_env(env_path)
    package_version = read_text(package / "VERSION").strip()
    env.update(
        {
            "PACKAGE_VERSION": package_version,
            "MAIBOT_BASE_IMAGE": "sengokucola/maibot@sha256:02d2d9bdd7b3f22f73c63d0ca7a415a9f4c9d16b3f269ca63d62cedfa01edfda",
            "NAPCAT_BASE_IMAGE": "mlikiowa/napcat-docker@sha256:b101b8968cc31ae428ec0f8e117386e4ced7773b2d8226ed9f7ddfcec55f1b7e",
            "MAIBOT_IMAGE": f"qqbridge-maibot:{package_version}",
        }
    )
    previous_owner_name = env.get("OWNER_NAME", "群主")
    mapping = {
        "owner_qq": "OWNER_QQ",
        "owner_name": "OWNER_NAME",
        "bot_qq": "BOT_QQ",
        "maibot_port": "MAIBOT_PORT",
        "napcat_port": "NAPCAT_PORT",
        "onebot_port": "ONEBOT_PORT",
        "maibot_bind": "MAIBOT_BIND",
        "napcat_bind": "NAPCAT_BIND",
        "llm_base_url": "LLM_BASE_URL",
        "llm_api_key": "LLM_API_KEY",
        "llm_model": "LLM_MODEL",
        "llm_client_type": "LLM_CLIENT_TYPE",
        "search_base_url": "SEARCH_BASE_URL",
        "search_api_key": "SEARCH_API_KEY",
        "search_model": "SEARCH_MODEL",
        "restart_policy": "RESTART_POLICY",
    }
    for answer_key, env_key in mapping.items():
        if answer_key in answers:
            env[env_key] = str(answers[answer_key]).strip()
    if env.get("RESTART_POLICY", "unless-stopped") not in {
        "unless-stopped",
        "always",
        "on-failure",
        "no",
    }:
        fail("RESTART_POLICY must be unless-stopped, always, on-failure or no")
    save_env(env_path, env)
    config = instance / "config"
    if any(key in answers for key in ("llm_base_url", "llm_api_key", "llm_model", "llm_client_type")):
        render_model(config, package, env)
    render_bot_config(config, package, env, previous_owner_name)
    render_persona_seed(instance, env, previous_owner_name)
    if "allowed_groups" in answers or "allowed_users" in answers:
        write_adapter_policy(config, answers.get("allowed_groups", []), answers.get("allowed_users", []))
    render_napcat(instance, package, env)
    update_snowluma(instance, env)
    owner_file = instance / "plugins" / "persona-manager" / "data" / "owner.txt"
    if env.get("OWNER_QQ"):
        write_text(owner_file, env["OWNER_QQ"] + "\n", 0o600)
    else:
        owner_file.unlink(missing_ok=True)
    configure_advanced(instance, answers, env)
    write_plugin_report(instance, package)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("install", "configure"), required=True)
    parser.add_argument("--instance", required=True)
    parser.add_argument("--package", required=True)
    parser.add_argument("--answers")
    parser.add_argument("--napcat-uid", type=int, default=1000)
    parser.add_argument("--napcat-gid", type=int, default=1000)
    args = parser.parse_args()
    if args.mode == "install":
        command_install(args)
    else:
        command_configure(args)


if __name__ == "__main__":
    main()
