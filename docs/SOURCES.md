# 文献来源

RC7 的“设置 → 文献来源”提供 11 种可配置连接，适用于 Windows 安装版和 Linux 服务器。9 个开放来源默认添加；Google Scholar（SerpApi）和 CORE 可通过“添加来源”配置密钥后启用。历史 RC6 安装包不包含来源管理功能，升级入口见 [RC7 发布说明](RELEASE_RC7.md)。

| 来源 | 主要覆盖 | 接口与凭据 |
| --- | --- | --- |
| Semantic Scholar | 跨学科论文、摘要和引用信息 | [Graph API](https://api.semanticscholar.org/api-docs/graph)，可选 API Key |
| OpenAlex | 跨学科论文和学术元数据 | [Works API](https://docs.openalex.org/api-entities/works)，支持 API Key |
| Crossref | DOI 注册的期刊、会议等出版元数据 | [REST API](https://www.crossref.org/documentation/retrieve-metadata/rest-api/)，使用联系邮箱进入 polite pool |
| arXiv | 计算机、数学、物理等领域预印本 | [API](https://info.arxiv.org/help/api/index.html)，无需密钥 |
| PubMed | 医学、生物和健康研究 | [E-utilities](https://www.ncbi.nlm.nih.gov/books/NBK25501/)，可选 API Key 和联系邮箱 |
| DOAJ | 跨学科开放获取期刊文章 | [Search API](https://doaj.org/api/docs)，无需密钥 |
| DataCite | 机构仓储、预印本、学位论文及其他文字类学术成果 | [Public API](https://support.datacite.org/docs/api)，无需密钥 |
| HAL | 跨学科机构仓储、会议论文和学位论文 | [Search API](https://api.archives-ouvertes.fr/docs/search)，无需密钥 |
| Europe PMC | 生命科学与医学文章、预印本和开放全文链接 | [REST API](https://europepmc.org/RestfulWebService)，无需密钥 |
| Google Scholar | 跨学科文献检索与引用线索 | [SerpApi](https://serpapi.com/google-scholar-api) 第三方接口，需要其 API Key 和可用额度 |
| CORE | 跨学科开放获取机构仓储 | [官方 API](https://core.ac.uk/services/api)，需要申请 API Key |

在“设置 → 文献来源”点击“添加来源”，选择检索服务，填写该服务的凭据、每日请求上限，并选择是否默认用于新任务和新订阅，保存后生效。每个已添加来源都可配置、启停、测试连接或移除。密钥输入框不回显已保存的值；留空保持原密钥，清除密钥使用单独的“清除已保存密钥并停用”操作。PubMed 的联系邮箱可在其配置中修改。

任务和订阅的来源选择随后台配置变化，只提供已添加、已启用且满足凭据要求的来源。新建任务和订阅使用用户保存的默认来源，而非把所有来源自动勾选。所有默认来源都关闭时，新建任务会提示先配置或选择来源。已有任务、订阅保留来源选择；被停用或移除的来源在检索时明确标记跳过，缓存也不会绕过停用设置。编辑已有任务时可取消其已停用来源。

“测试连接”对当前已保存配置执行一次小规模真实检索，绕过查询缓存，并计入该来源的每日请求上限。页面保存最近检测时间、结果数量和失败原因；零条结果的成功 HTTP 请求只代表接口可访问，不保证当前主题有文献。配置密钥变化会清除旧检测状态。移除来源会停用连接，保留密钥以便重新添加；已有研究结果不受影响。

桌面版密钥沿用 Windows 凭据库，服务器版沿用受限文件；非秘密的来源偏好保存在数据目录的 `settings.json`。每来源上限留空则继承全局每来源每日请求预算。`SERPAPI_API_KEY`、`CORE_API_KEY` 也可作为环境配置，但来源仍须在页面添加并启用。来源测试与检索错误不包含 API Key；HTTPX 请求日志中的查询参数密钥也会脱敏。

DataCite 仅查询 Text、Preprint、JournalArticle、ConferencePaper、Dissertation、Book、BookChapter 和 Report 类型；数据集、软件等非文字成果不进入候选集。HAL 限于文章、会议论文、预印本、学位论文、报告和书籍章节等文献类型。

各来源可能索引同一篇文章。结果沿用 DOI、PMID、arXiv ID 和保守标题/作者匹配去重；增加来源数量不等于增加相同比例的独立论文。Europe PMC 使用带原始数据库前缀的来源 ID，MED 记录同时保留 PMID；HAL 保留可用的 PMID 和 arXiv ID，供跨来源匹配。

日期按发表日期处理，不用仓储创建或更新日期代替。只提供年份或月份的记录保留原精度：整个可能日期区间落在筛选范围外时排除，否则保留并标记 `date_unknown`。日期缺失的记录也会保留并标记，供后续审查。DOAJ/DataCite/HAL 先按年份限制服务端请求，再按实际精度在本地过滤；Europe PMC 使用 FIRST_PDATE。

DOAJ、DataCite、HAL、Europe PMC、Google Scholar 和 CORE 适配器复用请求间隔、HTTP 429 重试与 Retry-After 冷却、逐查询缓存、完整查询缓存和每来源每日请求预算。计入实际 HTTP 请求次数，包括重试；后续请求失败时保留已取得的记录并报告部分可用。当前新增来源每条查询最多取 100 条，Google Scholar 每页最多 20 条，检索规划最多执行 4 条不同查询；这不构成系统综述的穷尽检索。

Google Scholar 没有官方公开批量检索 API。此产品通过 SerpApi 获取搜索结果，页面明确标注第三方服务及额度要求。搜索片段保存为 `search_snippet`，不会冒充作者摘要进入证据摘要；年份信息保留年份精度。Google Scholar 和 CORE 默认不发请求，只有用户添加并配置后才参与所选任务。未提供真实授权密钥，因此本次通过公开 SerpApi 样例、模拟接口和产品回归验证；用户需在页面执行实际连接测试以确认自己的权限和额度。Scopus、Web of Science、知网、万方尚无适配器，不在可添加列表中。

全文链接仅在来源返回开放链接或明确开放许可时填入；DataCite 元数据公开不代表原文可自由访问。

## 配置接口

`GET /api/sources` 返回目录、是否添加/启用/可选、默认标记、请求上限和最近检测状态，不返回密钥。`PUT /api/sources/{id}` 添加或更新连接；可提交 `enabled`、`default_enabled`、`daily_request_budget`、`api_key`、`clear_api_key`，PubMed 另支持 `email`。请求上限为 1–100000，`null` 继承全局值；空白密钥保持原值。`DELETE /api/sources/{id}` 移除连接，保留密钥和历史。`POST /api/sources/{id}/test` 使用已保存配置执行小规模真实检索。

未知来源返回 404；缺少必填密钥、无效预算或不支持的字段返回 422。新建任务/订阅未指定 `sources` 时使用保存的默认选择；显式指定未启用/未配置来源会返回 422。停用既有任务来源不改写其历史选择。

服务器初始环境可使用 `SERPAPI_API_KEY`、`CORE_API_KEY`；推荐在网页填写。设定环境密钥后仍需在页面添加并启用对应来源。密钥经现有凭据库保存，勿写入发布说明、命令行历史或镜像构建参数。

2026-11-01 用 `machine learning`、日期范围 `2024-01-01` 至 `2026-11-01`、每来源 2 条的真实请求验证：四个新增适配器均返回 HTTP 200 和 2 条规范化记录。DBLP 在当前网络返回 HTTP 202 人机验证页面，本次没有接入。该验证仅覆盖接口和字段映射，未执行模型筛选、邮件发送或 Zotero 写入。

本次最终回归通过 299 项后端测试、前端生产构建和 9 项 Edge 浏览器测试，覆盖来源配置持久化、默认来源、密钥不泄露、停用后零请求、日期精度、跨来源身份合并、缓存、请求预算及限流后保留结果。浏览器覆盖添加和配置 Google Scholar、刷新恢复、切换启停、移除和重新添加入口、清除密钥、逐来源检测、手机配置窗口，以及任务与订阅来源选择。
