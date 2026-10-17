# Godot AI Project Setup

用于把 [Godot AI](https://github.com/hi-godot/godot-ai) v4 MCP 接入指定 Godot 项目的 Codex skill，面向 Windows / PowerShell。

自动校验签名发布包、安装或核验插件、合并项目级 Codex 配置、处理目标编辑器重开，并通过完整项目路径与显式 session_id 执行只读 MCP 验收。保留其他项目、插件及 MCP 配置。

## 安装 skill

克隆本仓库到本地，将整个仓库目录作为 `godot-ai-project-setup` skill 安装到 Codex 的 skills 目录（可使用目录 junction）。入口为 [SKILL.md](SKILL.md)。本仓库仅包含接入工具，不包含 Godot AI 插件发布包或上游签名校验器。

## 本机准备

1. 准备 Python 3.11–3.14、匹配的 Godot 编辑器、uvx 和原生 Codex 可执行文件。建议在独立 Python 环境执行 `python -m pip install -r requirements.txt`。
2. 获取可信的上游源码，以及同一固定版本的 ZIP、manifest 与签名；依据 [标准流程](references/project-installation.zh-CN.md) 独立核对发布 commit 和校验器来源。
3. 将 `config.example.json` 复制为 `config.local.json`，填写真实路径、版本、端口、记录目录及 launcher。示例路径须替换；版本基线为 Godot AI 4.3.0、Godot 4.7+。`repo` 指向上游源码目录，包含 `src/godot_ai/release_verify.py`。

本机配置受到 `.gitignore` 排除。保留已有 launcher 的隔离策略、后台包装器、域排除与遥测选择。签名材料准备和新机器依赖下载按实际耗时记录。

## 使用

向已安装此 skill 的 Codex 提出“将 Godot AI MCP 接入 `<项目绝对目录>`”，或从 skill 目录运行：

```powershell
python -B -X utf8 .\scripts\setup_project.py --project 'D:\projects\MyGame'
```

命令会修改指定项目的插件与配置、添加该项目的 Codex 信任，并按需正常关闭/重开目标编辑器、启动持久后端。执行前保存目标编辑器的工作；未保存内容阻塞时不会强制结束编辑器。

已有引擎、依赖和签名包缓存的本机验收：新装 **32.1 秒**、目标编辑器已打开 **26.7 秒**、重复接入 **10.1 秒**。这些是特定机器的实测，包含签名校验与真实工具调用；大型项目导入、网络下载和等待保存不保证一分钟。

结果及备份写入 profile 指定的项目外记录目录。`current_chat_reloaded=false` 表示当前聊天尚未热加载 MCP，应从目标项目新开聊天。成功探针不表示当前聊天已经可调用工具。

## 文件

- `scripts/setup_project.py`：单命令安装、配置与连接验收。
- `scripts/install_fresh.py`：签名包预览与仅限新装的文件安装。
- `scripts/check_project.py`：项目检查与可选只读 MCP 探针。
- `references/project-installation.zh-CN.md`：新机器准备、手动流程、升级与恢复。

## 来源与许可

以 [hi-godot/godot-ai](https://github.com/hi-godot/godot-ai) 的 v4.3.0 发布及官方配置为基线。本工具独立维护，非 Godot AI 官方发行包。上游签名校验器和插件由用户从可信上游获取，并保留其版权声明。

本仓库采用 [MIT License](LICENSE)。
