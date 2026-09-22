# Literature Agent MVP 测试清单

## 本地地址

- GUI: http://127.0.0.1:5175/
- API health: http://127.0.0.1:8001/api/health
- API settings: http://127.0.0.1:8001/api/settings
- API docs: http://127.0.0.1:8001/docs

## 1. 服务检查

1. 打开 GUI，确认左侧有“工作台”“每日订阅”“Prompt 版本”“设置”。
2. 打开 API health，预期返回 `{"status":"ok","live":false}` 或 `live:true`。
3. 打开 API settings，确认 `sources` 中包含 OpenAlex、Crossref、arXiv、PubMed。

## 2. 工作台检索

在“工作台”填写：

| 字段 | 测试值 |
| --- | --- |
| 任务名称 | Agentic RAG 测试 |
| 研究主题 | agentic retrieval augmented generation evaluation |
| 检索语言 | 中英文 |
| 目标数量 | 5 |
| 文献来源 | OpenAlex、Crossref、arXiv、PubMed |

点击“开始检索”。预期：

- 运行状态依次显示检索规划、来源检索、去重、相关性筛选、文献简报、保存结果。
- 结果页显示论文或 fixture 记录。
- “来源诊断”显示每个来源的状态、记录数或失败原因。

## 3. SMTP 测试

先在 `backend/.env` 配置：

```env
SMTP_HOST=smtp.resend.com
SMTP_PORT=465
SMTP_USERNAME=resend
SMTP_PASSWORD=YOUR_RESEND_API_KEY
SMTP_FROM=agent@mail.251104.xyz
SMTP_STARTTLS=false
SMTP_SSL=true
```

重启后端，再打开“每日订阅”，创建：

| 字段 | 测试值 |
| --- | --- |
| 订阅名称 | RAG 日报测试 |
| 研究主题 | agentic RAG |
| 收件人 | 你的收件邮箱 |
| 目标篇数 | 5 |
| 执行时间 | 任意时间 |
| 时区 | Asia/Hong_Kong |

保存订阅后，点击信封图标“发送测试邮件”。预期：

- 收件箱收到标题为 `[Literature Agent] SMTP test` 的邮件。
- “投递记录”显示 `sent`。

## 4. 真实日报运行

在 `.env` 追加 LLM 和实时来源配置：

```env
LITERATURE_AGENT_LIVE=true
LLM_BASE_URL=https://api.openai.com/v1
LLM_API_KEY=YOUR_LLM_API_KEY
LLM_MODEL=YOUR_MODEL_NAME
```

重启后端，在“每日订阅”点击“手动运行”。预期：

- 工作台显示本次运行进度和来源诊断。
- 收件箱收到包含论文标题、作者、DOI、原文链接、中文摘要和推荐理由的日报。
- “投递记录”显示 `sent`；失败时记录错误原因。
- 刷新 GUI 后，在“最近任务”选择该订阅对应任务，仍可重新打开本次运行的节点、来源诊断和论文结果。

## CLI 验证

```powershell
cd backend
.\.venv\Scripts\python.exe -m literature_agent.daily --run-enabled
```

仅验证检索、不发邮件：

```powershell
.\.venv\Scripts\python.exe -m literature_agent.daily --run-enabled --no-send
```

仅运行在各自时区内已到执行时间、且当天尚未运行的订阅：

```powershell
.\.venv\Scripts\python.exe -m literature_agent.daily --run-due
```

## Windows 定时任务

首次手动投递验收通过后，在项目根目录执行：

```powershell
.\scripts\register-windows-task.ps1
```

脚本默认每 15 分钟检查一次到期订阅；同一订阅在其本地自然日内最多自动运行一次。卸载命令：

```powershell
.\scripts\register-windows-task.ps1 -Unregister
```
