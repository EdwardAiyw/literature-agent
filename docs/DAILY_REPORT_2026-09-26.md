# Literature Agent 日报 - 2026-09-26

## 今日结论

LocalJev 已接入 Literature Agent，Windows 本地完整链路已经建立：`Literature Agent :8001 -> LocalJev :8080 -> Qwen2.5 3B Vulkan :8000`。Jev 默认保持 Shadow 模式，只记录决策审计，不改变现有文献筛选结果；确认多轮运行稳定后再考虑 Active 模式。

公开反馈邮箱已统一修正为 [aiyuling.usm@gmail.com](mailto:aiyuling.usm@gmail.com)，README、GitHub Bug Report 模板和日报中的可见文字及 `mailto:` 链接均已同步。

## 今日完成

- 接入 [githubnext/localjev](https://github.com/githubnext/localjev)，增加 LocalJev 配置、健康检查、就绪检查和模型列表检查。
- 在 Windows 上配置 `node-llama-cpp` Vulkan 上游与 Qwen2.5 3B Instruct Q4_K_M，并提供完整链路启动、停止和状态检查脚本。
- 扩展 Jev 决策层，支持 Shadow、Active、低置信度回退、请求失败回退、缓存和决策审计。
- 增加 Jev V3 数据库迁移、API 状态接口、设置接口和前端 LocalJev 控制面板。
- 更新 LocalJev 接入说明、Jev Shadow 验证说明、运行手册、发布脚本和回归测试。
- 使用 PhD 主题“Agentic RAG evaluation”完成一次真实检索：37 条记录、26 条去重记录，最终选择 5 篇文献。
- 修正公开反馈邮箱，避免 GitHub Issue 模板和项目文档继续指向错误地址。

## 已验证

- Literature Agent、LocalJev 和本地 Vulkan 模型服务均可按脚本启动和检查。
- PhD 主题真实检索任务已完成，Run ID：`7c1a4077-fd93-4a7f-9026-dd9dc592336b`，Task ID：`db8cf51c-92a7-45cb-b37d-3c9bbedebe04`。
- Jev Shadow 审计数据能够记录模式、状态、置信度、延迟、模型和回退原因。
- 项目文本中已不存在旧的错误反馈邮箱拼写；`git diff --check` 通过。

## 当前边界与风险

- Jev 当前默认使用 Shadow 模式，Active 模式必须在检查多轮置信度分布和文献质量后再启用。
- Vulkan 上游首次启动需要加载约 2 GB 模型，模型自报概率不等同于直接读取 logits。
- 本次 GitHub 更新不包含 `test-results` 下的回归截图和安装沙箱临时目录。
- Windows 安装版仍需继续完成覆盖安装、计划任务、备份恢复、重复启动和卸载的人工验收。

## 下一步

1. 完成本次后端、前端和脚本回归测试，并推送到 GitHub `main`。
2. 在 Shadow 模式下积累更多真实 PhD 文献任务，检查 Jev 置信度与最终筛选质量。
3. 通过 [aiyuling.usm@gmail.com](mailto:aiyuling.usm@gmail.com) 收集外部测试反馈，邮件中附上脱敏后的复现步骤、版本和截图。
4. 安装版人工验收通过且无阻断问题后，再准备稳定版发布。
