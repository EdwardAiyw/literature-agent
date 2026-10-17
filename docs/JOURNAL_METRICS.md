# 文献推送中的期刊影响因子（JIF）

真实运行默认在文献筛选/摘要完成后，自动补齐期刊信息，查询期刊或出版商官网明确公布的 JIF，再生成每日邮件和新建 Zotero 条目。网页、邮件同时展示数值、**指标年份**和来源链接；不需要先手动导入 CSV。JIF 属于期刊指标，不参与论文相关性筛选或排序。

## 使用方式

- “设置 → 期刊影响因子（JIF）→ 自动获取影响因子”默认开启，保存后对下一次运行生效。关闭后仍可展示已有指标。
- “工作台 → 影响因子查询”显示本次匹配、缺失、信息不足、不适用、冲突和查询失败情况。旧运行不会自动联网回填，也不会重发历史邮件。
- 明确属于预印本、会议论文、书籍等非期刊文献显示“不适用”；没有有效 ISSN 显示“期刊信息不足”；其余查不到可靠值时显示“暂未查到”。不将缺失值填成 0。
- 查询超时、HTTP 429、403 或验证页面不会阻止检索结果和邮件。已有可靠值保留原指标年份及来源；网页展示官网值的获取时间。

## 数据来源与覆盖范围

1. 缺失期刊元数据的 DOI 通过 Crossref 补齐期刊名、ISSN 和出版类型；已知 arXiv DOI 直接归为预印本，不将其当作期刊。
2. 按有效 ISSN 查询 OpenAlex 的期刊登记信息和官网地址，**仅使用登记信息定位期刊**，不使用 OpenAlex 引用指标代替 JIF。
3. 只请求程序允许的出版商 HTTPS 域名；核验实际页面的 ISSN 或期刊标题，读取相邻的明确 JIF、指标年份和数值。通用解析仅接受明确格式，不从版权年份或搜索摘要推断。
4. Frontiers 使用其官网影响力表格的明确指标年份、JIF 列及精确期刊链接；兼容旧版期刊链接，避免混入 CiteScore 列。

2026-10-17 实测 Frontiers 的三本期刊成功匹配，见下表。通用解析允许 Nature/Springer、MDPI、Wiley、ScienceDirect、PLOS、OUP、Cambridge、Taylor & Francis、SAGE、IEEE、ACM 的官网，但**允许请求不代表已验证覆盖**。Nature/Springer 返回过验证页，MDPI/ScienceDirect 返回过 403；程序记录缺失/失败，不绕过验证，也不估算数字。OpenAlex 不可用或页面布局不符合规则时同样可能查不到。

| 期刊 | ISSN | 官网 JIF | 指标年份 |
| --- | --- | --- | --- |
| Frontiers in Artificial Intelligence | 2624-8212 | 6.7 | 2025 |
| Frontiers in Computer Science | 2624-9898 | 3.4 | 2025 |
| Frontiers in Psychology | 1664-1078 | 3.8 | 2025 |

来源：[Frontiers 官网指标表](https://www.frontiersin.org/about/impact)。以上是验证时的页面内容，不是代码中写死的指标。三本期刊来自同一出版商，不能据此推断所有出版商均可查询。

查询每次运行最多 60 秒，最多两个网络请求并发；单次 HTTP 超时 12 秒、响应最多 4 MB，不跟随到非允许域名。成功查询缓存 30 天，未找到/失败缓存 24 小时，后续运行到期再查。同一 DOI、同一期刊及共享官网指标页在一次运行内复用。采用最新已获得指标年份；同一 ISSN/年份自动查询不覆盖用户导入的数据，印刷/电子 ISSN 的最新同年数据冲突则不显示数字。

## 可选：导入已有 JCR 数据

自动来源覆盖不全时，可在设置中下载空白模板，整理 UTF-8 CSV：

```csv
journal,issn,eissn,year,jif
```

必填 `journal,issn,year,jif`，可选 `eissn`；印刷/电子 ISSN 至少一个有效且校验位正确。指标年份应为数值对应年份，不能用论文年份或导入年份代替。支持非负数（含 0）或官方 `<0.1`，没有指标的行应省略。填写实际来源名称及可选 HTTP/S 链接后导入；单次最大 15 MB、100000 行，整批校验通过才原子更新。再次导入更新相同 ISSN/年份，其他年份保留。

来源明确区分“用户导入”和“官网公布”；程序不能独立核验用户导入的数据是否来自 JCR。

## 邮件、Zotero 与历史数据

- HTML 和纯文本每日邮件均包含每篇文献的期刊、JIF、指标年份和来源链接；来源故障时文献照常发送。
- 新建 Zotero 期刊条目包含期刊名、ISSN 和带 JIF/年份/来源的 Extra。已有条目只补集合，不覆盖用户元数据或 Extra。
- `zotero-identifiers.txt` 保持每行一个真实标识符，不混入影响因子。
- 新运行只补齐论文的期刊元数据，不改标题、摘要、相关性或 Prompt。历史指标读取当前缓存；历史论文不会自动联网改写。

## API、配置和存储

| 接口/配置 | 行为 |
| --- | --- |
| `GET /api/journal-metrics` | `records/latest_year/updated_at`，新增 `auto_enabled/cached_journals/matched_journals`（ISSN 缓存键计数） |
| `PUT /api/settings/journal_metrics` | `{ "journal_metrics_auto": true }`，返回公开设置 |
| `GET /api/journal-metrics/template` | 空白 UTF-8 CSV 模板 |
| `POST /api/journal-metrics/import` | `{csv,source,source_url?}`；无效输入返回 422 |
| `GET /api/runs/{id}/papers` | `venue/venue_type/issns/journal_metric/journal_metric_status` |
| `GET /api/runs/{id}/artifacts` | `journal_metrics` 记录本次统计、超时或内部错误类型 |
| `JOURNAL_METRICS_AUTO=true` | 默认启用，网页保存的值优先；离线/fixture 模式不联网 |

指标记录保留 `jif/year/journal/source/source_url/matched_by`，官网值另有 `source_kind=publisher`、`identity_url`、`fetched_at`；老导入记录缺少 `source_kind` 时按用户导入解释。

Alembic `20261017_0004` 的 `journal_metrics` 保存 ISSN/年份指标；`20261017_0005` 新增 `journal_metric_lookups` 保存 DOI/ISSN 查询结果及到期时间。旧表原样保留，升级前自动创建数据库备份。指标/查询缓存随 SQLite 备份，设置和密钥应另行备份。生产升级流程见 [服务器运维](SERVER_DEPLOYMENT.md)。

## 验证范围

使用隔离临时库对现有 50 条任务结果验证：48 条为预印本/会议等非期刊文献，2 条信息不足，未匹配任何 JIF。此结论只针对这批记录，不能作为期刊查询覆盖率。验证没有重发邮件、重新检索或写入 Zotero，也没有修改生产论文。

自动测试覆盖指标年份、0/<0.1、列名校验、精确期刊链接、来源冲突、缓存、超时取消、请求并发上限、验证页、429、来源域名，以及真实运行流程中的邮件/自动导入顺序。真实官网核验与模拟测试分别记录，不用合成数据冒充真实验收。

2026-10-17 本机全量后端 **235 项测试通过**；前端构建和 JIF/服务器/Zotero 相关 **15 项 Edge 回归通过**。移动端截图检查通过，自动查询开关、来源链接与导入后刷新均通过。

## 2026-10-17 服务器更新

- 核心实现 `ab775ac`，公开设置返回字段修复 `5e2defc`；[最终代码 CI](https://github.com/EdwardAiyw/literature-agent/actions/runs/39003945482) 的后端 235 项测试、前端构建和 LocalJev 检查全部通过。该字段修复另外通过 49 项本机相关测试。
- 生产镜像 `literature-agent:5e2defc`，迁移版本 `20261017_0005`。备份 `/opt/literature-agent/backups/before-auto-jif-20261017T044735Z`；旧 14 张业务表内容哈希不变，配置/密钥及 LocalJev 环境哈希不变，新查询缓存为空。
- 从服务器使用隔离、无生产数据卷的容器重复查询三本真实期刊，数值/年份均与上表一致；生产网页只读检查确认自动查询开启、手机布局正常、历史记录未捏造数值。
- 调度已恢复，保留既有每日 07:00 Asia/Hong_Kong、目标 Zotero 集合及 LocalJev Shadow。本次没有重发邮件、重复检索、写入 Zotero 或上传合成指标。后续真实运行才会填充自动查询缓存；历史记录不会主动回填。既有 RC5 安装包/发布标签保持原样。
