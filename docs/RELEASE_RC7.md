# Literature Agent 0.3.0-rc.7

RC7 将文献来源管理做成产品设置，Windows 安装版和 Linux 服务器共用配置行为；同时将此前的 Obsidian 文库设置与完整邮件归档纳入安装包。此版本保留 prerelease 状态。

## 功能

- “设置 → 文献来源”支持添加、配置、测试、启停和移除来源，保存密钥、逐来源每日请求上限，以及新任务/订阅的默认选择。
- 支持 11 种连接：Semantic Scholar、OpenAlex、Crossref、arXiv、PubMed、DOAJ、DataCite、HAL、Europe PMC、Google Scholar（SerpApi）、CORE。9 个开放来源默认添加；Google Scholar 和 CORE 须用户添加并填写服务密钥。
- 停用来源在缓存读取和 HTTP 请求前跳过；已有任务和订阅保留原选择。检测状态和错误不回显密钥，HTTPX 查询参数日志脱敏。
- 新适配器保留日期精度、跨来源标识、缓存、请求预算及部分结果。Google Scholar 搜索片段与作者摘要分开保存，不将片段当作证据摘要。
- Windows 设置页内置 Obsidian 文库连接、立即同步、独立自动任务和状态；归档完整邮件、来源诊断、去重信息、JIF 与标识符附件，保留个人批注。

## 安装与升级

从 [RC7 Release](https://github.com/EdwardAiyw/literature-agent/releases/tag/v0.3.0-rc.7) 下载 `Literature-Agent-0.3.0-rc.7-Windows-x64.exe` 和 `SHA256SUMS.txt`。核验后退出旧程序并覆盖安装，保留原安装位置、数据目录和 Windows 凭据。升级前创建一致性数据库备份并单独备份设置；本次没有新增数据库迁移，数据库仍为 `20261018_0006`。

服务器需单独构建固定镜像并更新 Compose，保留现有数据卷。更新 GitHub 不会自动升级用户设备。历史 RC6 标签及资产不变。

## 验证和限制

- 2026-11-01 本机通过 299 项后端测试、前端生产构建和 36 项完整 Edge 回归，包含来源管理、Obsidian、Zotero、订阅和响应式页面。
- Windows 发布工作流执行全量测试和打包程序检查，新增 11 来源目录、配置保存、移除重加及 Obsidian 接口检查。
- DOAJ、DataCite、HAL、Europe PMC 各完成一次 HTTP 200、两条记录的真实 API 验证。Google Scholar 和 CORE 的授权真实检索尚未提供用户密钥，以模拟接口及公开样例验证；在页面测试自己的权限及额度。
- RC7 干净系统首次设置、自然调度及外部邮箱收件仍需人工验收；不复用历史 RC6 的实机检索作为本版检索验收。升级验证不触发新的检索、邮件或 Zotero 导入。

来源覆盖、API 和凭据规则见 [SOURCES.md](SOURCES.md)，Obsidian 见 [OBSIDIAN.md](OBSIDIAN.md)，服务器操作见 [SERVER_DEPLOYMENT.md](SERVER_DEPLOYMENT.md)。

## 2026-11-01 发布与升级验证

- 不可变标签 `v0.3.0-rc.7` 指向 `e75abade0862ecd39337948b65ca23052f8a87af`。[源码 CI](https://github.com/EdwardAiyw/literature-agent/actions/runs/41310862092) 成功；发布检查脚本由后续提交 `ec4cc8a` 修正 PowerShell 数组计数并补充失败诊断，标签未移动。
- [Windows Release](https://github.com/EdwardAiyw/literature-agent/actions/runs/41312375669) 使用该标签源码构建并成功发布：**299 项后端测试、36 项完整 Edge 回归、前端构建、安装包构建和打包程序检查全部通过**。早期一次订阅编辑超时未在本机 10 轮重复或后续完整回归中复现；没有跳过测试。
- [公开安装包](https://github.com/EdwardAiyw/literature-agent/releases/download/v0.3.0-rc.7/Literature-Agent-0.3.0-rc.7-Windows-x64.exe) **29,420,269 字节**。匿名重新下载后，SHA-256 与同一 Release 的 `SHA256SUMS.txt`、GitHub 资产摘要三方一致：

```text
95d593ce0d43e65f55e60830b8a7b0c59b558fb14882246fde3c31f50af86885
```

- 本机覆盖安装返回 0，注册表及运行健康接口均为 RC7。原 D 盘安装位置、E 盘数据目录保留；17 张表内容、设置、bootstrap 及 Windows 凭据哈希一致。Local/Daily 任务继续停用，既有 Obsidian 任务保持原配置与状态；安装版通过用户环境变量复用已有 Obsidian 配置及笔记映射。备份：`D:/codex/backups/literature-agent/pre-rc7-20261101`。
- 服务器运行镜像 `literature-agent:rc7-e75abad`，健康且内部调度正常。17 张表及设置、密钥、Compose、LocalJev 配置哈希保留，恢复原调度开关，既有订阅来源不自动扩大。备份：`/opt/literature-agent/backups/rc7-20261101T132509Z`；保留旧镜像。最终 Linux 镜像隔离通过 **298 项后端测试，1 项 Windows 文件锁检查跳过**。
- 真实安装版与正式服务器均通过桌面/390px 手机页面验证：9 个已添加来源、Google Scholar/CORE 添加配置入口、空白密码框、无横向溢出、无页面错误。只读验证没有触发配置写入、检索、发信或 Zotero 导入。

本机完整证据保存在 `D:/codex/validation/literature-agent/rc7-20261101/`；服务器部署报告为 `/opt/literature-agent/validation/rc7-e75abad/deployment.json`。历史 RC6 安装与检索记录保持原样。
