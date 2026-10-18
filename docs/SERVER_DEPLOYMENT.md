# Linux 服务器部署与本机网页管理

RC6 源码支持单用户 Linux 服务器模式。每日检索和邮件在服务器运行，本机只打开管理网页；本机关机不会影响服务器任务。Windows 安装包和 Linux 镜像来自同版本源码，分别部署，不进行数据库双向同步。

## 使用网页

服务器仅监听回环地址。先配置 SSH 密钥登录并核对主机指纹，再从 Windows 执行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/open-server.ps1 -Target user@server
```

脚本建立隐藏的 SSH 隧道并打开 <http://127.0.0.1:18001>；再次运行会复用健康连接。本机重启后重新打开即可。其他电脑需要自己的 SSH 访问权限。也可手动运行：

```sh
ssh -N -T -o StrictHostKeyChecking=yes -o ExitOnForwardFailure=yes -o ServerAliveInterval=30 -L 127.0.0.1:18001:127.0.0.1:18081 user@server
```

- “每日订阅 → 编辑订阅”：修改执行时间、IANA 时区、主题、收件人、篇数、日期和来源；保存后供后续运行使用。可勾选或取消“启用每日自动执行”。
- 编辑会保留任务 ID、历史、研究问题、检索/输出语言、证据审查及 Prompt 覆盖。正在执行的任务使用启动时的配置快照。
- “手动运行”：在服务器立即排队执行检索及邮件投递，可返回工作台查看进度。
- “每日订阅 → Zotero 导入”：读取已有集合并选择确切目标，按任务开启自动导入；完成后在工作台查看进度/失败重试。每日邮件附可粘贴到 Zotero 的标识符 TXT；已完成运行可直接下载文件，无需重发。详见 [Zotero 说明](ZOTERO.md)。
- “设置 → 期刊影响因子（JIF）”：默认自动查询官网 JIF，随文献邮件附指标年份和来源；可关闭自动查询，也可导入已有 JCR CSV 补充。公开来源可能拒绝访问，查询失败仍推送文献。指标/缓存随 SQLite 备份，详见 [来源覆盖与使用说明](JOURNAL_METRICS.md)。
- “设置”：修改模型、邮箱、来源、Zotero、Jev 和请求预算；空白密钥保留已有值。
- “设置 → 后台自动运行”展示常驻调度状态。无需注册 Windows 计划任务。
- 页面备份保存在服务器数据卷；目录切换和备份恢复须停服后由运维执行。

服务器每 60 秒检查一次。按订阅自己的时区判断当天是否到时，过时可补跑当天一次；不会逐天追补历史。订阅执行（包括失败）占用当天名额；单次普通任务不占用。活动任务阻止同任务重叠。服务器重启可恢复中断的工作，但外部邮件发送与本地记录之间不能保证严格的恰好一次投递。

每日选文会在筛选前排除本订阅已成功推送的论文，不足目标篇数时按实际数量发送。新订阅默认截止到运行当天；已有订阅保留固定日期策略，可在页面切换。数据库当前升级到 `20261018_0006`，包含独立推送历史及旧邮件回填。详见 [去重、日期策略和部署验收](DAILY_DEDUPLICATION.md)。

## 已验证的 RC6 部署（2026-10-18）

- 运行镜像 `literature-agent:rc6-ebda008`，来自不可变标签 `v0.3.0-rc.6` / 提交 `ebda008d2efec3aae5413343a7328adba1e52202`。健康接口返回 `0.3.0-rc.6`，内部调度正常、无错误。
- 升级前备份位于 `/opt/literature-agent/backups/rc6-20261018T012736Z`，保留上一镜像 `literature-agent:digest-0aaced276934`。升级前后 17 张表内容及设置、密钥、LocalJev 配置哈希一致；验证报告位于 `/opt/literature-agent/validation/rc6-ebda008/deployment.json`。
- 既有订阅保持每日 `07:00 Asia/Hong_Kong`、最多 `10` 篇、`today` 截止策略及原 Zotero 目标；LocalJev 保持 Shadow。部署没有再次检索、发邮件或写入 Zotero。
- 最终 Linux 镜像在无网络、无生产密钥的隔离环境通过 **245 项后端测试**。Windows 发布及校验结果见 [RC6 记录](RELEASE_RC6.md)。

## 构建与启动

需要 Linux x86-64、Docker Compose、可访问模型/学术来源/SMTP 的网络、持久磁盘和 SSH。前端在开发电脑构建，减少服务器内存压力：

```sh
cd frontend
npm ci
npm run build
cd ..
docker build -f deploy/Dockerfile -t literature-agent:YOUR_COMMIT .
docker build -f deploy/localjev/Dockerfile -t literature-localjev:YOUR_COMMIT .
```

`.dockerignore` 使用白名单，只发送应用源码、迁移、构建后的网页和许可证；不发送 `.env`、密钥、数据库或测试输出。容器只运行一个 API 进程和一个后台工作线程。

在服务器准备持久目录，将 `deploy/compose.server.yaml` 放到 `/opt/literature-agent/`，并设置镜像标签：

```sh
install -d -m 700 -o 10001 -g 10001 /opt/literature-agent/data
cd /opt/literature-agent
printf 'LITERATURE_AGENT_IMAGE=literature-agent:YOUR_COMMIT\nLOCALJEV_IMAGE=literature-localjev:YOUR_COMMIT\nLOCALJEV_DEPLOYMENT=YOUR_COMMIT-deepseek-chat\nLITERATURE_AGENT_SCHEDULER_PAUSED=true\n' > .env
chmod 600 .env
chmod 600 localjev.env
docker compose -f compose.server.yaml up -d
docker compose -f compose.server.yaml ps
curl --fail http://127.0.0.1:18081/api/health
```

启动前先创建 `/opt/literature-agent/localjev.env`，权限 600，填入以下配置。`LOCALJEV_UPSTREAM_API_KEY` 是已有云端模型密钥；`LOCALJEV_API_KEY` 使用单独生成的内部密钥，并在应用网页的 Jev API Key 中填写相同值。不要提交真实文件。

```env
LOCALJEV_UPSTREAM=https://api.deepseek.com
LOCALJEV_UPSTREAM_API_KEY=YOUR_CLOUD_MODEL_KEY
LOCALJEV_UPSTREAM_MODEL=deepseek-flash
LOCALJEV_API_KEY=YOUR_SEPARATE_INTERNAL_KEY
LOCALJEV_OUTPUT_MODE=json_object
LOCALJEV_TIMEOUT=45
LOCALJEV_MALFORMED_RETRIES=1
LOCALJEV_MAX_INFLIGHT=2
```

首次保持调度暂停，在网页完成配置、导入并校验数据，确认没有待恢复的本机运行，再将 `.env` 中 `LITERATURE_AGENT_SCHEDULER_PAUSED` 改为 `false` 并再次 `up -d`。该变量只暂停新的每日调度，不阻止手动执行或启动恢复。

Compose 只发布 `127.0.0.1:18081`，使用 SSH 访问。应用没有多用户鉴权，不要直接把端口或反向代理暴露到公网；如需公网访问，应先配置独立的访问认证。容器以 UID/GID 10001 运行，根文件系统只读，内存上限 384 MiB，日志滚动。应根据真实运行峰值监控并调整容量；资源上限不是容量保证。

## 从 Windows 迁移

1. 等待所有运行完成，保留本机数据和回退副本。停用本机 `Literature Agent Daily` 计划任务，防止迁移后两端重复投递。
2. 使用 SQLite backup API 创建一致性数据库副本；不要只复制运行中的 `.db` 而遗漏 WAL。数据库包含任务、订阅、历史、Prompt 和来源缓存。
3. 将最终生效的非密钥设置导出为 `settings.json`。Windows Credential Manager 不随数据库迁移：在本机读取已保存密钥，通过 SSH 单独安全传送为服务器 `secrets.json`，不要经聊天、日志或 Git 传递。
4. 服务器停服后放入数据目录，修改拥有者为 10001:10001，目录权限 700，密钥文件 600。服务器路径使用 `/data`，不要沿用 Windows 盘符或本机代理地址。
5. 先以调度暂停状态验证记录数量、Prompt 和配置，以及模型与 SMTP 连通性。确保数据库没有会与本机重复恢复的活动运行。
6. 启用服务器调度，打开本机 SSH 网页入口核验。沿用现有订阅时间，之后由用户在网页修改。

迁移是一次性拷贝，不是双向同步。迁移后以服务器网页为每日任务和配置的管理入口；本机旧库作为回退资料，不应同时自动运行。

## 配置与密钥

| 环境变量 | 用途 |
| --- | --- |
| `LITERATURE_AGENT_SERVER=true` | 启用常驻调度和 Linux 文件密钥库 |
| `LITERATURE_AGENT_DATA_DIR=/data` | 数据库、配置、密钥及备份目录 |
| `LITERATURE_AGENT_BOOTSTRAP=/data/bootstrap.json` | 容器路径选择文件 |
| `LITERATURE_AGENT_SCHEDULER_PAUSED=true` | 迁移或检修时暂停新每日任务 |
| `LITERATURE_AGENT_IMAGE` | Compose 使用的固定镜像标签 |
| `LOCALJEV_IMAGE` | 独立 LocalJev 固定镜像标签 |
| `LOCALJEV_DEPLOYMENT` | 传给应用的 `LITERATURE_AGENT_JEV_DEPLOYMENT`，隔离决策缓存版本 |
| `JOURNAL_METRICS_AUTO=true` | 自动查询 JIF 的初始默认值；网页设置优先，Compose 自定义覆盖可传入容器 |

Linux 服务器密钥库是受文件权限保护的明文 JSON，不是 Windows 凭据库加密；备份与 SSH 账号同样需要保护。设置接口仅返回密钥是否已配置。数据目录应由单个 API 实例写配置，不支持多个 API 副本并行修改密钥。

Jev 默认关闭。服务器配置使用 `http://localjev:8080`、`localjev-latest` 和独立内部密钥；先启用影子模式并执行网页连接测试。LocalJev 没有宿主机端口，128 MiB 内存限额，使用现有模型的云端 API。健康检查只检查服务进程；网页 `/api/jev/status` 另检查上游就绪和带鉴权模型列表。上游模型名必须出现在云端 `/models` 中；本次实测 `deepseek-chat` 请求实际解析为 `deepseek-flash`，所以适配器使用正式名称。其他账号应先核实自己的模型列表和推理响应，不能照抄不可用名称。Windows 上的 `127.0.0.1` 地址不会自动指向原电脑。

2026-10-16 的主动筛选质量/耗时门槛未通过，生产保留影子模式。阈值 0.82 本身不能保证正确。复验可运行 `python scripts/evaluate-jev-screening.py --output output/task-subscription/jev-evaluation.json`：它读取有效模型配置，使用独立临时库和固定案例，不发邮件或写 Zotero，但会产生云端调用费用。详见 [验收记录](LOCALJEV_CLOUD_VALIDATION_2026-10-16.md)。

## 运维、更新与回退

```sh
cd /opt/literature-agent
docker compose -f compose.server.yaml ps
docker compose -f compose.server.yaml logs --tail 80 app
docker stats --no-stream literature-agent-app-1
curl --fail http://127.0.0.1:18081/api/scheduler
```

应用重启由 `restart: unless-stopped` 管理。检查 Docker 服务开机启动。健康检查失败会在 Compose 中显示，但不会单独触发重启；退出或主机重启才按重启策略拉起。

更新前检查运行状态，等待任务结束并暂停调度。备份数据库、`settings.json` 和 `secrets.json`，构建新固定标签后修改 `.env`，执行 `up -d`，核验健康、历史、订阅和调度。保留旧镜像及迁移前备份；回退代码时检查数据库迁移兼容性，必要时停服恢复匹配备份。不要移动已有 Git 发布标签。

恢复必须停服，先备份当前数据，再恢复 SQLite 文件及所需配置/密钥、修正权限后启动。数据库备份不包含设置和密钥；单独备份它们。容器停止宽限时间为 30 分钟，超过后可能被终止，不应把停止操作当作无损迁移方法。

若网页打不开，先检查 SSH 隧道和服务器健康；若没有邮件，检查启用状态、时区、当天订阅运行及投递记录、模型/SMTP 配置和调度错误。HTTP 429 仍取决于上游来源配额，迁到服务器不保证消除限流。

影响因子排查：只读检查 `GET /api/journal-metrics` 的开关和缓存计数，以及运行 artifacts 的 `journal_metrics` 统计。查询预算 60 秒、并发 2；官网验证页/403/429 视为失败，24 小时后由后续运行再查。已有值的年份可能早于当前年份，这是保留已核实数据的降级行为。不要通过重跑每日订阅测试指标，以免重复邮件/导入；使用隔离临时库验证。JIF 缓存由 `20261017_0005` 引入；当前数据库版本为 `20261018_0006`，回退需配套迁移前备份。
