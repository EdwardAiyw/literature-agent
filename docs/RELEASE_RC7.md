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

来源覆盖、API 和凭据规则见 [SOURCES.md](SOURCES.md)，Obsidian 见 [OBSIDIAN.md](OBSIDIAN.md)，服务器操作见 [SERVER_DEPLOYMENT.md](SERVER_DEPLOYMENT.md)。最终发布、安装校验和部署证据将在完成后记录于本页。
