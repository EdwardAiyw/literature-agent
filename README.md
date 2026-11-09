# Literature Agent

把研究主题变成可追踪的每日文献邮件。

[English](README.en.md) · [Windows 下载](https://github.com/EdwardAiyw/literature-agent/releases/tag/v0.3.0-rc.7) · [服务器部署](docs/SERVER_DEPLOYMENT.md) · [使用指南](docs/WINDOWS_USER_GUIDE.md) · [反馈](https://github.com/EdwardAiyw/literature-agent/issues)

Literature Agent 是面向个人研究者的开源文献助手。输入研究主题、日期和来源后，它会检索论文、合并跨来源记录、筛选相关文献、生成研究摘要，并保留结果、运行过程和邮件投递记录。当前源码支持在正常检索无新增时暂停订阅，并完整汇总历次成功推送的文献。支持 Windows 本机使用和自有 Linux 服务器常驻运行。

## 版本与使用方式

**2026-11-09 更新：正常检索无新增时暂停订阅，单独发送暂停通知，再发送历史文献完整汇总。** 已合入 `main` 并部署到现用 Linux 服务器；已发布的 Windows 安装包仍为 RC7。

| 使用方式 | 适合谁 | 功能范围与更新方式 |
| --- | --- | --- |
| [Windows RC7 安装包](https://github.com/EdwardAiyw/literature-agent/releases/tag/v0.3.0-rc.7) | 希望直接安装的测试用户 | 含 11 种来源管理、Obsidian、完整邮件归档、推送去重、Zotero 和 JIF；未包含自动暂停与历史汇总 |
| 当前 `main` 源码 | 开发者与需要新增功能的用户 | 包含本文全部能力；拉取更新后重新构建前端并重启服务 |
| [Linux Docker 部署](docs/SERVER_DEPLOYMENT.md) | 希望电脑关机后仍每日运行的用户 | 从所选提交构建并切换镜像，通过 SSH 管理；现用服务器已部署本次优化，其他部署需分别升级 |

RC7 仍是预发布测试版，本次优化归入 **Unreleased**，没有发布新 Windows 安装包或移动旧标签。RC7 功能与发布验证见 [发布记录](docs/RELEASE_RC7.md)，当前服务器的源码提交、镜像及备份见 [部署记录](docs/SERVER_DEPLOYMENT.md)。更新 GitHub 不会自动升级已安装程序或其他服务器。

## 能做什么

- **可配置文献来源**：在设置页添加、配置、测试和启停来源，管理密钥、默认选择与请求上限；支持 9 个开放来源，以及可选的 Google Scholar（SerpApi）和 CORE，共 11 种连接。详见[覆盖与接入说明](docs/SOURCES.md)。
- **筛选与摘要**：规划查询、判断相关性、生成结构化摘要，可选证据核查；保留实际检索式、Prompt 快照及来源诊断。
- **每日邮件**：按订阅时区运行，发送 HTML/纯文本摘要、DOI 与原文链接，记录投递结果。
- **持续选文**：合并本次重复记录，排除本订阅之前成功推送的论文，也可继续补充未推送过的历史文献。
- **无新增时暂停（当前源码/已升级服务器）**：正常检索和处理后为 0 篇时停止该订阅的后续自动执行，分别发送暂停通知与历史汇总；来源或模型异常不触发自动暂停。
- **历史文献汇总（当前源码/已升级服务器）**：覆盖本订阅全部成功日报，生成带编号引用的主题、方法、发现、联系与分歧及后续建议，附完整逐篇清单和 Markdown 报告；页面支持下载、失败重试与恢复订阅。
- **Zotero**：逐篇导入，或指定已有集合自动导入；支持进度、失败重试和邮件标识符 TXT。
- **Obsidian**：设置页发现并选择文库，保存本机或服务器连接，立即同步、启停自动同步、查看状态并打开索引；重复导入复用论文笔记，保留个人批注。RC7 安装版内置此入口，详见 [Obsidian 连接](docs/OBSIDIAN.md)。
- **邮件归档到文库**：同步完整邮件正文、来源诊断、去重统计、JIF 与标识符 TXT 附件；后续推送保存发送时快照，旧邮件明确标注重建来源。
- **期刊指标**：查询可核实的官网 JIF 并标注年份、来源，也可导入已有 JCR CSV；查询失败不阻断邮件。
- **运行管理**：页面配置模型、SMTP、来源、备份、订阅和 Prompt 版本；可选 LocalJev 决策审计。

支持的来源为 Semantic Scholar、OpenAlex、Crossref、arXiv、PubMed、DOAJ、DataCite、HAL、Europe PMC，以及需独立密钥的 Google Scholar（SerpApi）和 CORE。来源启用、权限、预算与覆盖限制见 [来源说明](docs/SOURCES.md)。

摘要、相关性分数和历史汇总依据实际保存的元数据、摘要与简报，引用前仍需核对原文。程序不下载或发送 PDF，也不绕过付费墙。

## 快速开始

### Windows 安装版

1. 从 [RC7 Release](https://github.com/EdwardAiyw/literature-agent/releases/tag/v0.3.0-rc.7) 下载 `Literature-Agent-0.3.0-rc.7-Windows-x64.exe` 和 `SHA256SUMS.txt`，核对校验值。
2. 安装并启动，打开 <http://127.0.0.1:8001>。无需 Python 或 Node.js。
3. 在“设置”选择数据目录，填写模型服务、SMTP 邮箱和来源，测试并保存。
4. 注册 Windows 自动任务，完成首次设置后执行一次小规模检索。
5. 创建每日订阅，或将已有任务转为每日任务；先发测试邮件，再验证正式运行。

需要可用的 OpenAI-compatible 模型 API Key；发邮件需要 SMTP 授权码或应用密码。相关服务费用由服务商决定。详细安装、设置、备份及排错见 [Windows 使用指南](docs/WINDOWS_USER_GUIDE.md)。

### Linux 服务器

按 [部署手册](docs/SERVER_DEPLOYMENT.md) 构建镜像并配置持久数据卷。服务器每 60 秒检查到期订阅，本机无需保持开机。Compose 默认只发布服务器回环端口 `18081`。

配置 SSH 密钥并核对主机指纹后，从项目根目录连接已有服务器：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/open-server.ps1 -Target user@server
```

脚本建立隧道后打开 <http://127.0.0.1:18001>。服务器为单用户应用，没有登录系统，应保持回环绑定并通过 SSH 访问。迁移后停用原电脑的自动任务，由服务器统一管理订阅。

## 每日选文规则

例如将订阅设为每天 `07:00`、`Asia/Hong_Kong`、目标 **10 篇**：

1. 按主题、起始日期及来源检索；“截止到运行当天”策略每天推进截止日，也可选固定日期。
2. 合并当前重复记录，再排除这个订阅已成功发送过的论文。
3. 对剩余候选筛选、摘要并按需核查证据，最多选出 10 篇；目标篇数由订阅配置。
4. 有符合要求的文献时发送日报并记录成功推送历史，随后处理已启用的 Zotero 自动导入。
5. 当前源码/已升级服务器在检索与处理正常且结果为 0 篇时，转入下文的暂停与汇总流程；来源或模型异常时保留订阅并展示诊断。

**目标篇数是上限。** 不足时按实际数量发送，不用已推送论文凑数；10 篇是示例，其他用户可自行设置。RC7 安装包在零篇时仍发送原有空结果说明，自动暂停与历史汇总需当前源码或已升级的服务器。

- 使用规范化 DOI、PMID、去版本号 arXiv ID、来源 ID 和保守标题/作者匹配；元数据不完整仍可能漏判。
- 历史按订阅隔离；更换收件人不清空历史，不同订阅可以推送同一论文。普通单次任务只做本次去重。
- 测试邮件、失败投递和 `--no-send` 不占用论文。
- 新订阅默认截止到运行当天，旧订阅保留固定日期策略，可在页面切换。
- 常规调度与“手动运行”共用当地自然日限制，活动任务阻止重叠。SMTP 成功表示服务器接受邮件，不等于收件箱确认收件。

机制、迁移、诊断与发送边界见 [每日去重与日期策略](docs/DAILY_DEDUPLICATION.md)。

## 无新增时自动暂停与完整汇总

自动触发要求正式订阅运行完成、所有选定来源均为正常或缓存成功、没有来源或模型处理错误，并且最终为 **0 篇**。来源失败、部分成功、限流、停用、缺少配置或诊断，以及模型异常都不触发。普通单次任务、演示数据、SMTP 测试和 `--no-send` 不触发。暂停只影响当前订阅，也不表示整个研究领域没有新论文。

触发后依次执行：

1. **暂停后续执行**：保存暂停状态及本次汇总的历史资料快照，调度器随后跳过该订阅。
2. **单独发送暂停通知**：说明原因、时间、历史日报数、文献数及恢复方法，不再继续每天发送空日报。
3. **发送历史汇总**：读取本订阅历次成功正式日报，去重后分批分析、分层合并，另发汇总邮件；不受页面历史列表 50/100 条限制。失败邮件、测试邮件及通知/汇总邮件不进入文献范围或消耗推送历史。

报告包含研究主题、主要方法与发现、文献之间的联系与分歧、此资料集合中的不足与后续建议，使用 `[P0001]` 等编号关联完整逐篇清单。附录保留可用的原始摘要、已保存简报、证据提示、元数据和原文链接；早期邮件重建来源与缺失记录明确标注。附件包括 `literature-history-report.md`，有可靠编号时另附 `zotero-identifiers.txt`。

| 在“每日订阅”中操作 | 结果 |
| --- | --- |
| 查看暂停状态 | 显示原因、暂停时间、历史篇数及通知/汇总状态 |
| 下载完整报告 | 生成后即可下载，即使汇总邮件投递失败也可取回 |
| 点击“重试通知与汇总” | 仅继续失败部分，复用已完成批次和报告，跳过已成功记录的邮件；不重新检索或导入 Zotero |
| 汇总完成或失败后，编辑订阅并勾选“启用每日自动执行” | 保存后恢复调度，保留历史推送去重；可先调整主题、日期或来源 |

暂停立即生效，通知或汇总失败不会重新启用订阅。服务重启会恢复中断的排队/运行中汇总；已明确失败的任务需要主动重试。汇总进行中阻止同任务新运行及删除等冲突操作。JSON、章节、引用编号或输出长度校验失败时，模型最多纠错一次，仍无效则保留缓存并报告失败。

报告基于已保存摘要与简报，**未读取论文全文**；引用校验不等于独立核实全部研究结论。已有最近一次完成的零篇运行，可按用户明确要求通过 `POST /api/subscriptions/{id}/closure/start` 暂停并汇总，保留来源提示而不重跑检索。接口、错误码、重试、下载和恢复细节见 [完整说明](docs/SUBSCRIPTION_CLOSURE.md)。

## 数据与运行边界

| 内容 | 保存方式 |
| --- | --- |
| 任务、论文、运行、投递与去重历史 | 数据目录中的 `literature_agent_v2.db`，SQLite WAL，Alembic 自动迁移 |
| 暂停记录、汇总资料快照、批次缓存与报告 | 同一数据库的订阅与运行产物；删除订阅会删除其历史和报告，应先下载留存 |
| 普通配置 | 同目录 `settings.json` |
| Windows 密钥 | 当前用户 Windows Credential Manager |
| Linux 服务器密钥 | 数据卷内权限受限的明文 `secrets.json`，备份也需保护 |
| 外部请求 | 查询发给所选来源；论文元数据、摘要及汇总材料发给配置的模型；日报、通知及报告经配置的 SMTP 发出 |

数据库备份不包含全部配置与密钥，应单独保管。避免网盘实时同步运行中的 SQLite，使用一致性备份，不能遗漏 WAL。Windows 与服务器没有双向数据同步。

来源可能限流或返回部分结果，页面展示来源诊断。JIF 覆盖取决于出版商页面，预印本和会议论文通常不适用；不会用 CiteScore 或模型猜测代替。LocalJev 默认关闭，已验证服务器保持 Shadow，主动筛选尚未通过质量门槛。

历史汇总会增加模型调用与邮件体积，费用和投递大小限制取决于服务商。成功落库的邮件在重试时跳过；SMTP 已接受、进程尚未记账就退出的窗口仍可能重复发送，无法保证严格的恰好一次投递。

## 从源码运行

要求 **Python 3.12+、Node.js 22 和 npm**。Windows PowerShell：

```powershell
git clone https://github.com/EdwardAiyw/literature-agent.git
cd literature-agent
python -m venv backend/.venv
./backend/.venv/Scripts/python.exe -m pip install -e "./backend[dev]"
cd frontend
npm ci
npm run build
cd ..
./backend/.venv/Scripts/python.exe -m literature_agent.launcher --port 8001
```

打开 <http://127.0.0.1:8001>，在设置页配置并启用真实检索、模型与 SMTP。未配置的源码默认离线；已有设置会继续生效。`.env` 保留用于开发和迁移，不要提交真实密钥。更新已有源码部署前先备份数据及配置，执行 `git pull` 后按上面的步骤安装依赖、重新构建前端并重启；Linux 镜像升级按部署手册执行。

开发前端时，在两个窗口分别运行：

```powershell
# 窗口一，从项目根目录开始
cd backend
./.venv/Scripts/python.exe -m uvicorn literature_agent.api:app --host 127.0.0.1 --port 8001
```

```powershell
# 窗口二，从项目根目录开始
cd frontend
npm run dev
```

开发页面为 <http://127.0.0.1:5175>，Vite 将 `/api` 代理到后端。更多配置见 [高级运行手册](docs/V2_OPERATIONS_MANUAL.md)。

## 验证与开发

截至 **2026-11-09**，各项验证范围如下：

| 范围 | 结果与边界 |
| --- | --- |
| 当前源码后端 | **328 项通过**，覆盖暂停条件、历史覆盖、事务回滚、缓存续做、模型纠错、邮件重试和接口行为 |
| 当前服务器最终镜像 | 隔离环境 **327 项通过、1 项 Windows 专用测试跳过**；部署保留全部 17 张表与设置/密钥，worker、调度器健康 |
| 前端与 GitHub CI | 生产构建、新增 Edge 手机交互 **1 项通过**；功能与修复提交的后端、前端和 LocalJev CI 通过 |
| 实际历史汇总 | 26 封成功日报、322 条记录合并为 **235 篇身份记录**，无历史缺失；235 个逐篇条目与两个附件核验通过，暂停通知和汇总均被 SMTP 接受，收件箱未核验 |
| 已发布 Windows RC7 | 历史发布基线为 **299 项后端、36 项完整 Edge 回归**及打包检查；该安装包不含本次优化 |

详细记录见 [自动暂停与汇总验收](docs/SUBSCRIPTION_CLOSURE.md)、[服务器部署](docs/SERVER_DEPLOYMENT.md) 和 [RC7 发布记录](docs/RELEASE_RC7.md)。自动化测试使用模拟模型/SMTP；实际汇总验证不等于科学结论已独立核实，也不保证其他来源、模型或邮箱的可用性。RC7 干净系统首次设置、自然调度及外部收件箱仍按 [测试指南](TEST_GUIDE.md) 单独验收。

在独立测试数据目录与 bootstrap 配置下运行，避免使用生产设置；隔离方法见 [测试指南](TEST_GUIDE.md#18-开发者自动化测试附录)：

```powershell
cd backend
./.venv/Scripts/python.exe -m pytest -q
cd ../frontend
npm run build
npm run test:e2e
```

浏览器测试需 Windows Edge 和 `backend/.venv`，使用独立端口 `8011` 和测试数据，关闭真实模型/邮件调用。不要提交测试产物、密钥或个人数据库。

## 项目结构

| 路径 | 内容 |
| --- | --- |
| `backend/src/literature_agent/` | FastAPI 接口、工作流、来源、调度、邮件、历史汇总和数据访问 |
| `backend/alembic/`、`backend/tests/` | SQLite 迁移与后端测试 |
| `frontend/` | React / TypeScript / Vite 网页及 Playwright 交互测试 |
| `deploy/` | Linux Docker / Compose 与可选 LocalJev 服务 |
| `scripts/`、`packaging/` | SSH 连接、自动任务、验收与 Windows 打包辅助工具 |
| `docs/` | 功能、接口、运维、发布及验收记录 |

## 文档导航

| 主题 | 文档 |
| --- | --- |
| 安装与排错 | [Windows 指南](docs/WINDOWS_USER_GUIDE.md) · [服务器部署与回退](docs/SERVER_DEPLOYMENT.md) |
| 来源与每日选文 | [11 种来源与配置](docs/SOURCES.md) · [历史去重与日期](docs/DAILY_DEDUPLICATION.md) |
| 自动暂停与历史汇总 | [触发条件、邮件、完整报告、重试及恢复](docs/SUBSCRIPTION_CLOSURE.md) |
| Zotero 与 JIF | [导入和附件](docs/ZOTERO.md) · [期刊指标](docs/JOURNAL_METRICS.md) |
| Obsidian | [文库连接、自动同步与排错](docs/OBSIDIAN.md) |
| Prompt 与 LocalJev | [Prompt 系统](docs/PROMPT_SYSTEM.md) · [LocalJev](docs/LOCALJEV.md) · [质量验证](docs/LOCALJEV_CLOUD_VALIDATION_2026-10-16.md) |
| 开发与运维 | [架构](docs/ARCHITECTURE.md) · [运行手册](docs/V2_OPERATIONS_MANUAL.md) · [Windows 发布](docs/WINDOWS_RELEASE.md) |
| 进展与验收 | [当前状态](docs/CURRENT_STATE.md) · [路线图](docs/ROADMAP.md) · [更新日志](CHANGELOG.md) · [测试指南](TEST_GUIDE.md) |

## 反馈与许可

通过 [GitHub Issues](https://github.com/EdwardAiyw/literature-agent/issues/new?template=bug_report.yml) 或 [邮件](mailto:aiyuling.usm@gmail.com) 提交版本、复现步骤、运行 ID 和脱敏截图。漏洞遵循 [安全政策](SECURITY.md)，贡献代码见 [贡献指南](CONTRIBUTING.md)。

采用 [GNU AGPL-3.0](LICENSE) 许可，按现状提供，不作担保。
