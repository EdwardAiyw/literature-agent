# Changelog

## Unreleased

- Make Windows scheduler status checks degrade cleanly on timeout and keep Jev decision audit ordering deterministic.

## 0.3.0 - 2026-09-24

- 增加页面化首次配置、LLM、SMTP、来源、Jev 和运行参数设置。
- 使用 Windows Credential Manager 保存 API Key 和 SMTP 密码。
- 增加设置热更新、连接测试、数据目录选择、备份恢复和日志轮转。
- 增加 Windows 计划任务页面管理和重复运行保护。
- 增加 PyInstaller、Inno Setup 与 GitHub Releases 自动构建流程。
- 保留现有 `.env`、SQLite 数据库和无 Jev 运行路径的兼容性。
- 串行保护共享 SQLite 连接，修复并发初始化中的虚假 404 和 500。
- 增加首次加载、轮询和任务切换的请求取消与过期响应保护。
- 修复 390px 移动端和 768px 平板端的导航、表单与任务列表横向溢出。
- 增加 100 组双初始化并发回归和 Edge Playwright 响应式回归。
- 增加 Windows Sandbox 安装、备份恢复和卸载验收工具。
