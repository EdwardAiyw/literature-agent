# 源码模式本机正式上线

本页用于开发者把源码检出作为单用户 Windows 本机服务运行。普通用户应安装 Windows 安装包，并按照根目录 [`README.md`](../README.md) 在页面完成设置。正式地址为 `http://127.0.0.1:8001`；服务不监听局域网或公网接口。

## 1. 构建并启动

```powershell
.\scripts\start-local.ps1 -BuildFrontend
```

脚本会构建前端、执行 Alembic 迁移，并以非热重载模式启动 FastAPI。前端由同一个 FastAPI 进程托管。日志写入忽略提交的 `backend/logs/`。

## 2. 持久化正式运行配置

推荐在页面“设置”中保存模型、SMTP、来源和运行参数。普通设置写入数据目录的 `settings.json`，密钥写入 Windows 凭据管理器，保存后立即供服务与计划任务使用。

`backend/.env` 仅作为源码开发和旧配置迁移的兼容回退。如果必须通过文件配置，可写入：

```env
LITERATURE_AGENT_LIVE=true
LLM_API_KEY=你的LLM密钥
LLM_MODEL=你的模型名
SMTP_HOST=你的SMTP主机
SMTP_PORT=587
SMTP_USERNAME=你的SMTP用户名
SMTP_PASSWORD=你的SMTP密码或应用专用密码
SMTP_FROM=发件邮箱
JEV_ENABLED=false
JEV_SHADOW_MODE=true
```

不要把 `.env`、密钥或邮箱密码提交到 Git 或发到聊天中。直接编辑 `.env` 后需要重启服务；通过页面保存则通常无需重启。确认：

```powershell
Invoke-RestMethod http://127.0.0.1:8001/api/settings |
  Select-Object live,llm_configured,smtp_configured,jev_enabled
```

无 Jev 上线时应为 `live=True`、`llm_configured=True`、`smtp_configured=True`、`jev_enabled=False`。

可在不创建订阅、不发送邮件的情况下验证持久配置和运行中服务是否一致：

```powershell
.\scripts\create-agentic-rag-subscription.ps1 -Recipient you@example.com -ValidateOnly
```

## 3. 创建并验收正式订阅

以真实收件邮箱执行：

```powershell
.\scripts\create-agentic-rag-subscription.ps1 -Recipient you@example.com -TestSend -RunNow
```

脚本会幂等创建或更新 `Agentic RAG 日报`：每天 08:00、`Asia/Hong_Kong`、5 篇、全部五个来源、开启证据审查。它会检查 Live、LLM 和 SMTP 配置，但不会要求 Jev。`-TestSend` 必须成功发送测试邮件；`-RunNow` 会等待真实运行和摘要投递完成，只有投递记录为 `sent` 才视为通过。慢速检索可通过 `-TimeoutSeconds 3600` 延长等待时间。

正式运行还会检查最终结果恰好为 5 篇、完成全部证据审查，并且至少覆盖两个文献来源。系统按相关性优先选文；当至少两个来源存在 `relevance_score >= 0.55` 的候选时，会保留一个第二来源的合格候选。Semantic Scholar 遇到 429 会限速并退避重试；arXiv 使用显式字段查询和 `%20` 编码，Python TLS/连接异常时使用仍执行证书验证的系统 `curl` 后备。

修复或复验现有订阅时可精确指定订阅 ID，避免重复创建：

```powershell
.\scripts\create-agentic-rag-subscription.ps1 `
  -Recipient you@example.com `
  -SubscriptionId 已有订阅ID `
  -TestSend -RunNow -TimeoutSeconds 3600
```

## 4. 注册自动运行

测试邮件和首次真实日报均确认到达后，关闭手动启动的服务，再注册登录自启和每日检查任务：

```powershell
.\scripts\register-local-startup.ps1
.\scripts\register-windows-task.ps1
Start-ScheduledTask -TaskName "Literature Agent Local"
```

验证：

```powershell
Invoke-RestMethod http://127.0.0.1:8001/api/health
Invoke-RestMethod http://127.0.0.1:8001/api/settings |
  Select-Object live,llm_configured,smtp_configured,jev_enabled,jev_configured,jev_shadow_mode,jev_model
Get-ScheduledTask -TaskName "Literature Agent Local","Literature Agent Daily" |
  Select-Object TaskName,State
```

卸载任务：

```powershell
.\scripts\register-local-startup.ps1 -Unregister
.\scripts\register-windows-task.ps1 -Unregister
```

## 5. 可选：以后启用 Jev

Jev 不是正式订阅的前置条件。取得 TypeSafe API Key 后，再按本节独立完成 Shadow、人工审核和 Active canary，不影响现有 LLM/规则路径运行。

登录 TypeSafe 控制台，在 API Keys 页面创建 Key。优先在页面“设置 > Jev 决策层”中填写并保存，Key 会进入当前 Windows 用户的凭据管理器。自动化脚本或页面不可用时，源码用户也可以把 Key 写入 `backend/.env` 作为兼容回退：

```env
TYPESAFE_API_KEY=你的Key
```

不要把 Key 发到聊天、写进 Prompt 或提交 Git。通过 `.env` 修改后先重启本地服务；通过页面保存通常无需重启。随后运行：

```powershell
cd backend
.\.venv\Scripts\python.exe ..\scripts\jev-release.py prepare
```

该命令会读取账户可用模型：优先选择 `jev-1.13.0`，不可用时选择发布日期最新的具体模型；同时把 Jev 设置为 Shadow。重启本地服务后运行三组真实验证：

```powershell
.\.venv\Scripts\python.exe ..\scripts\jev-release.py shadow
```

报告保存在 `backend/logs/jev-shadow-*.json`。逐篇检查报告中的 15 篇论文，确认每组至少 4/5 直接相关且摘要没有超出证据。自动门禁和人工检查均通过后：

```powershell
.\.venv\Scripts\python.exe ..\scripts\jev-release.py activate --report .\logs\jev-shadow-时间戳.json --approve-relevance
```

重启服务并执行 Active canary：

```powershell
.\.venv\Scripts\python.exe ..\scripts\jev-release.py canary
```

canary 必须完成、无 `failed` 审计，且至少一条记录为 `applied`。若失败，把 `JEV_SHADOW_MODE` 恢复为 `true` 并重启服务。
