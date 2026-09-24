# Literature Agent 0.3.0 UAT 测试报告

## 测试信息

| 项目 | 结果 |
| --- | --- |
| 测试日期 | 2026-09-24 |
| 测试环境 | Windows 11 专业版，64 位，Build 26200 |
| 产品版本 | 0.3.0 |
| Git 分支 / 提交 | `v2/jev-hybrid` / `046e8f7`，含未提交产品改动 |
| 运行方式 | 源码本地服务，`http://127.0.0.1:8001` |
| 数据目录 | `backend/data`（已有数据，不是空白隔离目录） |
| 模型 | DeepSeek `deepseek-chat` |
| SMTP | Resend，SSL 465；凭据未读取或记录 |
| 收件人 | `e***@126.com` |
| Jev | 关闭，使用现有 LLM/规则路径 |
| 当前结论 | 两个 P2 已修复并通过自动化回归；新安装包已通过宿主机隔离冒烟，Windows Sandbox 功能已启用但必须重启后才能完成安装版人工验收 |

## 自动化基线

| 检查 | 结果 | 证据 |
| --- | --- | --- |
| 安装包 SHA-256 | 通过 | 修复后重建值与 `SHA256SUMS.txt` 均为 `4305edc251b5fb0b80464cbf369c4898c5c34b1d5b71ad782ba9262ed2958194` |
| 后端测试 | 通过 | `45 passed, 51 warnings in 54.50s`；新增 100 组 StrictMode 双初始化并发回归 |
| 前端生产构建 | 通过 | TypeScript 与 Vite 构建完成，1878 个模块 |
| Playwright 浏览器回归 | 通过 | `5 passed`；10 次冷加载、3 个视口、4 个页面、快速任务切换 |
| 打包版非默认端口冒烟 | 通过 | 独立数据目录、`8012` 端口，health=ok、首页 HTTP 200、空数据库任务数 0 |
| 健康检查 | 通过 | `status=ok`、数据库可写、worker 已启动、`live=true` |
| 首页 | 通过 | HTTP 200，`text/html; charset=utf-8`，包含 React root |
| 公开设置脱敏 | 通过 | 返回中不存在 API Key、SMTP 密码或来源密钥字段 |
| 更新检查 | 通过 | 当前版本 0.3.0，接口返回 `available=false` |

pytest 的 51 条 warning 均来自当前依赖的弃用提示，本轮没有测试失败。并发用例执行了 200 次完整 bootstrap、共 2,200 个 API 读取，并与 400 次数据库写入并行，结果为 0 个 500 和 0 个虚假 404。

## 配置与来源

| 测试 | 结果 | 说明 |
| --- | --- | --- |
| 首次配置状态 | 通过 | data、llm、smtp、sources、scheduler 五步全部为 true |
| 模型连接 | 通过 | `/api/settings/llm/test` 返回 `status=ok` |
| 无效模型 | 通过 | 不存在的模型返回 HTTP 400，错误中没有密钥 |
| 来源测试 | 部分降级通过 | Crossref、arXiv、PubMed 成功；Semantic Scholar、OpenAlex 当前返回 429 |
| Jev 关闭路径 | 通过 | `jev_enabled=false`，未阻塞检索或订阅 |
| SMTP SSL/STARTTLS 互斥 | 通过 | 无效组合返回 HTTP 422，设置未改变 |

Semantic Scholar 在真实运行中记录 `attempts=4`、`retry_count=3`、`final_http_status=429`，说明退避策略已执行。arXiv 来源测试和本轮真实运行均成功，不再出现 406。

## 手动 UAT 订阅

| 项目 | 结果 |
| --- | --- |
| 订阅 ID | `41f26888-f4b9-402e-9a4e-1e05b9499e82` |
| 订阅名称 | `UAT Agentic RAG 日报 20260924-215708` |
| Run ID | `aaf48dac-6852-41e8-a11c-559057fefb4f` |
| 执行结果 | completed，7/7，无运行级错误 |
| 执行时间 | 21:57:12 至 21:59:03，约 1 分 52 秒 |
| 最终篇数 | 5 |
| 最终来源 | arXiv 2 篇、Crossref 3 篇 |
| 摘要 | 5/5 有摘要 |
| 原文入口 | 5/5 有 `official_url`；arXiv 同时有开放 PDF 地址 |
| 测试邮件记录 | `sent`，Delivery `76d98b7d-1c02-4c55-a49e-7a8931836a7e` |
| 正式日报记录 | `sent` |
| 测试邮件实际到达 | 已由收件人确认 |
| 正式日报实际到达 | 已由收件人确认 |
| 测试后状态 | 已停用，保留运行和投递证据 |

本轮满足“最终 5 篇至少来自两个来源”的硬性门槛。中文订阅名称和邮件主题通过 UTF-8 原始响应核对，没有 `???` 或数据库乱码。

## 自动调度 UAT

| 项目 | 结果 |
| --- | --- |
| 订阅 ID | `ae62b8dd-7129-4c50-bada-8cdf1539a749` |
| 订阅名称 | `UAT 自动调度 20260924-215947` |
| 计划时间 | 21:58，Asia/Hong_Kong |
| Windows 检查时间 | 22:00:01 |
| 自动 Run ID | `4536c3d1-cb6e-4e94-aa22-13ab70423293` |
| 自动触发 | 通过；没有调用手动运行接口 |
| 执行结果 | completed，7/7，5 篇 |
| 最终来源 | arXiv 3 篇、Crossref 2 篇 |
| 自动日报记录 | `sent`，22:01:59 |
| 重复保护 | 通过；再次执行 `--run-due` 显示无到期订阅，运行数保持 1 |
| 自动日报实际到达 | 已由收件人确认 |
| 测试后状态 | 已停用，不会在次日继续发送 |

Windows 任务状态：

- `Literature Agent Daily`：Ready，最近结果 0，下次 22:15。
- `Literature Agent Local`：Ready；当前服务由源码进程运行，登录触发器本轮没有通过重新登录验证。
- “修复”操作执行成功，两项任务仍为 Ready，已有任务、订阅和结果未丢失。

## 数据与管理功能

| 测试 | 结果 | 说明 |
| --- | --- | --- |
| 创建备份 | 通过 | `literature-agent-20260924-220233.db`，585,728 字节 |
| 备份 SHA-256 | 通过 | `AAC869F8521EEB0ECFB7E29BFAB86CF61EEA68C4E21FB819EF3A8D20E54AEBC5` |
| 恢复备份 | 未执行 | 当前使用已有数据目录，恢复会替换数据库；须在隔离目录执行 |
| 任务 CRUD | 通过 | 临时任务创建、编辑、读取、删除成功；删除后返回 404；临时数据已清理 |
| 阅读标记持久化 | 通过 | `unreviewed -> read` 后重新读取仍为 read，随后恢复原值 |
| Prompt 版本 | 通过 | 创建、激活、恢复内置默认、删除自定义版本成功；临时版本已清理 |
| 内置 Prompt 保护 | 通过 | 删除内置版本返回 HTTP 409 |
| 必填字段校验 | 通过 | 空任务名、空来源、无效订阅均返回 HTTP 422 |

## 界面检查

### P2-01：桌面首次加载显示错误横幅

状态：已修复，回归通过。

根因是 FastAPI 多线程并发访问同一个 `sqlite3.Connection`，导致读取游标和事务状态互相干扰。数据库现已用可重入锁串行保护全部共享连接访问；前端首次加载、任务切换和轮询同时增加 AbortController 与请求代次保护。

修复后证据：

- 100 组 React StrictMode 双初始化压力测试通过。
- 10 次 Edge 桌面冷加载均无 `.global-error`。
- 快速点击两个任务后只显示最终选择的任务。

修复前证据仍保留：

- [第一次桌面截图](workspace-desktop.png)
- [第二次桌面截图](workspace-desktop-recheck.png)

### P2-02：390px 窄屏横向溢出

状态：已修复，回归通过。

表单网格现在在 800px 以下改为单列，390px 下导航使用 2 x 2 网格；输入控件和所有关键 grid/flex 子项增加 `min-width: 0`。Playwright 在 390 x 844、768 x 1024、1440 x 1000 三个视口逐页检查，均满足 `scrollWidth <= clientWidth`，四个导航入口全部可见，表单控件未越出视口。

修复后证据：

- [390px 工作台](../p2-regression-20260924/workspace-mobile-fixed.png)
- [768px 工作台](../p2-regression-20260924/workspace-tablet-fixed.png)
- [1440px 工作台](../p2-regression-20260924/workspace-desktop-fixed.png)

修复前证据：[窄屏截图](workspace-mobile.png)

## 尚未执行

以下项目没有在当前已有数据和运行中服务上强行执行：

- Windows Sandbox 安装向导、开始菜单、真实首次设置和卸载：`Containers-DisposableClientVM` 已成功启用，但 Windows 返回 `RestartNeeded=True`；必须重启后执行 `scripts/run-installer-sandbox.ps1`。
- 备份恢复：需要隔离数据目录，避免覆盖当前订阅和历史结果。
- 覆盖升级和卸载：需要安装版隔离环境。
- 断网恢复：本轮没有中断当前正在使用的网络连接。
- Local 登录启动器：需要注销并重新登录 Windows。
- 100%/125% Windows 缩放、键盘 Tab 全流程和真实人工点击：需要交互式桌面测试。
- SMTP/配置测试邮件、手动正式日报和自动调度日报均已由收件人确认实际到达，且对应系统投递记录为 `sent`。

## 当前结论

核心后端和端到端研究流程通过：模型可用、arXiv 恢复、Semantic Scholar 退避生效、最终 5 篇来自至少两个来源、测试/正式/自动邮件均由 SMTP 接受、Windows Daily 自动触发成功、重复保护有效。

测试结束后，两个名称以 `UAT` 开头的订阅已停用；原有 `Agentic RAG 日报` 正式订阅保持启用，时间仍为 08:00。

两个 P2 已完成修复，后端并发、浏览器冷加载和响应式布局回归全部通过，新安装包及校验文件已经重建，打包版也在独立数据目录和非默认端口完成宿主机冒烟。

当前仍不能标记“正式发布通过”，唯一发布阻塞是 Windows Sandbox 在启用后要求重启。重启完成后运行 `scripts/run-installer-sandbox.ps1`，在 Sandbox 页面手工输入临时模型/SMTP 凭据，并按 `docs/INSTALLER_SANDBOX_TEST.md` 完成五篇两来源、邮件、计划任务、备份恢复和卸载验收。
