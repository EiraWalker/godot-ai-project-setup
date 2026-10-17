<div align="center">

# Godot AI Project Setup

Connect Codex to your Godot project with a verified MCP setup.

Signed plugin installation · Project configuration · Editor connection checks

[![Windows](https://img.shields.io/badge/platform-Windows-0078D4?style=flat-square)](#requirements) [![Godot AI 4.3.0](https://img.shields.io/badge/Godot_AI-4.3.0-478CBF?style=flat-square)](https://github.com/hi-godot/godot-ai/releases/tag/v4.3.0) [![MIT License](https://img.shields.io/badge/license-MIT-2EA44F?style=flat-square)](LICENSE)

**English** · [简体中文](README.zh-CN.md)

[Quick start](#quick-start) · [Documentation](#documentation) · [Report an issue](https://github.com/EiraWalker/godot-ai-project-setup/issues)

</div>

## Why use it?

A Windows setup toolkit and Codex skill for [Godot AI](https://github.com/hi-godot/godot-ai) v4. One command takes a selected project from plugin setup to a verified editor connection.

- **Verify before installing.** Check signed release assets and verify the installed plugin files.
- **Keep setup scoped.** Merge project-level MCP configuration, preserve existing settings, and back up changed files.
- **Handle the editor lifecycle.** Reuse a working editor or close and reopen the target editor when required, respecting unsaved work.
- **Confirm the right project.** Match the full project path and call `editor_state` with an explicit `session_id`.

## Requirements

- Windows with PowerShell.
- Python **3.11–3.14**, **uvx**, and the native **Codex executable**.
- **Godot 4.7+ within the 4.x series**; use the .NET editor for C# projects.
- Trusted Godot AI source and signed release assets for the same pinned version.

The included profile targets **Godot AI 4.3.0**. The plugin and upstream signature verifier are obtained separately.

## Quick start

### 1. Get the toolkit

```powershell
git clone https://github.com/EiraWalker/godot-ai-project-setup.git
cd godot-ai-project-setup
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item config.example.json config.local.json
```

### 2. Configure your machine

Edit `config.local.json` using the [example profile](config.example.json):

| Setting | What to provide |
| --- | --- |
| `repo` | Trusted upstream checkout containing `src/godot_ai/release_verify.py` |
| `assets` | Matching release ZIP, manifest, and signature directory |
| `tag`, `version`, `source` | Pinned release identity and independently confirmed source commit |
| `godot`, `codex` | Absolute paths to the editor and native Codex executable |
| `launcher` | Verified, version-pinned `godot-ai attach` command and actual ports |
| `records` | Directory outside the game project for results, logs, and backups |

Follow the [setup guide](references/project-installation.zh-CN.md) (Chinese) to obtain and verify release materials. Replace all example paths and preserve your launcher isolation, domain exclusions, and telemetry preferences. `config.local.json` is ignored by Git.

### 3. Connect a project

Save your work in the target editor, then run from the toolkit directory:

```powershell
.\.venv\Scripts\python.exe -B -X utf8 .\scripts\setup_project.py --project 'D:\projects\MyGame'
```

This installs or verifies the plugin, enables it, configures project-level MCP access and Codex trust for that project, and verifies the target editor connection. It may reopen the target editor and start a persistent backend.

For agent use, install the entire repository directory as the `godot-ai-project-setup` Codex skill; [SKILL.md](SKILL.md) is its entry point. Then ask:

> Set up Godot AI MCP for the project at `D:\projects\MyGame`.

## Verify the result

Check `result.json` in the run directory under `records`. A successful run reports `status: "target_roundtrip_ok"` after a read-only MCP call to the selected project.

If `current_chat_reloaded` is `false`, start a new Codex chat from that project to load its MCP configuration. The setup probe and the current chat are separate connections.

With the engine, dependencies, and signed assets already cached, setup targets one minute. First-time downloads, large project imports, and unsaved work can require additional time. Existing older or modified plugins follow the [upgrade and recovery guide](references/project-installation.zh-CN.md), rather than a fresh installation.

## Documentation

| Resource | Purpose |
| --- | --- |
| [Skill instructions](SKILL.md) | Agent workflow and completion criteria (Chinese) |
| [Setup guide](references/project-installation.zh-CN.md) | Release verification, manual setup, upgrades, and recovery (Chinese) |
| [Project checker](scripts/check_project.py) | Project inspection and an optional read-only MCP probe |
| [Fresh installer](scripts/install_fresh.py) | Signed release preview and installation into a new plugin directory |

## Contributing

Issues and pull requests are welcome. For setup failures, include the failing stage, software versions, and relevant logs with secrets and private paths removed.

## Acknowledgments & license

Built around [hi-godot/godot-ai](https://github.com/hi-godot/godot-ai), using its v4.3.0 release as the baseline. This toolkit is independently maintained; upstream plugins and verification tools retain their own copyright notices.

Released under the [MIT License](LICENSE).
