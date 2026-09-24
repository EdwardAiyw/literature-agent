# P2 修复回归报告

日期：2026-09-24
版本：Literature Agent 0.3.0（未提交工作区）

## 结论

桌面首次加载竞态和移动端横向溢出两个 P2 均已修复。源代码自动化、真实 Edge 浏览器和重建后的打包 EXE 冒烟全部通过。

## 自动化结果

| 检查 | 结果 |
| --- | --- |
| 后端完整测试 | `45 passed, 51 warnings` |
| 并发专项 | 100 组双初始化、200 次 bootstrap、2,200 个读取、400 个并发写入；0 个 500、0 个虚假 404 |
| 前端生产构建 | 通过，1878 个模块 |
| Edge Playwright | `5 passed` |
| 桌面冷加载 | 连续 10 次，无全局错误横幅 |
| 响应式视口 | 390 x 844、768 x 1024、1440 x 1000 全部通过 |
| 页面范围 | 工作台、每日订阅、Prompt 版本、设置均无横向溢出 |
| 快速任务切换 | 最终状态只显示最后选择的任务 |
| PowerShell 语法 | 全部脚本解析通过 |
| 打包版冒烟 | 独立数据目录、端口 8012；health=ok、首页 HTTP 200 |

## 截图

- [移动端 390px](workspace-mobile-fixed.png)
- [平板 768px](workspace-tablet-fixed.png)
- [桌面 1440px](workspace-desktop-fixed.png)

修复前证据保留在 `../uat-20260924/`，未覆盖。

## 安装包

- 文件：`release/Literature-Agent-0.3.0-Windows-x64.exe`
- 大小：31,467,694 字节
- SHA-256：`4305edc251b5fb0b80464cbf369c4898c5c34b1d5b71ad782ba9262ed2958194`

Windows Sandbox 功能已启用，但操作系统返回 `RestartNeeded=True`。重启后仍需完成 `docs/INSTALLER_SANDBOX_TEST.md` 中的安装版人工验收，才能解除最终发布阻塞。
