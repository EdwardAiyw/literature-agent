# Windows 发布与维护

面向非技术用户的逐步说明、字段解释和故障排查见[Windows 使用指南](WINDOWS_USER_GUIDE.md)。本页保留为发布与维护速查。

当前公开预发布版为 [`v0.3.0-rc.6`](https://github.com/EdwardAiyw/literature-agent/releases/tag/v0.3.0-rc.6)，包含历史推送去重、动态截止日期、自动 Zotero 集合导入、标识符附件和官网 JIF。对应源码还支持单独部署 Linux 服务器。完整人工安装、覆盖升级、计划任务、恢复与卸载验收尚未全部完成，因此保留 prerelease 状态。

[GitHub CI](https://github.com/EdwardAiyw/literature-agent/actions/runs/39086374846) 与 [Windows Release](https://github.com/EdwardAiyw/literature-agent/actions/runs/39086375057) 均通过：245 项后端测试、前端构建、32 项 Edge 回归及打包程序检查。安装包为 **29,146,628 字节**，公开匿名重新下载后的 SHA-256 为 `d0d553e64a0356953e3a4b83b8cf536efa2c6394408aacc08b261b2517641515`，与同一 Release 的 `SHA256SUMS.txt` 和 GitHub 资产摘要一致。详见 [RC6 发布记录](RELEASE_RC6.md)；历史资产验证保留在 [项目状态](CURRENT_STATE.md)。

## 安装

1. 在 GitHub Releases 下载 `Literature-Agent-<version>-Windows-x64.exe` 和 `SHA256SUMS.txt`。
2. 校验 SHA-256 后运行安装包。Beta 安装包暂未签名，Windows SmartScreen 可能要求确认发布者。
3. 从开始菜单启动 Literature Agent。程序只监听 `127.0.0.1:8001`，随后打开默认浏览器。
4. 首次启动按页面完成数据目录、模型、SMTP、来源和自动任务配置。

用户无需安装 Python、Node.js，也不需要编辑 `.env`。普通设置写入所选数据目录，API Key 和 SMTP 密码写入当前 Windows 用户的凭据库。

## 首次配置

- 数据目录：选择长期保留且当前用户可写的本机目录。不要选择程序安装目录。
- 模型：填写 OpenAI-compatible API 地址、模型和 API Key，先测试再保存。
- 邮件：填写 SMTP 主机、端口、账号、授权码和发件人，发送测试邮件确认。
- 来源：公共来源可以直接使用；Semantic Scholar、OpenAlex 和 PubMed 密钥均为可选。
- Jev：默认关闭；关闭时系统使用原有 LLM/规则路径，不影响日报。
- 自动运行：点击“注册自动任务”，页面应显示 Local 和 Daily 两项任务。

## 数据与备份

数据库、设置、日志和备份均位于首次选择的数据目录。升级和卸载默认不删除该目录。

设置页的“立即备份”会在 `backups` 子目录创建 SQLite 一致性备份。数据库迁移前也会自动创建 `pre-migration-*.db`。日志每日轮转并保留 14 天。

恢复备份前必须停止正在执行的研究任务。恢复接口会先创建 `before-restore-*.db` 安全副本，再替换数据库。

## 更新与卸载

本仓库已公开，可直接从 RC6 Release 下载。设置页“检查更新”当前使用 GitHub 稳定版入口，候选版可能无法被发现，请使用 README 的直接下载链接。先完成活动运行、备份并退出正在运行的程序，再校验新版安装包并覆盖安装；数据目录和 Windows 凭据会保留。

从 Windows“已安装的应用”卸载时会移除程序文件和计划任务，但保留用户数据和凭据。确认不再需要后，可由用户手动删除数据目录和 Windows 凭据管理器中以 `LiteratureAgent/` 开头的条目。

## 发布构建与验收

开发者在标签发布前执行：

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest -q

cd ..\frontend
npm run build
npm run test:e2e

cd ..
.\scripts\build-windows-release.ps1 -Version 0.3.0-rc.6
```

构建脚本会生成安装包和 `release/SHA256SUMS.txt`。推送 `v*` 标签时，GitHub Actions 会在干净的 Windows runner 上运行后端测试、前端构建及 Edge Playwright 回归测试，然后构建，启动打包后的程序检查版本、数据库隔离、Prompt v2、Zotero、自动 JIF 默认值、推送历史迁移、前端、固定/当天日期策略切换及任务转换无检索/投递副作用，再把 runner 生成的安装包与校验文件上传到对应 Release；发布页应以该次工作流生成的校验文件为准。

稳定版发布前还要使用 RC6 安装包在 Windows Sandbox 中运行：

```powershell
.\scripts\run-installer-sandbox.ps1 -Version 0.3.0-rc.6
```

按 [`INSTALLER_SANDBOX_TEST.md`](INSTALLER_SANDBOX_TEST.md) 完成首次设置、五篇两来源、邮件、计划任务、备份恢复、重复启动和卸载。Sandbox 未完成时只能发布为 prerelease 候选版。

## 故障排查

- 页面无法打开：确认 `127.0.0.1:8001` 未被其他程序占用，然后重新从开始菜单启动。
- 模型失败：检查 Base URL 是否包含 `/v1`、模型标识是否正确，并重新运行连接测试。
- 邮件失败：126/QQ 等服务通常需要 SMTP 授权码而非网页登录密码。
- 自动日报未发送：在设置页查看两个计划任务状态、最近结果和下一次运行时间。
- 数据源降级：Semantic Scholar 429 或 arXiv 临时超时不会阻塞其他来源；来源诊断会保留失败原因。

## 源码开发模式

开发者仍可使用 `backend/.env` 作为兼容回退。页面保存的配置优先用于当前产品进程，密钥不会通过设置 API 返回。
