# Literature Agent V2 配置与测试手册

本文是源码开发、API 调试和 Jev 审计的高级运行手册。普通 Windows 用户无需安装依赖或编辑 `.env`，请使用根目录 [`README.md`](../README.md) 的安装版页面操作。源码模式默认使用 `backend/data/literature_agent_v2.db`；旧版 `literature_agent.db` 不会被读取、覆盖或自动迁移。

## 1. 组件与地址

| 组件 | 地址 | 说明 |
| --- | --- | --- |
| 前端 | `http://127.0.0.1:5175` | Vite 开发服务 |
| 后端 | `http://127.0.0.1:8001` | FastAPI + 本地任务队列 |
| 健康检查 | `http://127.0.0.1:8001/api/health` | 不暴露密钥 |
| 运行时设置 | `http://127.0.0.1:8001/api/settings` | 查看配置状态 |
| Jev 审计 | `/api/runs/{run_id}/decisions` | 当前通过 API 查看，暂无 GUI 审计面板 |

V2 工作流是：创建任务 -> 检索 -> 去重 -> 相关性筛选 -> 文献总结 -> 可选证据审查 -> 结果查看。Jev 是类型化决策层，不替代生成式 LLM。

## 2. 安装依赖

要求 Python 3.12+、Node.js 18+。PowerShell 执行：

```powershell
cd D:\jianguoyun\1usm-onedrive\PhD\literature-agent
cd backend
if (-not (Test-Path .venv)) { python -m venv .venv }
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
cd ..\frontend
npm install
```

前端依赖目录是 `frontend/node_modules`，不是 `frontend/node_module`。

## 3. 配置 `backend/.env`（仅源码兼容方式）

安装版和常规源码运行都可以直接在“设置”页保存配置；下面的 `.env` 方式保留给自动化测试、迁移和无法打开页面时的开发调试。

```powershell
cd D:\jianguoyun\1usm-onedrive\PhD\literature-agent\backend
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
notepad .env
```

最低 V2 配置：

```env
LITERATURE_AGENT_LIVE=false
LITERATURE_AGENT_DB=data/literature_agent_v2.db
LLM_BASE_URL=https://api.openai.com/v1
LLM_API_KEY=
LLM_MODEL=
TYPESAFE_API_KEY=
JEV_ENABLED=false
JEV_SHADOW_MODE=true
JEV_MODEL=jev-1.13.0
JEV_TIMEOUT_SECONDS=15
JEV_AUTO_THRESHOLD=0.82
JEV_REVIEW_THRESHOLD=0.55
JEV_CACHE_TTL_HOURS=168
```

真实检索还要填写：

```env
LITERATURE_AGENT_LIVE=true
LLM_API_KEY=你的LLM密钥
LLM_MODEL=你的模型名
```

可选数据源配置：`OPENALEX_API_KEY`、`SEMANTIC_SCHOLAR_API_KEY`、`PUBMED_API_KEY`、`PUBMED_EMAIL`、`SOURCE_CACHE_TTL_HOURS=24`、`SOURCE_DAILY_REQUEST_BUDGET=200`。邮件订阅另外填写 `SMTP_HOST`、`SMTP_PORT`、`SMTP_USERNAME`、`SMTP_PASSWORD`、`SMTP_FROM`。所有密钥只放在本机 `backend/.env`，不要提交到 Git、放入 Prompt 或发到聊天中。

## 4. 启用 Jev Shadow

拿到 Jev Key 后，只修改：

```env
TYPESAFE_API_KEY=你的Jev密钥
JEV_ENABLED=true
JEV_SHADOW_MODE=true
```

第一次真实测试不要设置 `JEV_SHADOW_MODE=false`。Shadow 会调用 Jev 并记录审计，但最终结果仍由原有 LLM/规则路径决定。

不暴露密钥的检查命令：

```powershell
Invoke-RestMethod http://127.0.0.1:8001/api/settings |
  Select-Object live, llm_configured, jev_enabled, jev_configured, jev_shadow_mode, jev_model, jev_auto_threshold, jev_review_threshold
```

真实 Shadow 测试预期：`live=True`、`llm_configured=True`、`jev_enabled=True`、`jev_configured=True`、`jev_shadow_mode=True`。

## 5. 数据库与迁移

V2 启动时先运行 Alembic，再打开 SQLite。数据库不存在时创建完整 V2 schema；已有 V2 schema 幂等升级；迁移失败时后端不会继续启动。

```powershell
cd D:\jianguoyun\1usm-onedrive\PhD\literature-agent\backend
.\.venv\Scripts\alembic.exe current
```

备份前先停止后端：

```powershell
Copy-Item data\literature_agent_v2.db ("data\literature_agent_v2.before-" + (Get-Date -Format yyyyMMdd-HHmmss) + ".db")
```

不要删除正在使用的 `.db-wal` 或 `.db-shm` 文件。旧数据库可以归档，V2 不依赖它。

## 6. 启动 V2

后端窗口：

```powershell
cd D:\jianguoyun\1usm-onedrive\PhD\literature-agent\backend
.\.venv\Scripts\python.exe -m uvicorn literature_agent.api:app --host 127.0.0.1 --port 8001 --reload
```

前端窗口：

```powershell
cd D:\jianguoyun\1usm-onedrive\PhD\literature-agent\frontend
$env:VITE_API_URL='http://127.0.0.1:8001/api'
npm run dev -- --host 127.0.0.1 --port 5175 --strictPort
```

打开 `http://127.0.0.1:5175`。如果端口被旧进程占用，先确认命令行后停止对应 PID：

```powershell
Get-NetTCPConnection -State Listen -LocalPort 8001,5175 | Select-Object LocalPort,OwningProcess
Stop-Process -Id <确认后的进程ID> -Force
```

## 7. Shadow 实测

使用一个明确主题，目标数量设为 5：

```powershell
$task = Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8001/api/tasks `
  -ContentType 'application/json' `
  -Body '{"name":"Jev Shadow validation","topic":"填写一个明确研究主题","research_questions":["填写一个主要研究问题"],"target_count":5,"sources":["semantic_scholar","openalex","crossref","arxiv","pubmed"]}'
$run = Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8001/api/tasks/$($task.id)/runs"
$run.id
```

等待运行结束：

```powershell
$runId = '粘贴上一步的运行ID'
do {
  $state = Invoke-RestMethod "http://127.0.0.1:8001/api/runs/$runId"
  $state | Select-Object id,status,current_node,progress,total_steps,paper_count,error
  Start-Sleep -Seconds 2
} while ($state.status -in @('queued','running','paused'))
```

查看 Jev 审计：

```powershell
Invoke-RestMethod "http://127.0.0.1:8001/api/runs/$runId/decisions" |
  Select-Object stage,subject_id,mode,status,confidence,cached,fallback_used,fallback_reason,error |
  Format-Table -AutoSize
```

审计状态：`shadow_observed` 表示 Shadow 成功观察；`applied` 表示 Active 高置信度采用；`fallback` 表示 Active 低置信度回退，原因是 `low_confidence`；`failed` 表示 Jev 调用失败，原因是 `jev_error`，原路径继续执行。健康 Shadow 运行应看到 `mode=shadow`、`status=shadow_observed`、`fallback_used=False`。还要检查运行状态、运行事件、论文列表和结果 artifact。

## 8. Active 模式门槛

完成数次 Shadow 运行后，再评估置信度分布、缓存命中、失败率、论文相关性和人工审核结果。确认稳定后才改为：

```env
JEV_ENABLED=true
JEV_SHADOW_MODE=false
```

Active 下低置信度或调用异常仍会回到原有 LLM/规则路径。

## 9. 常见问题

- `jev_configured=False`：检查 `TYPESAFE_API_KEY` 是否为空，并重启后端。Key 不要放前端 `.env`。
- `live=False` 或 `llm_configured=False`：补齐 `LITERATURE_AGENT_LIVE=true`、`LLM_API_KEY`、`LLM_MODEL`，再重启后端。
- 迁移失败：停止后端，执行 `alembic current` 查看状态；不要手动删除 `alembic_version`。
- 前端显示旧数据：开发服务器默认通过 Vite 将同源 `/api` 代理到 `http://127.0.0.1:8001`；确认后端端口和数据库为 `data/literature_agent_v2.db`。V2 不读取旧库任务。
- Jev 失败但任务继续：这是预期回退行为，检查 `/api/runs/{run_id}/decisions` 中的 `status=failed`、`fallback_reason=jev_error` 和运行事件。
