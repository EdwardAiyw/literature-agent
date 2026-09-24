# Windows Sandbox 安装版隔离验收

本验收只在临时 Windows Sandbox 中运行，不会读取宿主机的 Literature Agent 数据目录或 Windows 凭据。关闭 Sandbox 后，Sandbox 内部数据会被 Windows 删除；只有 `C:\LiteratureAgentResults` 中的结果会同步回宿主机。

## 1. 自动启动阶段

打开 Sandbox 后等待两个窗口出现：Literature Agent 页面和本说明。脚本会自动完成 SHA-256 校验、当前用户静默安装、首次启动、首页 HTTP 检查和重复启动检查。

打开 `C:\LiteratureAgentResults\AUTOMATED_RESULTS.md`，确认前四项为 `PASS`。如果失败，不要输入任何凭据，记录页面和文件中的错误后关闭 Sandbox。

## 2. 页面人工验收

在 Literature Agent 的“设置”页完成以下操作：

1. 数据目录保持 `C:\LiteratureAgentData`。
2. 手工输入模型 API 地址、模型名称和 API Key，测试通过后保存。
3. 手工输入 SMTP 信息，只向你自己的测试邮箱发送测试邮件；确认实际收到。
4. 文献来源可不填写可选 Key；填写 PubMed 联系邮箱并测试来源。
5. Jev 保持关闭。
6. 点击“注册自动任务”，确认 Local 和 Daily 两项任务都出现。

凭据只输入 Sandbox 页面。不要把 API Key、SMTP 密码或授权码写入 `CHECKLIST.md`、`MANUAL_CONFIRMATION.txt`、命令行或截图。

## 3. 核心研究与邮件

在工作台创建任务：

| 字段 | 值 |
| --- | --- |
| 任务名称 | `Sandbox Agentic RAG` |
| 研究主题 | `agentic retrieval augmented generation evaluation` |
| 检索语言 | 中英文 |
| 目标数量 | 5 |
| 来源 | 全选 |
| 证据审查 | 开启 |

等待运行完成并检查：

- 状态为 7/7、已完成。
- 最终恰好 5 篇论文。
- 最终论文至少来自两个不同来源。
- 页面无 `Run not found`、`Task not found` 或 `Internal Server Error`。

再创建一个每日订阅，先发送 SMTP 测试邮件，再手动运行一次并确认正式摘要邮件实际到达。不要使用他人的邮箱。

## 4. 手工确认文件

用记事本打开 `C:\LiteratureAgentResults\MANUAL_CONFIRMATION.txt`，把已经实际确认的四项 `NO` 改成 `YES`：

- SMTP 测试邮件实际到达。
- 5 篇正式摘要邮件实际到达。
- 最终 5 篇至少包含两个来源。
- 页面首次设置已经完成。

不要在该文件中写邮箱地址或任何凭据。

## 5. 备份、恢复与卸载

确保没有任务处于运行中，然后双击桌面的 `Finish Literature Agent Test.cmd`。它会自动：

1. 核对数据库中存在“5 篇、至少两个来源”的已完成运行。
2. 核对两项 Windows 计划任务。
3. 创建备份并立即从该备份恢复。
4. 停止程序、静默卸载。
5. 核对程序文件和计划任务已移除，同时用户数据仍保留。

完成后查看 `AUTOMATED_RESULTS.md`。全部自动项目为 `PASS` 且人工确认均为 `YES`，才可判定安装版隔离验收通过。确认结果文件已同步到宿主机后，再关闭 Windows Sandbox。
