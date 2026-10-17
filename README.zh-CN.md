<div align="center">

# Godot AI Project Setup

通过可验证的 MCP 接入流程，将 Codex 连接到你的 Godot 项目。

签名插件安装 · 项目配置 · 编辑器连接验收

[![Windows](https://img.shields.io/badge/platform-Windows-0078D4?style=flat-square)](#环境要求) [![Godot AI 4.3.0](https://img.shields.io/badge/Godot_AI-4.3.0-478CBF?style=flat-square)](https://github.com/hi-godot/godot-ai/releases/tag/v4.3.0) [![MIT License](https://img.shields.io/badge/license-MIT-2EA44F?style=flat-square)](LICENSE)

[English](README.md) · **简体中文**

[快速开始](#快速开始) · [文档](#文档) · [反馈问题](https://github.com/EiraWalker/godot-ai-project-setup/issues)

</div>

## 为什么使用它？

面向 Windows 的 [Godot AI](https://github.com/hi-godot/godot-ai) v4 接入工具与 Codex skill，用一个命令完成指定项目的插件接入和编辑器连接验收。

- **先校验，再安装。** 验证签名发布包，并核对已安装的插件文件。
- **限定配置范围。** 合并项目级 MCP 配置，保留已有设置，为修改的文件创建备份。
- **处理编辑器生命周期。** 复用可用编辑器，或按需正常关闭并重开目标编辑器，保留未保存工作。
- **确认目标项目。** 按完整项目路径匹配会话，携带显式 `session_id` 调用 `editor_state`。

## 环境要求

- Windows 与 PowerShell。
- Python **3.11–3.14**、**uvx** 和原生 **Codex 可执行文件**。
- **Godot 4.7+，限 4.x 系列**；C# 项目使用 .NET 编辑器。
- 可信 Godot AI 源码，以及同一固定版本的签名发布材料。

示例配置以 **Godot AI 4.3.0** 为基线。插件发布包与上游签名校验器需单独获取。

## 快速开始

### 1. 获取工具

```powershell
git clone https://github.com/EiraWalker/godot-ai-project-setup.git
cd godot-ai-project-setup
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item config.example.json config.local.json
```

### 2. 配置本机环境

根据[示例配置](config.example.json)填写 `config.local.json`：

| 配置项 | 填写内容 |
| --- | --- |
| `repo` | 可信上游源码目录，包含 `src/godot_ai/release_verify.py` |
| `assets` | 同一发布版的 ZIP、manifest 与签名所在目录 |
| `tag`、`version`、`source` | 固定发布身份，以及独立确认的源码 commit |
| `godot`、`codex` | 编辑器与原生 Codex 可执行文件的绝对路径 |
| `launcher` | 已核验、固定版本的 `godot-ai attach` 命令及实际端口 |
| `records` | 游戏项目外的结果、日志与备份目录 |

按[标准接入流程](references/project-installation.zh-CN.md)获取并核验发布材料。替换所有示例路径，保留 launcher 隔离策略、域排除与遥测偏好。`config.local.json` 已被 Git 忽略。

### 3. 接入项目

保存目标编辑器中的工作，然后在工具目录执行：

```powershell
.\.venv\Scripts\python.exe -B -X utf8 .\scripts\setup_project.py --project 'D:\projects\MyGame'
```

命令会安装或核验插件、启用插件、配置项目级 MCP 访问与该项目的 Codex 信任，并验收目标编辑器连接。执行时可能重开目标编辑器并启动持久后端。

通过 Agent 使用时，将整个仓库目录安装为 `godot-ai-project-setup` Codex skill，入口为 [SKILL.md](SKILL.md)，随后提出：

> 将 Godot AI MCP 接入 `D:\projects\MyGame` 项目。

## 确认结果

查看 `records` 下本次运行目录中的 `result.json`。成功时，程序在完成指定项目的只读 MCP 调用后返回 `status: "target_roundtrip_ok"`。

若 `current_chat_reloaded` 为 `false`，请从该项目新开 Codex 聊天，以加载项目 MCP 配置。接入探针与当前聊天使用各自的连接。

引擎、依赖和签名包已有缓存时，接入以一分钟为目标。首次下载、大型项目导入和未保存工作可能需要更多时间。已有旧版或修改过的插件，应按[升级与恢复流程](references/project-installation.zh-CN.md)处理。

## 文档

| 资源 | 用途 |
| --- | --- |
| [Skill 说明](SKILL.md) | Agent 工作流与完成条件 |
| [标准接入流程](references/project-installation.zh-CN.md) | 发布校验、手动接入、升级与恢复 |
| [项目检查脚本](scripts/check_project.py) | 项目盘点与可选只读 MCP 探针 |
| [新装脚本](scripts/install_fresh.py) | 签名包预览与新插件目录安装 |

## 参与贡献

欢迎提交 Issue 和 Pull Request。反馈接入失败时，请提供失败阶段、软件版本和相关日志，并移除秘密与私人路径。

## 致谢与许可

基于 [hi-godot/godot-ai](https://github.com/hi-godot/godot-ai) 的 v4.3.0 发布构建接入流程。本工具独立维护，上游插件与校验工具保留各自的版权声明。

本仓库采用 [MIT License](LICENSE)。
