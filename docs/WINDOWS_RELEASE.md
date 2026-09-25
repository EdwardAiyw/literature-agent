# Windows 产品使用说明

面向非技术用户的逐步说明、字段解释和故障排查见根目录 [`README.md`](../README.md)。本页保留为发布与维护速查。

当前私有预发布版是 [`v0.3.0-rc.3`](https://github.com/EdwardAiyw/literature-agent/releases/tag/v0.3.0-rc.3)。安装包大小为 28,611,752 字节，SHA-256 为 `5cfc8b45a68346b6ce5e51282d510d71ae0889b11760f79b05d00aaf2a5b51fc`。

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

公开仓库的设置页可以检查 GitHub Releases。仓库保持 Private 时，普通测试者无法使用内置更新检查，也无法直接下载 Release；需邀请其访问仓库或单独分发安装包与校验文件。此时更新检查会提示无法访问，而不会显示“已是最新版本”。下载新版安装包并覆盖安装即可，数据目录和 Windows 凭据不会被覆盖。

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
.\scripts\build-windows-release.ps1 -Version 0.3.0-rc.3
```

构建脚本会生成安装包和 `release/SHA256SUMS.txt`。推送 `v*` 标签时，GitHub Actions 会在干净的 Windows runner 上运行后端测试、前端构建及 Edge Playwright 回归测试，然后构建，并把 runner 生成的安装包与校验文件上传到对应 Release；发布页应以该次工作流生成的校验文件为准。

稳定版发布前还要使用 RC3 安装包在 Windows Sandbox 中运行：

```powershell
.\scripts\run-installer-sandbox.ps1
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
