# Obsidian 自动同步

当前 `main` 已内置 **设置 → Obsidian 文库**，提供配置、立即同步、自动同步、状态和打开索引的完整入口；**已发布的 RC6 安装包不含此新增入口**。打包入口和任务脚本已支持此功能，后续安装包可直接使用，源码运行现已可用。无需安装 Obsidian 插件或向文库放入 API Key。

## 在设置页连接

1. 启动最新源码的 Windows 本机版，在“设置 → Obsidian 文库”选择已发现的文库，或填写已有文库路径。
2. 选择推送来源：本机，或 Linux 服务器。服务器模式填写 SSH 地址和数据库路径；先核对主机指纹，确认密钥登录成功。服务器需有 Python 3，本机需有 OpenSSH 客户端。
3. 填写每日订阅 ID、导入起始时间和归档时区。订阅 ID 可从对应实例的 `/api/subscriptions` 获取。起始时间默认本机当天零点，可提前以补齐历史。
4. 保存配置，点击“立即同步到 Obsidian”。成功后可打开论文索引，再启用自动同步。修改配置后需先保存；保存本身不检索、不发信、不导入 Zotero，也不注册自动任务。
5. 状态区显示真实同步时间、结果、累计论文/每日清单数量，以及独立自动任务状态。失败可检查连接后再次同步；停用只移除同步任务，保留笔记。

本机模式只读本机数据库；服务器模式通过 SSH 只读成功投递记录。服务器网页会提示在 Windows 本机版连接，不会把笔记写入服务器上的同名路径。当前设置页维护一个订阅连接；多个订阅可用下面的高级配置分别运行，并使用独立导出文件夹及任务名称。

## 高级配置与命令行

1. 按 README 安装源码的 `backend/.venv`。本机需要 OpenSSH 客户端，服务器需要 Python 3；先人工核对 SSH 主机指纹，确认密钥登录成功。
2. 打开目标 Obsidian 文库。同步要求其已有 `.obsidian` 目录。
3. 在文库之外保存配置，例如 `D:\codex\integrations\literature-agent-obsidian\config.json`：

```json
{
  "vault": "D:\\My Vault",
  "folder": "Literature Agent",
  "mode": "ssh",
  "ssh_target": "user@server",
  "database": "/opt/literature-agent/data/literature_agent_v2.db",
  "subscription_id": "从网页订阅或 API 获取的订阅 ID",
  "since": "2026-10-18T16:00:00+00:00",
  "timezone": "Asia/Hong_Kong"
}
```

`since` 是首次导入范围的下限，必须带时区；示例对应香港时间 2026-10-19 零点。后续每次读取此范围内的全部成功记录，因此断网后能补齐，且能补入稍晚完成的 Zotero 链接。需要历史论文时将它提前，再运行同步。不会自动导入更早的测试批次。`folder` 使用普通的相对目录名；每个订阅使用独立配置目录和独立导出文件夹。

SSH 用户必须能只读访问服务器 SQLite 及其 WAL 文件。工具使用 `mode=ro` 和一致读事务，不复制运行中的数据库、不调用检索/发信/导入接口；不修改服务器状态。SSH 开启 BatchMode 和严格主机检查；网络连接、读取失败会在下次运行重试。本机模式改为 `"mode": "local"` 并填写本机数据库路径，不需要 SSH；已有省略 `mode` 的配置兼容为服务器模式。

设置页默认将配置和同步状态保存到当前数据目录的 `obsidian/` 子目录。早期独立工具用户可在启动源码前设置 `LITERATURE_AGENT_OBSIDIAN_CONFIG` 为已有配置文件的绝对路径，设置页及其注册任务便复用原有映射，不搬动个人文库或状态文件。命令行的 `--config` 始终使用显式指定的配置。

从仓库根目录执行：

```powershell
./backend/.venv/Scripts/python.exe -m literature_agent.obsidian --config D:\codex\integrations\literature-agent-obsidian\config.json
./scripts/register-obsidian-sync.ps1 -Config D:\codex\integrations\literature-agent-obsidian\config.json
```

打包程序新增 `LiteratureAgent.exe --sync-obsidian <配置文件>` 命令；注册脚本会自动选择安装版 EXE 或源码 Python。构建脚本包含所需的快照脚本，卸载流程会移除 Obsidian 自动任务并保留文库。上述新增命令不适用于历史 RC6 EXE。

任务名称为 `Literature Agent Obsidian Sync`，当前用户登录时和每 15 分钟运行一次，使用 `pythonw.exe` 避免弹出终端。机器关机、用户注销或无法连服务器时暂停；重新登录联网后补齐。电脑关机不影响服务器正常邮件推送。它与负责检索/邮件的 `Literature Agent Daily`、`Literature Agent Local` 任务相互独立。

## 在 Obsidian 阅读

- `Literature Agent/论文索引.md`：按日期进入每日清单。
- `Literature Agent/Daily/YYYY-MM-DD.md`：按订阅时区的**邮件发送日**归档，保留同日多次成功发送的清单，并链接到对应邮件正文及附件；空 digest 也有说明。
- `Literature Agent/Papers/*.md`：每篇一份，包含作者、日期、来源、研究问题、方法、发现、局限、推荐理由、研究用途、证据提示、DOI/原文、JIF 数值/年份/来源及已有 Zotero 条目的跳转链接。不会下载 PDF。点击 Zotero 链接需要本机 Zotero 已登录并同步相应文库。
- `Literature Agent/Emails/*.md`：邮件主题、发送时间和完整纯文本正文；保留论文顺序、去重统计、无新增说明、来源诊断、标识符数量和缺失提示。该笔记同样有“我的阅读笔记”区域。
- `Literature Agent/Attachments/*.txt`：邮件完整正文 TXT 和原有 `zotero-identifiers.txt` 附件内容，按投递分别命名，便于复制到 Zotero。已有自动导入条目不必再次粘贴。

新发送流程在 SMTP 调用前保存 `email_digest.<delivery_id>` 运行产物，包含当次 subject/text/html、附件及发送时论文信息；同步只读取投递成功的记录。未来指标变动或编辑论文不会改变这份发送时快照。没有快照的旧邮件使用当次订阅、检索/去重产物、论文与可用指标重建，**明确标注“按历史运行记录重建”**，不声称与原始收件箱逐字一致。此功能不会登录邮箱读取其他邮件；HTML 作为服务器快照保留，文库使用便于检索的完整纯文本正文。

论文按共享 DOI/PMID/arXiv/来源 ID 和保守标题作者规则复用笔记；文件名含稳定摘要后缀以避免同名覆盖。每日清单显示完整论文标题。相同论文可以出现在多个清单，笔记只保留一份。

自动更新仅替换 `<!-- literature-agent:start -->` 与 `<!-- literature-agent:end -->` 之间的内容。请把批注写在其后的“我的阅读笔记”区域；标记外的文字和已有 YAML 属性会保留。不要移动、重命名自动生成的文件，或修改管理标记，否则可能重新创建笔记或报错。已有同名文件没有标记时会拒绝覆盖。TXT 原文不插入管理标记，使用状态中的校验值保护；手工修改附件后会拒绝覆盖，请把批注留在对应 Markdown 笔记。

## 状态、排错与停用

配置旁的 `state.json` 保存身份与路径映射，`last-sync.json` 保存最近时间、成功/失败和数量，`sync.lock` 用于防止同步与配置保存并发；不含 SMTP 或模型密钥。更换文库/文件夹会为新目标使用单独的 `state-<摘要>.json`，保留原目标笔记及映射；切回原目标仍可复用。请备份文库及状态文件。

```powershell
Get-ScheduledTaskInfo -TaskName 'Literature Agent Obsidian Sync'
Get-Content -Raw D:\codex\integrations\literature-agent-obsidian\last-sync.json
# 手动验证任务
Start-ScheduledTask -TaskName 'Literature Agent Obsidian Sync'
# 停用（保留笔记和配置）
./scripts/register-obsidian-sync.ps1 -Config D:\codex\integrations\literature-agent-obsidian\config.json -Unregister
```

失败时先检查同用户 SSH 无交互登录、服务器数据库路径和订阅 ID。缺失管理标记时先备份并恢复标记，不要强制覆盖自己的笔记。更换仓库位置或删除虚拟环境后需要重新注册任务。这是从服务器到文库的单向导出，Obsidian 批注不会写回工作台、Zotero 或服务器。

## 产品接口

| 接口 | 用途 |
| --- | --- |
| `GET /api/obsidian` | 是否支持、已保存配置、已发现文库、最近同步、独立任务状态 |
| `PUT /api/obsidian` | 保存上述配置对象；校验文库、相对文件夹、SSH 地址、起始时区及归档时区 |
| `POST /api/obsidian/sync` | 同步已保存连接，返回投递数、论文访问数、累计笔记和日期数 |
| `POST /api/obsidian/register`、`/disable` | 注册/移除独立自动同步任务 |
| `POST /api/obsidian/open` | 使用本机 Obsidian URI 打开已有论文索引 |

配置校验失败返回 `422`，未配置或连接/文件/任务操作失败返回 `400`；非 Windows 或服务器运行时拒绝桌面动作（`409`），状态返回 `supported=false`。这些接口沿用本机 Origin 写保护，不新增远程执行或认证机制；服务器仍需保持回环绑定及 SSH 访问。

## 2026-10-19 实机验证

已在用户选定的 RAG_Agent 文库启用上述任务，从当天 07:08 成功投递记录导入 10 篇，生成 10 份论文笔记、一份每日清单与索引，保留 10 个已有 Zotero 跳转链接。计划任务实际执行返回 `0`，重复同步仍为 10 份笔记。

- 产品化版本全量 **258 项后端测试通过**，涵盖本机只读导出、配置保存/校验、失败恢复、服务器隔离及安装版命令路由。
- 前端构建与 **2 项新增 Edge 浏览器回归通过**，验证保存、立即同步、失败重试、启停任务、打开索引、未保存配置拦截和服务器提示；手机宽度无横向溢出。
- PyInstaller 开发构建完成，EXE 的 `--sync-obsidian` 实测本机一篇合成数据与真实服务器 10 篇同步均成功；独立临时任务选择了打包 EXE、实际执行返回 `0`，验收后已移除临时任务。打包版网页服务和 Obsidian 状态接口也实际启动，识别 4 个文库、10 份论文笔记与现有自动任务。开发构建位于 D 盘验证目录，未替换已发布 RC6 资产或本机安装程序。
- 邮件内容补齐通过 **261 项后端测试**，包括发送前正文/附件快照与 SMTP 参数一致、历史邮件重建与共享邮件渲染一致、JIF/来源诊断/去重统计、零置信度、附件路径与个人修改保护。2026-10-19 实际导出仍是 10 份论文笔记，新增一份邮件存档及两份 TXT（正文、标识符）；当次邮件重建显示合并 27 条重复、排除 28 篇历史推送。
- 正式服务器的发送快照采集已部署，运行镜像为 `literature-agent:obsidian-mail-821aac8f09e5`（RC6 基础镜像只补发送模块）。17 张表及配置校验一致，worker 健康；未为验证而重复发信或写 Zotero。后续自然推送的快照采集仍以实际投递记录为准。
