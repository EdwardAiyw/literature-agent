# 期刊影响因子（JIF）

当前源码支持将期刊 JIF、指标年份及数据来源显示在工作台和每日邮件中；新建 Zotero 期刊条目时写入 Extra，同时补充期刊名称及 ISSN。影响因子属于期刊指标，不改变论文相关性评分，也不替代论文内容判断。

此功能需要你已有的 JCR 指标数据。当前五个文献检索源不提供官方 JIF；程序不通过模型猜测数值，不将引用次数、CiteScore 或 OpenAlex 两年平均引用数标为 JIF。没有可匹配数据时显示“未提供”，预印本、会议论文等非期刊文献显示“不适用”。

## 网页操作

1. 在“设置 → 期刊影响因子（JIF）”下载空白 CSV 模板。
2. 将可使用的 JCR 数据整理为 UTF-8 CSV，列名如下；指标年份填数值对应年份，不是论文发表年份或导入年份：

   ```csv
   journal,issn,eissn,year,jif
   ```

3. `journal` 为期刊名称，`issn` 和可选 `eissn` 至少一个有效。填写非负 JIF（含 0）或官方 `<0.1` 值；没有指标的行不要填 0，可暂不导入这些行。ISSN 校验格式及校验位。
4. 选择文件，填写实际数据来源名称及可选 http/https 来源链接，点击“导入影响因子”。错误会显示行号；整批校验通过才写库。最大 15 MB、100000 行。
5. 返回工作台查看匹配结果。相同 ISSN/年份的再次导入更新该记录，其他年份保留；显示每本期刊最新已导入年份。来源明确标为“用户导入”，程序不能独立验证导入数值是否来自 JCR。

## 匹配与历史

- OpenAlex、Crossref、PubMed 保留期刊 ISSN；Semantic Scholar 在返回期刊信息时保留可用元数据。相同规范文献的跨源去重会补齐 ISSN，不覆盖已有标题/摘要。
- 仅使用校验通过的 ISSN 匹配，不按相似期刊名猜测。若同一年印刷/电子 ISSN 匹配结果的期刊、数值或来源冲突，则不显示数值。
- 已有论文在网页、邮件及新导入时读取当前指标表；不重写历史论文 payload、不重新筛选，也不重发邮件。历史记录若没有保存 ISSN，仍可能无法匹配；本次功能不会逐篇联网回填历史元数据。已有来源缓存可能仍缺 ISSN，后续缓存过期后的新检索会保留新字段。
- 已存在于 Zotero 的条目继续仅补集合，不覆盖用户 Extra 或其他字段；添加/更新指标表不会批量改写远端条目。新建的期刊条目在 Extra 标记 JIF、年份、用户导入来源及可选链接。
- `zotero-identifiers.txt` 保持每行一个编号，不混入影响因子，确保仍可整体粘贴到 Zotero 的标识符窗口。

## API 与存储

| 接口 | 行为 |
| --- | --- |
| `GET /api/journal-metrics` | 返回 `records`（ISSN/年份记录数）、`latest_year`、`updated_at` |
| `GET /api/journal-metrics/template` | 下载只有表头的 UTF-8 CSV 模板 |
| `POST /api/journal-metrics/import` | JSON `{csv,source,source_url?}`；校验后原子导入，无效输入返回 422 |
| `GET /api/runs/{id}/papers` | 新增 `venue`、`venue_type`、`issns`、可空 `journal_metric`；指标含 `jif/year/source/source_url/matched_by` |

Alembic `20261017_0004` 新增 `journal_metrics` 表，以 ISSN/年份为联合主键，payload 保存期刊名、JIF 和来源。原有数据不变；升级前自动备份，网页数据库备份包含指标表。服务器更新仍应备份数据库及配置/密钥，见 [部署手册](SERVER_DEPLOYMENT.md)。指标表不包含账号密钥。
