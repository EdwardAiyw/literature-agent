# Literature Agent 日报与交接 - 2026-11-01

记录时区：Asia/Hong_Kong。下一次人工处理日期：**2026-11-02**。

## 今日结论

**0.3.0-rc.7 已完成开发、GitHub 发布、本机覆盖升级及服务器部署。明天从页面配置和实际使用验收继续，无需重复安装或部署。**

数据来源已做成可在产品页面管理的功能。“设置 → 文献来源”支持添加、配置、测试、启停、移除连接，保存密钥、每日请求上限及新任务/订阅的默认选择。Google Scholar 通过 SerpApi 接入，需要用户提供该服务的密钥。

## 今日完成

- 支持 11 种来源：Semantic Scholar、OpenAlex、Crossref、arXiv、PubMed、DOAJ、DataCite、HAL、Europe PMC、Google Scholar（SerpApi）、CORE。默认添加前 9 种；Google Scholar 和 CORE 等待用户在页面添加并配置密钥。
- 任务和订阅的来源选择关联已保存的连接；停用来源在读取缓存或发出网络请求前跳过。已有订阅保留原来源选择，新增来源不会自动加入既有订阅。
- 新适配器接入缓存、限速、逐来源请求预算、部分结果保留、日期精度和跨来源去重。Google Scholar 搜索片段与作者摘要分开保存，密钥不回显，查询日志脱敏。
- RC7 安装包同时包含此前的 Obsidian 页面设置和完整邮件归档功能。
- GitHub `main`、公开预发布、安装包、校验文件和项目文档已更新。发布标签保持不可变；完整发布证据见 [RELEASE_RC7.md](RELEASE_RC7.md)，使用规则见 [SOURCES.md](SOURCES.md)。

## 已验证

| 范围 | 结果 |
| --- | --- |
| Windows 后端 | 299 项测试通过 |
| 前端 | 生产构建通过，36 项完整 Edge 回归通过 |
| GitHub Windows Release | 全量测试、打包和打包程序检查通过 |
| 最终 Linux 镜像 | 298 项通过，1 项 Windows 专用文件锁检查跳过 |
| 新开放 API | DOAJ、DataCite、HAL、Europe PMC 各返回 HTTP 200 和两条规范化记录 |
| 真实安装版与服务器页面 | 桌面及 390px 手机页面通过，显示 9 个已添加来源及 Google Scholar/CORE 配置入口，无页面错误或横向溢出 |
| 公开安装包 | 匿名重新下载后，与校验文件及 GitHub 资产摘要一致 |

Google Scholar 和 CORE 已完成模拟接口检查，并核对了 SerpApi 公开样例；**尚未使用用户密钥完成授权真实检索**，明天需在页面测试实际权限和额度。

本次升级未触发新的文献检索、邮件发送或 Zotero 导入。RC7 仍为预发布版，干净系统首次设置、自然调度及外部邮箱实际收件仍待验收。

## 当前运行状态与数据保护

| 项目 | 交接状态 |
| --- | --- |
| 本机安装版 | RC7；页面 `http://127.0.0.1:8001/` |
| 本机安装与数据 | 安装位置 `D:/Program Files (x86)/Literature Agent/`；数据库 `E:/Literature Agent/literature_agent_v2.db` |
| 服务器 | 镜像 `literature-agent:rc7-e75abad`，健康检查及内部调度正常 |
| 服务器管理页 | 本次通过 SSH 隧道访问 `http://127.0.0.1:18001/`；需要隧道运行 |
| 现有每日订阅 | 保留 07:00 Asia/Hong_Kong、每日最多 10 篇、截止到运行日、原来源及 Zotero 目标 |
| 本机计划任务 | Local/Daily 继续停用，避免与服务器重复发送；既有 Obsidian 自动任务保留 |
| Obsidian | 安装版复用现有配置与笔记映射；未重新导出笔记 |
| LocalJev | 保持 Shadow 模式 |

本机和服务器升级分别核验了全部 17 张表及保存配置，各自与升级前一致；本机 Windows 凭据、服务器密钥及相关配置哈希保留。**服务器继续按既有计划运行，本机与服务器数据各自独立。**

明早预期自然运行时间为 **2026-11-02 07:00 Asia/Hong_Kong**，实际结果需明天查看，本报告不代表该次运行已经发生。服务器是现有每日任务和配置的管理入口。

如需重建管理隧道，在项目目录运行以下命令，将 `user@server` 替换为已有的 SSH 目标：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/open-server.ps1 -Target user@server
```

详细操作见 [服务器部署说明](SERVER_DEPLOYMENT.md)、[Windows 用户指南](WINDOWS_USER_GUIDE.md)及 [Obsidian 说明](OBSIDIAN.md)。

## 明天处理清单（2026-11-02）

1. **先打开服务器管理页，检查 07:00 自然运行的状态、来源诊断和邮件记录，并确认外部邮箱实际收件及 Zotero/Obsidian 输出。**先看已有记录，避免为验证而重复运行造成重复发送或导入。
2. 打开“设置 → 文献来源”，检查启用状态、默认选择及每日请求上限。需要 Google Scholar 或 CORE 时，在页面添加连接并填写自己的服务密钥。
3. 对准备使用的连接执行页面测试，确认实际权限、额度和失败提示；只有真实测试成功后，才将对应授权来源记为验收通过。
4. 编辑**现有每日订阅**，明确选择要新增的来源并保存。来源设置中的默认选择只影响新任务/订阅，不会扩大现有订阅。
5. 后续观察扩展来源后的自然运行质量、去重和来源诊断，继续补齐干净系统首次设置与外部收件验收；验收完成前保留预发布状态。

## GitHub、备份与证据

- 公开版本：[v0.3.0-rc.7](https://github.com/EdwardAiyw/literature-agent/releases/tag/v0.3.0-rc.7)。安装包：`Literature-Agent-0.3.0-rc.7-Windows-x64.exe`，29,420,269 字节。
- 不可变版本提交：`e75abade0862ecd39337948b65ca23052f8a87af`；发布检查修复：`ec4cc8a45e085f206473dbf208d3291dc8733a5b`；本日报前的状态文档提交：`3211e1d3ca17e0bb6cbc9d7b5b4086d02957ab5a`。
- [成功的 Windows Release](https://github.com/EdwardAiyw/literature-agent/actions/runs/41312375669)；[本日报前最新 main CI](https://github.com/EdwardAiyw/literature-agent/actions/runs/41313176358) 三项作业通过。发布检查已修正 PowerShell 数组计数并保留失败诊断，未移动标签或跳过测试。
- 本机升级备份：`D:/codex/backups/literature-agent/pre-rc7-20261101`。
- 服务器升级备份：`/opt/literature-agent/backups/rc7-20261101T132509Z`；旧镜像 `literature-agent:obsidian-mail-821aac8f09e5` 保留供回退。
- 本机验证证据：`D:/codex/validation/literature-agent/rc7-20261101/`；服务器部署报告：`/opt/literature-agent/validation/rc7-e75abad/deployment.json`。私人日志、数据库和凭据不提交到 GitHub。
- 与本次工作无关的三张历史回归截图、`docs.zip` 和 `docs/SETTINGS.md` 保留原状态，不纳入本次提交。

安装包 SHA-256：

```text
95d593ce0d43e65f55e60830b8a7b0c59b558fb14882246fde3c31f50af86885
```
