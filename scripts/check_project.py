#!/usr/bin/env python3
"""Inspect project-local installation; optionally verify a pinned read-only MCP roundtrip."""

from __future__ import annotations

import argparse
import asyncio
import configparser
import json
import os
import re
import shutil
import sys
import tomllib
from pathlib import Path


def local_config(project: Path, server: str) -> dict:
    path = project / ".codex/config.toml"
    if not path.is_file():
        return {}
    return (
        tomllib.loads(path.read_text(encoding="utf-8-sig")).get("mcp_servers", {}).get(server, {})
    )


def inspect_project(project: Path, server: str) -> dict:
    text = (project / "project.godot").read_text(encoding="utf-8-sig")
    cfg = project / "addons/godot_ai/plugin.cfg"
    plugin = configparser.ConfigParser(interpolation=None)
    if cfg.is_file():
        plugin.read(cfg, encoding="utf-8-sig")
    entry = local_config(project, server)
    section = re.search(r"(?ms)^\[editor_plugins\]\s*\n(.*?)(?=^\[|\Z)", text)
    enabled = bool(
        section
        and re.search(
            r'(?m)^enabled\s*=\s*PackedStringArray\([^)]*"res://addons/godot_ai/plugin.cfg"',
            section.group(1),
        )
    )
    return {
        "status": "inspection_only",
        "project": str(project),
        "plugin_present": cfg.is_file(),
        "plugin_version": plugin.get("plugin", "version", fallback="").strip('"'),
        "plugin_enabled_on_disk": enabled,
        "addon_is_link": cfg.parent.is_symlink() or cfg.parent.resolve() != cfg.parent,
        "project_config": str(project / ".codex/config.toml"),
        "project_server_present": bool(entry),
        "project_server_enabled": entry.get("enabled", True) if entry else None,
        "project_transport": "stdio"
        if entry.get("command")
        else "http"
        if entry.get("url")
        else None,
        "uvx_path": shutil.which("uvx"),
        "python_version": sys.version.split()[0],
        "effective_client_config_checked": False,
    }


def tool_data(result) -> dict:
    payload = result.model_dump(by_alias=True)
    if payload.get("isError", False):
        raise RuntimeError("MCP tool returned isError=true; inspect private client logs")
    data = payload.get("structuredContent")
    if not isinstance(data, dict):
        for item in payload.get("content", []):
            if item.get("type") == "text":
                try:
                    data = json.loads(item["text"])
                except (ValueError, TypeError):
                    continue
                if isinstance(data, dict):
                    break
    if not isinstance(data, dict):
        raise RuntimeError("Expected an object in MCP structuredContent or text JSON")
    if "error" in data:
        raise RuntimeError("MCP result contains an application error; inspect private client logs")
    return data


def select_session(data: dict, project: Path) -> dict:
    def matches(item):
        path = item.get("project_path")
        return (
            isinstance(path, str) and Path(path).is_absolute() and Path(path).resolve() == project
        )

    sessions = [item for item in data.get("sessions", []) if matches(item)]
    if len(sessions) != 1:
        raise RuntimeError(f"Expected exactly one target project session, found {len(sessions)}")
    if not sessions[0].get("session_id"):
        raise RuntimeError("Target session is missing session_id")
    return sessions[0]


async def probe(project: Path, entry: dict, timeout: float) -> dict:
    try:
        from mcp import ClientSession, StdioServerParameters, types
        from mcp.client.stdio import stdio_client
    except ImportError as exc:
        raise RuntimeError(
            "Probe needs the mcp Python SDK; use a dedicated verification environment"
        ) from exc
    if not entry.get("command") or entry.get("url"):
        raise ValueError("Probe requires a project-local stdio command, without a legacy url")
    if entry.get("enabled", True) is False:
        raise ValueError("Project entry is disabled; inspect the user's choice before enabling")
    # Probing executes the inspected configuration; never print raw argv/env.
    env = os.environ.copy()
    env.update(entry.get("env", {}))
    params = StdioServerParameters(
        command=entry["command"],
        args=entry.get("args", []),
        env=env,
        cwd=str(Path(entry.get("cwd", project)).resolve()),
    )
    with open(os.devnull, "w", encoding="utf-8") as errlog:
        async with asyncio.timeout(timeout):
            async with stdio_client(params, errlog=errlog) as (read, write):
                async with ClientSession(read, write) as client:
                    initialized = await client.initialize()
                    names = set()
                    cursor = None
                    while True:
                        listing = await client.list_tools(
                            params=types.PaginatedRequestParams(cursor=cursor)
                        )
                        names.update(t.name for t in listing.tools)
                        cursor = listing.model_dump(by_alias=True).get("nextCursor")
                        if not cursor:
                            break
                    if not {"session_manage", "editor_state"}.issubset(names):
                        raise RuntimeError("Required session_manage/editor_state tools are missing")
                    data = tool_data(await client.call_tool("session_manage", {"op": "list"}))
                    target = select_session(data, project)
                    state = tool_data(
                        await client.call_tool("editor_state", {"session_id": target["session_id"]})
                    )
                    return {
                        "status": "target_roundtrip_ok",
                        "server_name": initialized.model_dump(by_alias=True)["serverInfo"]["name"],
                        "tool_count": len(names),
                        "project": str(project),
                        "session_id": target["session_id"],
                        "plugin_version": target.get("plugin_version"),
                        "server_version": target.get("server_version"),
                        "godot_version": target.get("godot_version"),
                        "readiness": state.get("readiness", target.get("readiness")),
                        "actual_client_visibility_checked": False,
                    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--server", default="godot-ai")
    parser.add_argument(
        "--probe", action="store_true", help="Execute the inspected project-local MCP command"
    )
    parser.add_argument("--timeout", type=float, default=90)
    args = parser.parse_args()
    try:
        if args.timeout <= 0:
            raise ValueError("timeout must be positive")
        project = args.project.expanduser().resolve(strict=True)
        if not (project / "project.godot").is_file():
            raise ValueError("project must contain project.godot")
        report = inspect_project(project, args.server)
        if args.probe:
            report["probe"] = asyncio.run(
                probe(project, local_config(project, args.server), args.timeout)
            )
    except Exception as exc:
        # MCP exception groups can embed child argv; keep shared errors bounded.
        message = (
            str(exc)
            if isinstance(
                exc, (ValueError, RuntimeError, FileNotFoundError, tomllib.TOMLDecodeError)
            )
            else type(exc).__name__
        )
        print(json.dumps({"status": "failed", "error": message}, ensure_ascii=False))
        return 1
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
