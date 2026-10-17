# Godot AI v4 项目安装标准流程（Windows / Codex）

## 快速入口与计时边界

日常接入使用一个命令；详细手动步骤留作新机器准备、升级和故障恢复。

```powershell
python -B -X utf8 '<skill-dir>\scripts\setup_project.py' --project 'D:\path\to\MyGame'
```

`config.local.json` 是本机配置，不进入 Git。它固定可信仓库、签名发布三件套目录、tag/version/独立确认的 source commit、Godot 路径、原生 `codex.exe` 路径、记录目录和现有安全 stdio launcher。新增机器时依据下文流程确认这些值，再创建该文件；不要从待验证 manifest 自报值建立信任。参考结构：

```json
{
  "repo": "D:/tools/godot-ai",
  "assets": "D:/path/to/verified-release-assets",
  "tag": "v4.3.0",
  "version": "4.3.0",
  "source": "b82b5c519b1b17228f70d8effce1626f391bd1dd",
  "godot": "D:/path/to/Godot.exe",
  "codex": "C:/path/to/native/codex.exe",
  "records": "D:/path/to/install-records",
  "launcher": { "command": "C:/path/to/uvx.exe", "args": ["完整的已验证解析参数及精确版本 godot-ai attach 参数"] }
}
```

launcher 采用第 5 节的完整隔离参数和实际端口，并保留本机现有 `pythonw` 后台包装器；上面的参数占位不是可执行配置。`codex` 使用安装包里的原生 EXE，避免 npm/PowerShell shim 反复启动 Node。普通运行需要 `cryptography`、MCP SDK 及 `psutil`，可复用本机已配置环境；其他机器先在独立环境中准备。

程序在主要步骤设 55 秒总 deadline，为结束 stdio 和写记录预留时间；计时不因重试清零。通过 `--record <新目录>` 指定证据位置。出现签名错误、已修改插件、歧义编辑器、未保存工作或时间不足，保存当前阶段并失败退出，保留用户项目，转入针对该原因的处理。

执行顺序是：只读确认目标 → 正常关闭需要重新载入的目标编辑器 → **签名文件安装和持久后端准备并行** → 合并项目配置和单项目信任 → 一个 attach 连接认证，tools/list 就绪 → 启动/复用目标编辑器 → 在同一连接等待准确的 project_path → 显式 session_id 读取 editor_state，等待 importing 结束 → 核对真实 Codex 已加载项目配置。端口检查只用于安排启动顺序；认证和真实工具调用仍是验收条件。

Windows MCP SDK 的 stdio 连接会清理其子进程组，所以持久后端必须由接入命令在探针之外启动，不能让临时探针代为创建后端。后端复用完整版本固定/索引隔离策略；关闭遥测的 attach 参数转换为该后端进程的 opt-out 环境变量。成功后保留新启动的服务和目标编辑器，复用的服务始终保留；日志、PID 和启动报告存放在该次记录目录。以后客户端继续使用 stdio attach，配置不保存 HTTP URL 或 capability。

结果会区分 MCP 连接已验收和当前聊天尚未热加载。若无新问题，直接根据 `result.json` 交付，不再启动完整重复检查。编辑器日志和 attach stderr 已保存在同一记录目录，失败时直接读取相关文件，不先再等一次长超时。

一分钟目标覆盖本机缓存可用时的完整接入操作，包含签名校验、文件安装、首次插件导入、后端启动、编辑器重开、项目配置/信任及工具往返。已有引擎、运行时/包缓存及签名包是此机器的初始状态。新机器缺少这些材料、网络下载、业务项目大量导入或等待未保存工作时，不承诺固定耗时，必须将实际耗时和未完成项写入记录。

## 适用范围与输入

为一个已确定的 Godot 项目安装发布版插件、启用插件、接入 MCP 客户端，并验证工具确实访问该项目。流程不包含发布、Git 提交或推送。

必需输入是项目绝对目录（内含 `project.godot`）、Godot 可执行文件和客户端。新装还需确定版本/tag、独立确认的发布源码 commit、签名三件套和可信校验器源码。目录未给定时询问，不默认选择其他现有项目或仓库测试项目。

上游源码目录由 profile 的 `repo` 指定（示例：`D:\tools\godot-ai`）。流程验证基线 commit 为 `b82b5c519b1b17228f70d8effce1626f391bd1dd`，插件/Python 版本均为 4.3.0。这只是本地基线，不是“最新版本”或所选发布包 commit 的替代值。脚本支持 Python 3.11+；该基线服务包要求 Python >=3.11,<3.15、Godot >=4.7 且属于 4.x。安装其他版本时重新核对要求。

## 1. 安装前盘点

```powershell
$projectRoot = 'D:\path\to\MyGame'  # 替换为用户指定项目
$repoRoot = 'D:\tools\godot-ai'
$skillRoot = '<此 skill 的绝对目录>'
python -X utf8 "$skillRoot\scripts\check_project.py" --project $projectRoot
Get-Command uv, uvx -ErrorAction SilentlyContinue
```

使用绝对路径执行 Godot 的 `--version` 验证引擎；C# 项目使用带 .NET 的编辑器。GodotSharp 目录须与 .NET 编辑器保留配套。

读取项目及父目录的适用 `AGENTS.md`，用 `git status --short` 记录已有更改。检查 `addons/godot_ai`、`project.godot` 的 `[editor_plugins]`、`[autoload]` 和 `.codex/config.toml`。先备份将修改的文件，备份放项目外且记录路径。

根据 `CODEX_HOME` 定位实际用户配置，未设置时为 `%USERPROFILE%\.codex\config.toml`；检查用户级、项目级以及当前工作目录的近层配置对 `godot-ai` / `godot_ai` 的影响。只摘录相关字段，不输出完整配置或秘密。记录用户配置的 SHA-256，结束时对照，证明项目接入未改写全局配置。检查脚本只展示项目本层，不代替 Codex 的配置合并、信任状态或策略校验。

已有目标编辑器时复用其身份；离线文件安装前先确认该目标编辑器已关闭，保留未保存工作，不强制结束任何现有编辑器。其他项目的 Godot/Python 进程继续保留。

## 2. 安装分支

| 当前状态 | 处理 |
|---|---|
| `addons/godot_ai` 不存在，无遗留更新状态 | 下节签名包新装 |
| 已有同版发布插件 | 先检查插件与客户端连接；需要时用签名 inventory 核对安装树 |
| 已有旧版 | 使用该版本支持的 dock Update；v3 先读仓库 `docs/v4-migration.md` |
| 插件有本地改动、junction、未知版本或 `.godot_ai_update` 遗留 | 先核对来源、备份和更新状态，保留现有目录；不走新装脚本 |
| 需要修改 MCP 自身源码 | 仓库 `docs/CONTRIBUTING.md` 和 `script/setup-dev.ps1`，与普通项目发布版接入分别处理 |

新装使用 `godot-ai-v4-plugin.zip`。`godot-ai-plugin.zip` 是 v3 迁移胶囊，不能作为 v4 普通插件包解压。

## 3. 签名包新装

从 [官方 Releases](https://github.com/hi-godot/godot-ai/releases) 选择明确版本，下载同一 release 的：

- `godot-ai-v4-plugin.zip`
- `godot-ai-v4-plugin.manifest.json`
- `godot-ai-v4-plugin.manifest.sig`

可用 `gh release download <tag> --repo hi-godot/godot-ai --pattern godot-ai-v4-plugin.zip --pattern godot-ai-v4-plugin.manifest.json --pattern godot-ai-v4-plugin.manifest.sig --dir <下载目录>`；也可使用对应 tag 的官方下载 URL。保持 tag 固定，下载失败先解决，不换成未固定的 latest 或源码目录。现有本机 ZIP 没有相配的 manifest/signature 时，仅视为待验证材料。

可信校验器为本地仓库 `src/godot_ai/release_verify.py`。从可信源码/发布凭据确认其版本及公钥指纹；不要把待验证 manifest 自报的 commit 当作独立来源。基线公钥 SPKI SHA-256 是 `84ebbd811f3a12c09ff4e236bbbbb9310fc23e03fcfc3717ba546747d0d21072`。脚本输出实际校验器文件 hash 供记录；此自报 hash 不能建立源码可信性。

签名校验需要 `cryptography`，只装到专用校验虚拟环境，或复用已确认可用的 Python 环境；不为此修改目标游戏依赖。缺少依赖时，先用 `python -m venv <校验环境>`，再用该环境的 `python -m pip install cryptography`。普通 `check_project.py` 盘点只依赖 Python 标准库。

```powershell
$assetDir = 'D:\path\to\release-assets'
$releaseTag = 'v4.3.0'         # 示例；采用实际选择的发布版
$releaseVersion = '4.3.0'
$releaseCommit = '<独立确认的40位发布源码commit>'
$installArgs = @(
    '--project', $projectRoot, '--repo', $repoRoot, '--assets', $assetDir,
    '--tag', $releaseTag, '--version', $releaseVersion, '--source', $releaseCommit
)
python -X utf8 "$skillRoot\scripts\install_fresh.py" @installArgs
if ($LASTEXITCODE -ne 0) { throw '发布包校验未通过，停止安装' }
# 已有安装授权且目标编辑器已关闭后执行：
python -X utf8 "$skillRoot\scripts\install_fresh.py" @installArgs --apply
if ($LASTEXITCODE -ne 0) { throw '文件安装未完成，保留现场检查' }
```

不加 `--apply` 只校验签名、发布身份、归档和 inventory，项目保持不变。加 `--apply` 后，官方校验器对冻结字节再校验并 staging，脚本在同一磁盘 rename 到新的 `addons/godot_ai`，最后比对整树 hash。已存在路径、链接目标和遗留更新状态会拒绝。重复运行不会覆盖已有安装。

成功状态 `installed_files_only` **仅代表文件安装**；脚本不写 `project.godot`、客户端配置或升级 marker，因此也不会触发该 marker 的跨客户端 repin。文件安装不应与另一个安装器同时运行。后续若树校验失败，停止启用并保留现场；不要把失败树当作可用安装。

## 4. 启用目标项目插件

用确认过的 Godot 打开目标项目，等待资源导入完成。在 **Project → Project Settings → Plugins → Godot AI** 启用，确认 Godot AI dock 可见。

若需要离线编辑 `project.godot`，只在目标编辑器关闭时合并 `[editor_plugins]` 的 `enabled=PackedStringArray(...)`，保留其他插件，加入 `res://addons/godot_ai/plugin.cfg`。优先使用编辑器完成启用。插件启动可能写入 `_mcp_game_helper` autoload，按实际 diff 记录；不覆盖已有用户 autoload。

记录 dock 的实际 HTTP/WebSocket 端口、后端版本和连接状态。默认通常为 8000/9500，但已有服务和用户设置可能不同。排查端口时先识别进程和所属项目，不清理其他项目的服务。

## 5. 项目级 Codex 配置

对 Codex 默认手动合并目标项目根的 `.codex/config.toml`。**不要使用 dock Configure / Configure all 来实现“仅此项目”**：当前 Codex descriptor 使用用户级 TOML，`mcp_client_scope=project` 不能改变它。`codex mcp add` 也不作为此流程的项目级写入步骤。

复用用户条目里的已验证绝对可执行路径和后台启动包装器；Windows 上已有 `pythonw.exe` / `CREATE_NO_WINDOW` 包装时予以保留。下面是无秘密的基本 stdio 模板，路径、版本和端口均需代入实际值：

```toml
[mcp_servers."godot-ai"]
command = "C:/absolute/path/to/uvx.exe"
args = [
  "--isolated", "--no-config", "--no-env-file", "--no-sources", "--no-build",
  "--index", "https://pypi.org/simple",
  "--default-index", "https://pypi.org/simple",
  "--find-links", "https://pypi.org/simple/godot-ai/",
  "--index-strategy", "first-index", "--keyring-provider", "disabled",
  "--link-mode", "copy", "--from", "godot-ai==4.3.0",
  "godot-ai", "attach", "--port", "8000", "--ws-port", "9500"
]
cwd = "D:/absolute/path/to/MyGame"
enabled = true
startup_timeout_sec = 60
tool_timeout_sec = 360
```

客户端 `command` 是单个可执行文件，`args` 是参数数组，不把整条 shell 字符串塞进 `command`。版本精确匹配插件；沿用 dock 生成命令的解析策略，禁止为了启动成功而删除索引隔离参数。冷缓存可在终端用同一 launcher 的 `godot-ai attach --version` 预热，并保留上述解析策略；失败应检查包可用性或网络，而非反复加大超时。

遥测沿用用户设置。若已选择关闭，在 attach 参数中保留 `--disable-telemetry`，并确认编辑器插件端偏好一致；只设置探针进程环境不代表已关闭正在运行的后端。域排除采用实际 `--exclude-domains`，也应与编辑器一致。Vision Routing 按需另行配置。

已有条目合并时保留 `env`、工具过滤、审批策略和用户超时；清除该条目与 stdio 冲突的旧 `url` 字段，不写入 capability token。全局 `enabled=false` 保持不动：用户明确要求此项目接入时，可在该项目显式 `enabled=true`，并说明覆盖仅限这个受信任项目。用 TOML 解析器核对语法并检查精确 diff。

项目配置仅在受信任项目加载。先从目标目录确认实际 Codex 配置/状态，必要时由用户完成该项目的信任操作；不要顺便扩大其他目录的信任。建立新聊天或按客户端支持的方式重载 MCP 后，再确认实际工具列表。配置落盘不等于当前聊天热加载成功。

## 6. 分层验收

`--probe` 会执行项目配置中的 command，可能通过 attach 启动/采用匹配后端；先检查该命令确为本次 Godot AI launcher。它只调用只读业务工具，临时连接退出不停止用户已有编辑器/后端。

探针需要 MCP Python SDK。使用已安装匹配 SDK 的环境，或专用验证环境（基线仓库使用 `mcp==2.2.0`；不同版本应核对对应依赖）。不要把验证依赖装入游戏项目。

```powershell
python -X utf8 "$skillRoot\scripts\check_project.py" --project $projectRoot --probe
```

| 层级 | 验收证据 |
|---|---|
| 文件 | 正确插件根目录、版本、签名校验及安装树 hash |
| 编辑器 | 实际目标编辑器 dock 正常，插件无 parse/startup 错误 |
| 临时 MCP | initialize 成功、工具可枚举，记录实际数量 |
| 目标身份 | `session_manage(op="list")` 中完整 `project_path` 匹配，恰好一个目标会话 |
| 工具往返 | 显式 `session_id` 的 `editor_state` 成功，记录 readiness 和版本 |
| 实际客户端 | 用户实际客户端/聊天可见并能调用 Godot AI 工具，不能用临时探针代替 |

同一路径若有多个编辑器，先明确目标 PID/session；脚本会拒绝歧义，不任意选择或调用全局 `session_activate`。`no_scene` 是可连接但无已编辑场景；无需为了验收去创建业务节点。需要场景层验收时，只读打开用户确认的现有场景并读取层级，不用 `project_run`，它可能自动保存。

## 7. 失败定位与恢复

| 现象 | 下一步 |
|---|---|
| 签名/身份/树校验失败或缺少 sidecar | 停止文件安装；核对同一 release 三件套、可信校验器和独立身份 |
| 插件未出现在列表 | 检查路径必须为 `addons/godot_ai/plugin.cfg`，不是多嵌一层或 `addons/plugin.cfg` |
| 插件报不支持引擎 | 核对所选发布版的引擎下限，不改插件版本门禁 |
| 端口监听但连接失败 | 分别检查 attach、capability、端口与版本，不转成无认证 HTTP |
| 工具未加载 | 分别检查项目是否受信任、条目是否启用、客户端是否重载、冷缓存/启动错误 |
| 返回了别的项目或目标会话数非一 | 查看 sessions 与完整路径，确认目标 PID，再显式 pin 单次调用 |
| 握手成功但探针失败 | 查看实际客户端私有日志；探针为防输出启动参数不转发子进程 stderr |
| 升级失败 | 按仓库 `docs/self-update.md` / `docs/v4-migration.md`，保留 `addons/.godot_ai_update/backup` 与 pending 记录 |

回退新装时先关闭目标编辑器，核对本次修改清单和备份，只恢复本次修改的项目配置、插件启用项及新增 helper autoload；保留其他插件/autoload/场景。新装目录先移到明确的项目外备份，不递归清理其他 addons。启用后还原配置应基于 diff，避免把并行产生的项目更改覆盖掉。

交付记录目标路径、引擎/插件/服务版本、发布身份与 hash、插件和客户端配置位置、备份位置、各层验收状态、全局配置 hash 对照以及仍待用户操作的步骤。未完成真实客户端/编辑器验证时明确写“待验证”。

## 依据与维护

- 本地仓库：`README.md`、`docs/packaging-distribution.md`、`docs/client-configuration.md`、`docs/self-update.md`、`docs/v4-migration.md`。
- 实现依据：`src/godot_ai/release_verify.py`、`script/v4-release`、`plugin/addons/godot_ai/clients/codex.gd`、`src/godot_ai/attach/main.py`、`src/godot_ai/handlers/session.py`。
- [Codex MCP 配置](https://developers.openai.com/codex/mcp/) 和 [项目配置与信任](https://developers.openai.com/codex/config-basic/)：项目配置、stdio 字段和加载条件。
- [uv CLI 官方文档](https://docs.astral.sh/uv/reference/cli/)：隔离工具运行和解析选项。

升级这个流程时先读当前源码及所选发布版说明；若签名格式、public staging API、客户端配置或会话工具协议变化，同时调整脚本并重新验证。
