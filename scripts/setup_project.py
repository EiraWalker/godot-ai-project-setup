#!/usr/bin/env python3
"""Install, configure and verify one project in one connection, within a 60s deadline."""

from __future__ import annotations

import argparse
import asyncio
import copy
import ctypes
import json
import os
import re
import socket
import subprocess
import time
import tomllib
from pathlib import Path
from types import SimpleNamespace

from check_project import select_session, tool_data
from install_fresh import install, load_verifier

PLUGIN_PATH = "res://addons/godot_ai/plugin.cfg"


def backend_launch(entry, record):
    """Keep the persistent backend outside the SDK's Windows child-process kill scope."""
    args = list(entry["args"])
    attach = args.index("attach")
    env = {**os.environ, **entry.get("env", {})}
    if "--disable-telemetry" in args[attach + 1 :]:
        args.remove("--disable-telemetry")
        env["GODOT_AI_DISABLE_TELEMETRY"] = "true"
    args[attach : attach + 1] = ["--transport", "streamable-http"]
    args.extend(
        [
            "--pid-file",
            str(record / "backend.pid"),
            "--startup-report",
            str(record / "backend-startup.json"),
        ]
    )
    return [entry["command"], *args], env


def listening(port):
    with socket.socket() as probe:
        probe.settimeout(0.05)
        return probe.connect_ex(("127.0.0.1", port)) == 0


def validate_project_paths(project):
    for relative in ("project.godot", ".codex", ".codex/config.toml"):
        target = project / relative
        if os.path.lexists(target) and (target.is_symlink() or target.resolve() != target):
            raise ValueError(f"Project configuration path must stay in this project: {target}")
    config_dir = project / ".codex"
    if config_dir.exists() and not config_dir.is_dir():
        raise ValueError(".codex must be a directory")


def value_toml(value):
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, list):
        return "[" + ", ".join(value_toml(v) for v in value) + "]"
    if isinstance(value, dict):
        return (
            "{ " + ", ".join(value_toml(k) + " = " + value_toml(v) for k, v in value.items()) + " }"
        )
    if hasattr(value, "isoformat"):
        return value.isoformat()
    raise ValueError(f"Unsupported TOML value: {type(value).__name__}")


def table_path(line):
    if not re.fullmatch(r"\s*\[[^\n]+\]\s*(?:#.*)?\r?\n?", line):
        return None
    try:
        node = tomllib.loads(line)
    except tomllib.TOMLDecodeError:
        return None
    keys = []
    while isinstance(node, dict) and len(node) == 1:
        key, node = next(iter(node.items()))
        keys.append(key)
    return tuple(keys) if node == {} else None


def replace_table(raw: bytes, path: tuple[str, ...], entry: dict) -> bytes:
    """Replace this server's tables; preserve other text and validate semantic scope."""
    text = raw.decode("utf-8-sig")
    before = tomllib.loads(text)
    kept = []
    removing = False
    for line in text.splitlines(keepends=True):
        header = table_path(line)
        if header is not None:
            removing = header[: len(path)] == path
        if not removing:
            kept.append(line)
    section = "[" + ".".join(value_toml(k) for k in path) + "]\n"
    section += "".join(value_toml(k) + " = " + value_toml(v) + "\n" for k, v in entry.items())
    result = ("".join(kept).rstrip() + "\n\n" + section).lstrip("\n")
    after = tomllib.loads(result)
    expected = copy.deepcopy(before)
    parent = expected
    for key in path[:-1]:
        parent = parent.setdefault(key, {})
    parent[path[-1]] = entry
    if after != expected:
        raise ValueError("Configuration layout needs manual merge; no file was written")
    return (b"\xef\xbb\xbf" if raw.startswith(b"\xef\xbb\xbf") else b"") + result.encode()


def enable_plugin(raw: bytes) -> bytes:
    text = raw.decode("utf-8-sig")
    section = re.search(r"(?ms)^\[editor_plugins\][^\n]*\n(.*?)(?=^\[|\Z)", text)
    if section is None:
        return raw + f'\n[editor_plugins]\n\nenabled=PackedStringArray("{PLUGIN_PATH}")\n'.encode()
    content = section.group(1)
    enabled = re.search(r"(?ms)^enabled\s*=\s*PackedStringArray\((.*?)\)", content)
    if enabled:
        if json.dumps(PLUGIN_PATH) in enabled.group(1):
            return raw
        addition = (", " if enabled.group(1).strip() else "") + json.dumps(PLUGIN_PATH)
        position = section.start(1) + enabled.end(1)
        text = text[:position] + addition + text[position:]
    elif re.search(r"(?m)^enabled\s*=", content):
        raise ValueError("Unexpected enabled syntax in editor_plugins; inspect before editing")
    else:
        position = section.start(1)
        text = text[:position] + f'enabled=PackedStringArray("{PLUGIN_PATH}")\n' + text[position:]
    return (b"\xef\xbb\xbf" if raw.startswith(b"\xef\xbb\xbf") else b"") + text.encode()


class Run:
    def __init__(self, project, profile, record, started, budget):
        self.project, self.profile, self.record = project, profile, record
        self.started, self.deadline = started, started + budget
        self.stage = "preflight"
        self.events = []
        self.editor = None
        self.editor_shown = False
        self.record_created = False
        self.backend = None

    def mark(self, name):
        self.stage = name
        self.remaining()
        self.events.append(
            {"stage": name, "elapsed_sec": round(time.monotonic() - self.started, 3)}
        )
        print(json.dumps(self.events[-1]), flush=True)

    def remaining(self):
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError(f"Setup deadline reached at {self.stage}")
        return remaining

    def write(self, target, raw, backup_name):
        if target.is_file() and target.read_bytes() == raw:
            return
        if target.is_file():
            (self.record / backup_name).write_bytes(target.read_bytes())
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)

    def planned_entry(self):
        local = self.project / ".codex/config.toml"
        raw = local.read_bytes() if local.exists() else b""
        current = tomllib.loads(raw.decode("utf-8-sig"))
        entry = copy.deepcopy(current.get("mcp_servers", {}).get("godot-ai", {}))
        launcher = self.profile["launcher"]
        entry.update(
            command=launcher["command"], args=launcher["args"], cwd=str(self.project), enabled=True
        )
        entry.pop("url", None)
        entry.setdefault("startup_timeout_sec", 60)
        entry.setdefault("tool_timeout_sec", 360)
        return entry

    def configure(self):
        self.mark("configure_project")
        user = Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex"))) / "config.toml"
        user_raw = user.read_bytes() if user.exists() else b""
        settings = tomllib.loads(user_raw.decode("utf-8-sig"))
        local = self.project / ".codex/config.toml"
        raw = local.read_bytes() if local.exists() else b""
        entry = self.planned_entry()
        updated = replace_table(raw, ("mcp_servers", "godot-ai"), entry)
        self.write(local, updated, "project-config.before.toml")
        trust = settings.get("projects", {}).get(str(self.project), {})
        if trust.get("trust_level") != "trusted":
            trusted = {**trust, "trust_level": "trusted"}
            updated = replace_table(user_raw, ("projects", str(self.project)), trusted)
            self.write(user, updated, "user-config.before.toml")
        return entry

    def prepare_plugin(self):
        self.mark("verify_release_and_install")
        p = self.profile
        live = self.project / "addons/godot_ai"
        if os.path.lexists(live):
            verifier, _ = load_verifier(Path(p["repo"]))
            assets = Path(p["assets"])
            identity = ("hi-godot/godot-ai", "stable", p["tag"], p["version"], p["source"])
            manifest = verifier.verify_release(
                assets / verifier.ASSET_NAME,
                assets / verifier.MANIFEST_NAME,
                assets / verifier.SIGNATURE_NAME,
                identity,
            )
            if live.resolve() != live or live.is_symlink():
                raise ValueError("Development-linked installation needs its own workflow")
            if verifier.hash_tree(live)["tree_sha256"] != verifier.inventory_tree_hash(manifest):
                raise ValueError(
                    "Existing plugin differs from signed release; preserve it for review"
                )
            return "existing_signed_install"
        result = install(
            SimpleNamespace(
                project=self.project,
                repo=Path(p["repo"]),
                assets=Path(p["assets"]),
                tag=p["tag"],
                version=p["version"],
                source=p["source"],
                apply=True,
            )
        )
        return result["status"]

    async def editor_processes(self):
        import psutil

        matches = []
        for process in psutil.process_iter(["name", "cmdline"]):
            try:
                if "godot" not in (process.info["name"] or "").lower():
                    continue
                args = process.info["cmdline"] or []
                if (
                    "--path" in args
                    and Path(args[args.index("--path") + 1]).resolve() == self.project
                ):
                    matches.append(process)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        if len(matches) > 1:
            raise ValueError("Multiple editors for this project; select the intended editor first")
        return matches

    async def close_for_install(self, editors):
        if not editors:
            return
        self.mark("close_target_editor")
        for process in editors:
            for hwnd in windows_for_pid(process.pid):
                ctypes.windll.user32.PostMessageW(ctypes.c_void_p(hwnd), 0x0010, 0, 0)
            end = time.monotonic() + min(5, self.remaining())
            while process.is_running() and time.monotonic() < end:
                await asyncio.sleep(0.1)
            if process.is_running():
                raise RuntimeError(
                    "Editor remains open, possibly with unsaved work; no forced shutdown"
                )

    def start_editor(self):
        self.mark("start_editor_after_backend_ready")
        env = {**os.environ, **self.profile.get("editor_env", {})}
        startup = subprocess.STARTUPINFO()
        startup.dwFlags = subprocess.STARTF_USESHOWWINDOW
        startup.wShowWindow = 4  # Show without activation; start visible so editor frames run.
        log = self.record / "editor.log"
        with log.open("wb") as out:
            self.editor = subprocess.Popen(
                [
                    self.profile["godot"],
                    "--path",
                    str(self.project),
                    "--editor",
                    "--log-file",
                    str(log),
                    *self.profile.get("editor_args", []),
                ],
                stdin=subprocess.DEVNULL,
                stdout=out,
                stderr=out,
                env=env,
                cwd=self.project,
                startupinfo=startup,
                creationflags=0x08000000,
            )

    async def prepare_backend(self, entry):
        self.mark("prepare_persistent_backend")
        args = entry["args"]
        ports = [int(args[args.index(option) + 1]) for option in ("--port", "--ws-port")]
        occupied = [listening(port) for port in ports]
        if not any(occupied):
            command, env = backend_launch(entry, self.record)
            with (self.record / "backend.log").open("wb") as output:
                self.backend = subprocess.Popen(
                    command,
                    stdin=subprocess.DEVNULL,
                    stdout=output,
                    stderr=output,
                    cwd=self.project,
                    env=env,
                    creationflags=0x08000000,
                )
        while True:
            self.remaining()
            if all(listening(port) for port in ports):
                # Listening is sequencing only; attach performs the actual authenticated check.
                self.mark("backend_listening")
                return
            if self.backend is not None and self.backend.poll() is not None:
                raise RuntimeError("Backend exited before listening; inspect backend.log")
            await asyncio.sleep(0.1)

    def show_editor_without_activation(self):
        if self.editor and not self.editor_shown:
            for hwnd in windows_for_pid(self.editor.pid):
                ctypes.windll.user32.ShowWindowAsync(ctypes.c_void_p(hwnd), 4)
                ctypes.windll.user32.SetWindowPos(ctypes.c_void_p(hwnd), 1, 0, 0, 0, 0, 0x13)
                self.editor_shown = True

    async def connect_and_verify(self, entry, editors, prepared):
        from mcp import ClientSession, StdioServerParameters, types
        from mcp.client.stdio import stdio_client

        self.mark("authenticated_backend")
        env = {**os.environ, **entry.get("env", {})}
        params = StdioServerParameters(
            command=entry["command"], args=entry["args"], env=env, cwd=str(self.project)
        )
        with (self.record / "attach.stderr.log").open("w", encoding="utf-8") as err:
            async with stdio_client(params, errlog=err) as (read, write):
                async with ClientSession(read, write) as client:
                    initialized = await client.initialize()
                    names, cursor = set(), None
                    while True:
                        listing = await client.list_tools(
                            params=types.PaginatedRequestParams(cursor=cursor)
                        )
                        names.update(t.name for t in listing.tools)
                        cursor = listing.model_dump(by_alias=True).get("nextCursor")
                        if not cursor:
                            break
                    if not {"session_manage", "editor_state"}.issubset(names):
                        raise RuntimeError("Required tools missing from authenticated backend")
                    # Prepare one backend before the editor can try to spawn a competing one.
                    self.mark("backend_ready")
                    plugin, configured_entry = await prepared
                    if entry != configured_entry:
                        raise RuntimeError("Project configuration changed during setup; inspect it")
                    codex = asyncio.create_task(self.verify_codex())
                    if not editors:
                        self.start_editor()
                    self.mark("wait_target_session")
                    while True:
                        self.remaining()
                        self.show_editor_without_activation()
                        if self.editor is not None and self.editor.poll() is not None:
                            raise RuntimeError("Target editor exited; inspect editor.log")
                        data = tool_data(await client.call_tool("session_manage", {"op": "list"}))
                        target_sessions = [
                            s
                            for s in data.get("sessions", [])
                            if s.get("project_path")
                            and Path(s["project_path"]).resolve() == self.project
                        ]
                        if target_sessions:
                            target = select_session({"sessions": target_sessions}, self.project)
                            break
                        await asyncio.sleep(0.2)
                    self.mark("target_editor_state")
                    state = tool_data(
                        await client.call_tool("editor_state", {"session_id": target["session_id"]})
                    )
                    while state.get("readiness") == "importing":
                        self.remaining()
                        await asyncio.sleep(0.2)
                        state = tool_data(
                            await client.call_tool(
                                "editor_state", {"session_id": target["session_id"]}
                            )
                        )
                    effective = await codex
                    if target.get("plugin_version") != self.profile["version"]:
                        raise RuntimeError("Target plugin version differs from selected release")
                    if target.get("server_version") != self.profile["version"]:
                        raise RuntimeError("Target backend version differs from selected release")
                    return plugin, {
                        "server": initialized.model_dump(by_alias=True)["serverInfo"]["name"],
                        "tool_count": len(names),
                        "session": target,
                        "editor_state": state,
                        "codex_effective_config": effective,
                    }

    async def execute(self):
        self.record.mkdir(parents=True, exist_ok=False)
        self.record_created = True
        if os.name != "nt":
            raise ValueError("This editor lifecycle adapter currently supports Windows")
        for key in ("repo", "assets", "godot"):
            if not Path(self.profile[key]).exists():
                raise ValueError(f"Profile {key} path is unavailable")
        if not (self.project / "project.godot").is_file():
            raise ValueError("Target must contain project.godot")
        validate_project_paths(self.project)
        before = (self.project / "project.godot").read_bytes()
        enabled = enable_plugin(before)
        editors = await self.editor_processes()
        needs_restart = (
            not (self.project / "addons/godot_ai/plugin.cfg").is_file() or enabled != before
        )
        # Verify signed inputs before requesting a normal editor close.
        if needs_restart and editors:
            p = self.profile
            verifier, _ = load_verifier(Path(p["repo"]))
            assets = Path(p["assets"])
            verifier.verify_release(
                assets / verifier.ASSET_NAME,
                assets / verifier.MANIFEST_NAME,
                assets / verifier.SIGNATURE_NAME,
                ("hi-godot/godot-ai", "stable", p["tag"], p["version"], p["source"]),
            )
            await self.close_for_install(editors)
            editors = []
            before = (self.project / "project.godot").read_bytes()
            enabled = enable_plugin(before)

        def prepare_files():
            plugin = self.prepare_plugin()
            self.write(self.project / "project.godot", enabled, "project.godot.before")
            return plugin, self.configure()

        entry = self.planned_entry()
        async with asyncio.timeout(self.remaining()):
            prepared = asyncio.create_task(asyncio.to_thread(prepare_files))
            await self.prepare_backend(entry)
            plugin, result = await self.connect_and_verify(entry, editors, prepared)
        self.mark("complete")
        return {
            "status": "target_roundtrip_ok",
            "elapsed_sec": round(time.monotonic() - self.started, 3),
            "budget_sec": 60,
            "project": str(self.project),
            "plugin": plugin,
            "editor_pid": self.editor.pid if self.editor else editors[0].pid,
            "backend_created": self.backend is not None,
            "events": self.events,
            "verification": result,
            "current_chat_reloaded": False,
            "record": str(self.record),
        }

    async def verify_codex(self):
        process = await asyncio.create_subprocess_exec(
            self.profile["codex"],
            "mcp",
            "get",
            "godot-ai",
            "--json",
            cwd=self.project,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            creationflags=0x08000000,
        )
        try:
            out, err = await process.communicate()
        except BaseException:
            if process.returncode is None:
                process.terminate()
                await process.wait()
            raise
        (self.record / "codex.stderr.log").write_bytes(err)
        if process.returncode:
            raise RuntimeError("Codex configuration lookup failed; see codex.stderr.log")
        config = json.loads(out)
        transport = config.get("transport", {})
        if (
            config.get("enabled") is not True
            or Path(transport.get("cwd", "")).resolve() != self.project
        ):
            raise RuntimeError("Codex did not load the enabled project-local configuration")
        return {"enabled": True, "cwd": transport["cwd"]}


def windows_for_pid(pid):
    user32 = ctypes.windll.user32
    found = []
    callback_type = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

    def visit(hwnd, _):
        owner = ctypes.c_ulong()
        user32.GetWindowThreadProcessId(ctypes.c_void_p(hwnd), ctypes.byref(owner))
        if owner.value == pid:
            title = ctypes.create_unicode_buffer(1024)
            user32.GetWindowTextW(ctypes.c_void_p(hwnd), title, len(title))
            if title.value.endswith(" - Godot Engine"):
                found.append(hwnd)
        return True

    user32.EnumWindows(callback_type(visit), 0)
    return found


def error_details(exc):
    if isinstance(exc, BaseExceptionGroup):
        return [leaf for child in exc.exceptions for leaf in error_details(child)]
    # Transport exceptions can contain launch arguments; keep their details in private logs.
    return [
        {
            "type": type(exc).__name__,
            "message": str(exc)
            if type(exc) in (ValueError, RuntimeError, TimeoutError, FileNotFoundError)
            else "see logs",
        }
    ]


def main():
    started = time.monotonic()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument(
        "--profile", type=Path, default=Path(__file__).resolve().parents[1] / "config.local.json"
    )
    parser.add_argument("--record", type=Path)
    args = parser.parse_args()
    profile = json.loads(args.profile.read_text(encoding="utf-8-sig"))
    project = args.project.expanduser().resolve(strict=True)
    record = args.record or Path(profile["records"]) / f"{project.name}-{time.time_ns()}"
    # Leave room for closing stdio and writing evidence inside the one-minute target.
    run = Run(project, profile, record, started, 55)
    try:
        report = asyncio.run(run.execute())
    except Exception as exc:
        report = {
            "status": "failed",
            "stage": run.stage,
            "elapsed_sec": round(time.monotonic() - started, 3),
            "errors": error_details(exc),
            "events": run.events,
            "record": str(record),
        }
    if run.record_created:
        (record / "result.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)
    return 0 if report["status"] == "target_roundtrip_ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
