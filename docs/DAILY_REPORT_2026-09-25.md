# Literature Agent 日报 - 2026-09-25

## 今日结论

`v0.3.0-rc.3` 已作为 GitHub prerelease 发布，仓库已由 Private 调整为 Public。外部测试者现在无需 GitHub 账号或协作者权限，即可查看源码、下载 Windows 安装包并参与测试。

后端测试、前端构建、Edge 浏览器回归、GitHub CI 和 Windows Release 工作流均已通过；安装包下载与 SHA-256 校验也已确认。RC3 仍需完成安装版人工验收，因此当前适合公开测试，但暂不应升级为稳定版。

公开反馈邮箱为 [aiyuing.usm@gmail.com](mailto:aiyuing.usm@gmail.com)。建议测试者通过邮件附上版本、复现步骤、错误信息和截图，发送前必须删除或遮挡密钥、密码及其他敏感信息。

## 今日完成

- 加固外部 Beta 发布检查、反馈模板和安全说明，并合并 GitHub PR #3。
- 修复恢复中的任务在回调注册前完成时可能出现的 worker 死锁。
- 将版本更新为 `0.3.0-rc.3`，补充更新检查回归，并统一后端、前端和 Windows 安装包版本。
- 在 Windows Release 工作流中加入前端生产构建和 Edge Playwright 回归，发布前自动阻止未通过验证的构建。
- 从干净的 GitHub Windows runner 构建并发布 RC3 安装包和 `SHA256SUMS.txt`。
- 更新 README、测试手册、当前状态和 Windows 发布文档，使其与 RC3 实际发布状态一致。
- 将 GitHub 仓库公开，并以匿名请求验证仓库、README、Release 和下载资产均可访问。
- 在 README 和 RC3 Release 页面加入反馈邮箱与反馈信息清单。

## 发布信息

- 公开仓库：<https://github.com/EdwardAiyw/literature-agent>
- RC3 Release：<https://github.com/EdwardAiyw/literature-agent/releases/tag/v0.3.0-rc.3>
- 安装包：`Literature-Agent-0.3.0-rc.3-Windows-x64.exe`
- 文件大小：`28,611,752` 字节
- SHA-256：`5cfc8b45a68346b6ce5e51282d510d71ae0889b11760f79b05d00aaf2a5b51fc`
- Release 对应提交：`9614050`
- 今日记录前 `main` 最新提交：`545cb32`

## 已验证

- 后端完整测试：本机与 GitHub Actions 均为 `51 passed`。
- SQLite 并发回归：100 组 StrictMode 双初始化，共 2,200 个读取和 400 个并发写入，无 500 或虚假 404。
- 前端生产构建：通过。
- Edge Playwright：本机与 Windows Release runner 均为 `5 passed`，覆盖连续冷加载、三个视口、全部导航入口、横向溢出和快速任务切换。
- GitHub CI：通过。
- Windows Release 工作流：通过。
- 从 Release 重新下载的安装包与 `SHA256SUMS.txt` 一致。
- 未登录状态下，仓库 README 和 `v0.3.0-rc.3` Release API 均可正常访问，反馈邮箱对外可见。
- 源码运行环境已完成五篇双来源真实检索、SMTP 测试邮件、手动日报和自动调度日报验证，并确认邮件到达。

## 今日提交

- `837e703 fix: harden Windows release tests`
- `a9aa686 Harden external beta release checks and feedback (#3)`
- `7d02ed8 fix: avoid worker recovery deadlock`
- `9614050 chore: prepare v0.3.0-rc.3`
- `67072cf docs: align RC3 release and update guide`
- `545cb32 docs: add public feedback contact`

## 当前边界与风险

- RC3 是 prerelease，不是稳定版。
- RC3 安装包仍需完成覆盖安装、首次设置、真实检索与邮件、计划任务、备份恢复、重复启动和卸载的人工验收。
- 安装包暂未进行商业代码签名，Windows SmartScreen 可能显示未知发布者提示。
- 稳定版发布前不得只依据自动化测试跳过人工安装验收。
- 本地工作区仍保留三张未提交的 P2 回归截图修改，以及两个未跟踪的安装沙箱结果目录；本次发布和文档提交均未包含这些文件。

## 下一步

1. 从公开 RC3 Release 下载安装包和 `SHA256SUMS.txt`，先核对 SHA-256。
2. 按 [Windows Sandbox 安装版验收说明](INSTALLER_SANDBOX_TEST.md) 和 [产品测试与验收手册](../TEST_GUIDE.md) 完成 RC3 人工验收。
3. 重点确认覆盖安装后版本、数据和凭据保留，以及真实邮件、计划任务、备份恢复和卸载行为。
4. 将问题和建议发送至 [aiyuing.usm@gmail.com](mailto:aiyuing.usm@gmail.com)，附上脱敏后的截图与复现信息。
5. 汇总外部测试结果；只有在 RC3 安装版验收通过且无阻断问题后，才准备稳定版发布。
