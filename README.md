# Literature Agent

把研究主题变成可追踪的每日文献邮件。

[English](README.en.md) · [Windows 下载](https://github.com/EdwardAiyw/literature-agent/releases/tag/v0.3.0-rc.6) · [服务器部署](docs/SERVER_DEPLOYMENT.md) · [使用指南](docs/WINDOWS_USER_GUIDE.md) · [反馈](https://github.com/EdwardAiyw/literature-agent/issues)

Literature Agent 是面向个人研究者的开源文献助手。输入研究主题、日期和来源后，它会检索论文、合并跨来源记录、筛选相关文献、生成研究摘要，并保留结果、运行过程和邮件投递记录。支持 Windows 本机使用和自有 Linux 服务器常驻运行。

## 版本与使用方式

**截至 2026-10-18，RC6 Windows 安装包、对应源码和已升级服务器均包含历史推送去重、动态日期、自动 Zotero 集合导入及官网 JIF 查询。**

| 使用方式 | 适合谁 | 功能范围 |
| --- | --- | --- |
| [Windows RC6 安装包](https://github.com/EdwardAiyw/literature-agent/releases/tag/v0.3.0-rc.6) | 希望直接安装的测试用户 | 每日历史去重、动态日期、自动 Zotero 集合导入、官网 JIF，以及既有工作台和 Prompt v2 |
| 最新 `main` 源码 | 开发者与需要新增功能的用户 | 包含下文全部已实现能力 |
| [Linux Docker 部署](docs/SERVER_DEPLOYMENT.md) | 希望电脑关机后仍每日运行的用户 | 自行构建源码镜像，通过 SSH 隧道管理网页 |

RC6 是预发布测试版。已通过 26 项 Sandbox 安装生命周期检查，并完成现有 Windows 安装覆盖升级、数据一致性核对及安装版真实五篇检索；干净系统首次设置、自然调度触发和外部邮箱到达仍需人工验收。详见 [安装验收记录](docs/INSTALLER_RC6_VALIDATION_2026-10-18.md)。Windows 与 Linux 使用同一版本源码，分别安装或部署；更新 GitHub 不会自动升级已安装程序。旧 RC5 标签和资产保持不变。

## 能做什么

- **多来源检索**：Semantic Scholar、OpenAlex、Crossref、arXiv、PubMed，支持中英文检索和日期范围。
- **筛选与摘要**：规划查询、判断相关性、生成结构化摘要，可选证据核查；保留实际检索式、Prompt 快照及来源诊断。
- **每日邮件**：按订阅时区运行，发送 HTML/纯文本摘要、DOI 与原文链接，记录投递结果。
- **持续选文**：合并本次重复记录，排除本订阅之前成功推送的论文，也可继续补充未推送过的历史文献。
- **Zotero**：逐篇导入，或指定已有集合自动导入；支持进度、失败重试和邮件标识符 TXT。
- **Obsidian**：设置页发现并选择文库，保存本机或服务器连接，立即同步、启停自动同步、查看状态并打开索引；重复导入复用论文笔记，保留个人批注。功能已内置 `main`，详见 [Obsidian 连接](docs/OBSIDIAN.md)；已发布 RC6 安装包尚不包含此入口。
- **期刊指标**：查询可核实的官网 JIF 并标注年份、来源，也可导入已有 JCR CSV；查询失败不阻断邮件。
- **运行管理**：页面配置模型、SMTP、来源、备份、订阅和 Prompt 版本；可选 LocalJev 决策审计。

摘要和相关性分数辅助阅读，引用前仍需核对原文。程序不下载或发送 PDF，也不绕过付费墙。

## 快速开始

### Windows 安装版

1. 从 [RC6 Release](https://github.com/EdwardAiyw/literature-agent/releases/tag/v0.3.0-rc.6) 下载 `Literature-Agent-0.3.0-rc.6-Windows-x64.exe` 和 `SHA256SUMS.txt`，核对校验值。
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
3. 对剩余候选筛选、摘要并按需核查证据，最多选出 10 篇。
4. 发送邮件并记录成功推送历史，随后处理已启用的 Zotero 自动导入。

**目标篇数是上限。** 不足时按实际数量发送，无新增时发送说明，不用旧论文凑数。10 篇是可配置的订阅目标，其他用户可自行设置。

- 使用规范化 DOI、PMID、去版本号 arXiv ID、来源 ID 和保守标题/作者匹配；元数据不完整仍可能漏判。
- 历史按订阅隔离；更换收件人不清空历史，不同订阅可以推送同一论文。普通单次任务只做本次去重。
- 测试邮件、失败投递和 `--no-send` 不占用论文。
- 新订阅默认截止到运行当天，旧订阅保留固定日期策略，可在页面切换。
- 常规调度与“手动运行”共用当地自然日限制，活动任务阻止重叠。SMTP 成功表示服务器接受邮件，不等于收件箱确认收件。

机制、迁移、诊断与发送边界见 [每日去重与日期策略](docs/DAILY_DEDUPLICATION.md)。

## 数据与运行边界

| 内容 | 保存方式 |
| --- | --- |
| 任务、论文、运行、投递与去重历史 | 数据目录中的 `literature_agent_v2.db`，SQLite WAL，Alembic 自动迁移 |
| 普通配置 | 同目录 `settings.json` |
| Windows 密钥 | 当前用户 Windows Credential Manager |
| Linux 服务器密钥 | 数据卷内权限受限的明文 `secrets.json`，备份也需保护 |
| 外部请求 | 查询及论文元数据发给所选来源与模型，邮件经配置的 SMTP 发出 |

数据库备份不包含全部配置与密钥，应单独保管。避免网盘实时同步运行中的 SQLite，使用一致性备份，不能遗漏 WAL。Windows 与服务器没有双向数据同步。

来源可能限流或返回部分结果，页面展示来源诊断。JIF 覆盖取决于出版商页面，预印本和会议论文通常不适用；不会用 CiteScore 或模型猜测代替。LocalJev 默认关闭，已验证服务器保持 Shadow，主动筛选尚未通过质量门槛。

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

打开 <http://127.0.0.1:8001>，在设置页配置真实调用。源码默认离线，`.env` 保留用于开发和迁移，不要提交真实密钥。

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

RC6 发布通过 Windows/Linux **245 项后端测试**、前端构建、Windows **32 项完整 Edge 回归**及打包程序检查；公开安装包重新下载校验一致，详见 [RC6 发布记录](docs/RELEASE_RC6.md)。真实补发选出 10 篇，按当前身份规则核对未与历史重复，SMTP 接受成功，10 篇 Zotero 自动导入完成。这是本次运行的验证，不代表未来检索都能凑齐目标数量。详见 [验证记录](docs/DAILY_DEDUPLICATION.md)。

```powershell
cd backend
./.venv/Scripts/python.exe -m pytest -q
cd ../frontend
npm run build
npm run test:e2e
```

浏览器测试需 Windows Edge 和 `backend/.venv`，使用独立端口 `8011` 和测试数据，关闭真实模型/邮件调用。不要提交测试产物、密钥或个人数据库。

## 文档导航

| 主题 | 文档 |
| --- | --- |
| 安装与排错 | [Windows 指南](docs/WINDOWS_USER_GUIDE.md) · [服务器部署与回退](docs/SERVER_DEPLOYMENT.md) |
| 每日选文 | [历史去重与日期](docs/DAILY_DEDUPLICATION.md) |
| Zotero 与 JIF | [导入和附件](docs/ZOTERO.md) · [期刊指标](docs/JOURNAL_METRICS.md) |
| Obsidian | [文库连接、自动同步与排错](docs/OBSIDIAN.md) |
| Prompt 与 LocalJev | [Prompt 系统](docs/PROMPT_SYSTEM.md) · [LocalJev](docs/LOCALJEV.md) · [质量验证](docs/LOCALJEV_CLOUD_VALIDATION_2026-10-16.md) |
| 开发与运维 | [架构](docs/ARCHITECTURE.md) · [运行手册](docs/V2_OPERATIONS_MANUAL.md) · [Windows 发布](docs/WINDOWS_RELEASE.md) |
| 进展与验收 | [当前状态](docs/CURRENT_STATE.md) · [更新日志](CHANGELOG.md) · [测试指南](TEST_GUIDE.md) |

## 反馈与许可

通过 [GitHub Issues](https://github.com/EdwardAiyw/literature-agent/issues/new?template=bug_report.yml) 或 [邮件](mailto:aiyuling.usm@gmail.com) 提交版本、复现步骤、运行 ID 和脱敏截图。漏洞遵循 [安全政策](SECURITY.md)，贡献代码见 [贡献指南](CONTRIBUTING.md)。

采用 [GNU AGPL-3.0](LICENSE) 许可，按现状提供，不作担保。
