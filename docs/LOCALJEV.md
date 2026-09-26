# LocalJev 接入

Literature Agent 将 [githubnext/localjev](https://github.com/githubnext/localjev) 作为本地 Jev 服务使用。两者保持独立进程：Literature Agent 负责文献工作流、路由和审计；LocalJev 负责提供兼容 Jev 的 `POST /v1/systemone` 决策 API。

## 服务边界

默认链路：

```text
Literature Agent :8001 -> LocalJev :8080 -> OpenAI-compatible model server :8000
```

LocalJev 仓库默认推荐 DiffusionGemma 上游，但 oMLX 只适用于 Apple Silicon。当前 Windows 机器使用 `node-llama-cpp` Vulkan 后端和 Qwen2.5 3B Instruct Q4_K_M，提供 LocalJev 所需的 OpenAI Chat Completions 与 JSON Schema 约束。它返回的是模型自报并归一化的概率，不等同于直接读取模型 logits；在 Active 模式使用阈值前，应先通过 Shadow 数据检查校准情况。

## 当前安装

| 组件 | 位置或地址 |
| --- | --- |
| Literature Agent | `http://127.0.0.1:8001` |
| LocalJev | 项目同级 `localjev`，监听 `http://127.0.0.1:8080` |
| 模型运行时 | `D:\localjev-runtime`（由 Bun 启动） |
| 上游接口 | `http://127.0.0.1:8000` |
| 模型 | `qwen2.5-3b-instruct-q4_k_m` |

模型文件约 1.96 GiB，SHA-256 为 `626B4A6678B86442240E33DF819E00132D3BA7DDDFE1CDC4FBB18E0A9615C62D`。运行时使用 `node-llama-cpp 3.21.1` 的 Windows x64 Vulkan 预编译后端，不需要另装 CUDA Toolkit。

## 启动完整链路

从 Literature Agent 根目录运行：

```powershell
.\scripts\start-jev-stack.ps1
.\scripts\localjev-status.ps1
```

停止模型上游和 LocalJev：

```powershell
.\scripts\start-jev-stack.ps1 -Stop
```

也可以分别控制两个服务：

```powershell
.\scripts\start-localjev-upstream.ps1
.\scripts\start-localjev.ps1
.\scripts\start-localjev.ps1 -Stop
.\scripts\start-localjev-upstream.ps1 -Stop
```

上游首次启动需要加载约 2GB 模型。启动脚本会等待最多 3 分钟，并把日志写入 `D:\localjev-runtime\logs`。

## 启动 LocalJev

LocalJev 需要 Bun 1.2+ 和一个已经运行的 OpenAI-compatible 模型服务。以下步骤仅用于在新机器上重装 LocalJev；当前机器已经完成：

```powershell
git clone https://github.com/githubnext/localjev.git
cd localjev
bun install
Copy-Item .env.example .env
```

当前 Windows 源码工作区的约定安装位置是 Literature Agent 项目同级的 `localjev` 目录。完成 `.env` 配置后，也可以从 Literature Agent 根目录使用辅助脚本：

```powershell
.\scripts\start-localjev.ps1
.\scripts\localjev-status.ps1
.\scripts\start-localjev.ps1 -Stop
```

启动日志、错误日志和 PID 文件分别写入 LocalJev 目录下的 `localjev.log`、`localjev-error.log` 和 `.localjev.pid`，它们都不会进入 Literature Agent 仓库。

编辑 LocalJev 自己的 `.env`，至少确认：

```env
LOCALJEV_UPSTREAM=http://127.0.0.1:8000
LOCALJEV_UPSTREAM_API_KEY=
LOCALJEV_UPSTREAM_MODEL=qwen2.5-3b-instruct-q4_k_m
LOCALJEV_HOST=127.0.0.1
LOCALJEV_PORT=8080
```

随后启动并检查就绪状态：

```powershell
bun run start
Invoke-RestMethod http://127.0.0.1:8080/health
Invoke-RestMethod http://127.0.0.1:8080/ready
```

`/ready` 必须返回 `status=ready`，并包含实际的 `upstream_model`。仅有 `/health` 成功不代表上游模型已加载。

Windows 可以运行 LocalJev 本身，但仓库默认推荐的 oMLX 上游只适用于 Apple Silicon。本项目的 `scripts/localjev-upstream-server.mjs` 负责把本地 Vulkan 推理封装成兼容 OpenAI Chat Completions 的接口。在上游未启动时，LocalJev 的 `/health` 会成功而 `/ready` 会返回 `unavailable`，这是预期状态。

完整检查应同时成功：

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
Invoke-RestMethod http://127.0.0.1:8000/v1/models
Invoke-RestMethod http://127.0.0.1:8080/health
Invoke-RestMethod http://127.0.0.1:8080/ready
Invoke-RestMethod http://127.0.0.1:8001/api/jev/status
```

## 配置 Literature Agent

打开“设置 > LocalJev 决策层”，保留以下默认值：

| 设置 | 默认值 |
| --- | --- |
| Provider | `LocalJev` |
| LocalJev API 地址 | `http://127.0.0.1:8080` |
| 模型 | `jev-latest` |
| 最大并发请求 | `2` |
| 超时 | `180` 秒 |

如果 LocalJev 设置了 `LOCALJEV_API_KEY`，把相同值填入 Literature Agent 的 Jev API Key；否则留空。点击“测试 LocalJev”后，页面会依次检查 `/health`、`/ready` 和 `/v1/models`。

源码模式也可以使用环境变量：

```env
JEV_PROVIDER=localjev
JEV_BASE_URL=http://127.0.0.1:8080
JEV_API_KEY=
JEV_MODEL=jev-latest
JEV_TIMEOUT_SECONDS=180
JEV_MAX_INFLIGHT=2
JEV_ENABLED=true
JEV_SHADOW_MODE=true
```

首次运行必须保留 Shadow 模式。确认决策审计中没有失败、概率分布符合实际文献判断后，再考虑 Active 模式。
