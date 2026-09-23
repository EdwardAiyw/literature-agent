# Literature Agent 日报 - 2026-09-23

## 今日结论

项目运行基线已正式切换到 V2。本地标准服务为前端 `http://127.0.0.1:5175` 和后端 `http://127.0.0.1:8001`，默认数据库为 `backend/data/literature_agent_v2.db`。旧数据库未删除，但 V2 不再读取或写入它。

Jev 集成代码、迁移、审计语义和 Shadow 测试流程已经就绪；实时 LLM 已配置。当前尚未填入 Jev API Key，因此 Jev 保持关闭，真实 Jev 调用和 Shadow 审计验证留待明天执行。

## 今日完成

- 将默认数据库路径切换到干净的 V2 SQLite 数据库，并保留旧库和在线备份 `literature_agent.before-v2-plan.bak.db`。
- 将启动建表逻辑收敛到 Alembic。V2 在 SQLite 连接打开前升级 schema，迁移失败时不会继续启动服务。
- 补齐空库、旧 V1 核心表和旧 V2 自动建表审计库的迁移兼容测试，确保原记录不丢失且迁移可重复执行。
- 明确 Jev 审计状态：`shadow_observed`、`applied`、`fallback`、`failed`；回退原因为 `low_confidence` 或 `jev_error`。
- 使 Shadow 成功记录不再被误计为 Active 回退。
- 增加 Jev 缓存、低置信度回退、调用失败与 Shadow 观察的测试覆盖。
- 完成 V2 配置与运维手册，以及 Jev Shadow 测试说明。
- 将 SQLite 的 WAL/SHM 运行时文件加入忽略规则，避免误提交运行中的数据库文件。
- 停止旧服务和临时 V2 实例，使用 V2 接管标准端口 `8001/5175`。

## 已验证

- 后端测试：26 项通过。
- 前端生产构建：通过。
- V2 后端健康接口：正常，版本 `0.2.0`。
- V2 前端 HTTP 检查：返回 200。
- 运行时设置：`live=true`、`llm_configured=true`、`jev_shadow_mode=true`。
- 当前 Jev 状态：`jev_enabled=false`、`jev_configured=false`，原因是本机 `.env` 中尚未填写 `TYPESAFE_API_KEY`。

## 本地提交

- `1894b5f feat: prepare v2 shadow validation`
- `63ee8fb docs: add v2 operations manual`

提交保留在 `v2/jev-hybrid` 本地分支，今天未推送 GitHub、未合并到 `main`。

## 明日启动清单

1. 在 `backend/.env` 填入 `TYPESAFE_API_KEY`，设定 `JEV_ENABLED=true`，保持 `JEV_SHADOW_MODE=true`。
2. 使用 TypeSafe SDK 的模型列表接口确认账户可用模型；仅在 `jev-1.13.0` 不可用时更新 `JEV_MODEL`。
3. 重启 V2 后端，并确认 `/api/settings` 的 `jev_configured=true`。
4. 创建三个主题明确的真实任务，每个 `target_count=5`，先保持 Shadow 模式。
5. 对每个运行记录运行 ID、论文数量、Jev 调用数、缓存命中、失败数和人工相关性判断。
6. 通过 `/api/runs/{run_id}/decisions` 检查成功审计均为 `mode=shadow`、`status=shadow_observed`、`fallback_used=false`。
7. 只有在多次 Shadow 运行稳定、论文质量人工确认后，才讨论 Active 模式；明天不启用 `JEV_SHADOW_MODE=false`。

## 操作资料

- [V2 配置与测试手册](V2_OPERATIONS_MANUAL.md)
- [Jev Shadow 测试说明](V2_JEV.md)
