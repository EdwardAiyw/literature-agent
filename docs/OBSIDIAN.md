# Obsidian 自动同步

当前 `main` 提供独立的源码同步工具，**未打包进已发布的 RC6 安装包**。Linux 服务器继续负责检索、邮件和 Zotero；Windows 通过已有 SSH 身份读取指定订阅成功发送的 digest，生成本地 Markdown。无需安装 Obsidian 插件或向文库放入 API Key。

## 配置

1. 按 README 安装源码的 `backend/.venv`。本机需要 OpenSSH 客户端，服务器需要 Python 3；先人工核对 SSH 主机指纹，确认密钥登录成功。
2. 打开目标 Obsidian 文库。同步要求其已有 `.obsidian` 目录。
3. 在文库之外保存配置，例如 `D:\codex\integrations\literature-agent-obsidian\config.json`：

```json
{
  "vault": "D:\\My Vault",
  "folder": "Literature Agent",
  "ssh_target": "user@server",
  "database": "/opt/literature-agent/data/literature_agent_v2.db",
  "subscription_id": "从网页订阅或 API 获取的订阅 ID",
  "since": "2026-10-18T16:00:00+00:00",
  "timezone": "Asia/Hong_Kong"
}
```

`since` 是首次导入范围的下限，必须带时区；示例对应香港时间 2026-10-19 零点。后续每次读取此范围内的全部成功记录，因此断网后能补齐，且能补入稍晚完成的 Zotero 链接。需要历史论文时将它提前，再运行同步。不会自动导入更早的测试批次。`folder` 使用普通的相对目录名；每个订阅使用独立配置目录和独立导出文件夹。

SSH 用户必须能只读访问服务器 SQLite 及其 WAL 文件。工具使用 `mode=ro` 和一致读事务，不复制运行中的数据库、不调用检索/发信/导入接口；不修改服务器状态。SSH 开启 BatchMode 和严格主机检查；网络连接、读取失败会在下次运行重试。

从仓库根目录执行：

```powershell
./backend/.venv/Scripts/python.exe -m literature_agent.obsidian --config D:\codex\integrations\literature-agent-obsidian\config.json
./scripts/register-obsidian-sync.ps1 -Config D:\codex\integrations\literature-agent-obsidian\config.json
```

任务名称为 `Literature Agent Obsidian Sync`，当前用户登录时和每 15 分钟运行一次，使用 `pythonw.exe` 避免弹出终端。机器关机、用户注销或无法连服务器时暂停；重新登录联网后补齐。电脑关机不影响服务器正常邮件推送。它与负责检索/邮件的 `Literature Agent Daily`、`Literature Agent Local` 任务相互独立。

## 在 Obsidian 阅读

- `Literature Agent/论文索引.md`：按日期进入每日清单。
- `Literature Agent/Daily/YYYY-MM-DD.md`：按订阅时区的**邮件发送日**归档，保留同日多次成功发送的清单；空 digest 也有说明。
- `Literature Agent/Papers/*.md`：每篇一份，包含作者、日期、来源、摘要、证据提示、DOI/原文及已有 Zotero 条目的跳转链接。不会下载 PDF。点击 Zotero 链接需要本机 Zotero 已登录并同步相应文库。

论文按共享 DOI/PMID/arXiv/来源 ID 和保守标题作者规则复用笔记；文件名含稳定摘要后缀以避免同名覆盖。每日清单显示完整论文标题。相同论文可以出现在多个清单，笔记只保留一份。

自动更新仅替换 `<!-- literature-agent:start -->` 与 `<!-- literature-agent:end -->` 之间的内容。请把批注写在其后的“我的阅读笔记”区域；标记外的文字和已有 YAML 属性会保留。不要移动、重命名自动生成的文件，或修改管理标记，否则可能重新创建笔记或报错。已有同名文件没有标记时会拒绝覆盖。

## 状态、排错与停用

配置旁的 `state.json` 保存身份与路径映射，`last-sync.json` 保存最近时间、成功/失败和数量，`sync.lock` 用于防止并发；不含 SMTP 或模型密钥。更换文库/文件夹需使用新的配置目录，避免复用旧映射。请备份文库及状态文件。

```powershell
Get-ScheduledTaskInfo -TaskName 'Literature Agent Obsidian Sync'
Get-Content -Raw D:\codex\integrations\literature-agent-obsidian\last-sync.json
# 手动验证任务
Start-ScheduledTask -TaskName 'Literature Agent Obsidian Sync'
# 停用（保留笔记和配置）
./scripts/register-obsidian-sync.ps1 -Config D:\codex\integrations\literature-agent-obsidian\config.json -Unregister
```

失败时先检查同用户 SSH 无交互登录、服务器数据库路径和订阅 ID。缺失管理标记时先备份并恢复标记，不要强制覆盖自己的笔记。更换仓库位置或删除虚拟环境后需要重新注册任务。这是从服务器到文库的单向导出，Obsidian 批注不会写回工作台、Zotero 或服务器。

## 2026-10-19 实机验证

已在用户选定的 RAG_Agent 文库启用上述任务，从当天 07:08 成功投递记录导入 10 篇，生成 10 份论文笔记、一份每日清单与索引，保留 10 个已有 Zotero 跳转链接。计划任务实际执行返回 `0`，重复同步仍为 10 份笔记。Windows 后端全量 **249 项测试通过**；其中新增自动化测试覆盖重复导入、跨记录身份复用、批注保留、恶意标题/标记、越界路径/文件冲突，以及超过 100 条成功记录的只读快照过滤。
