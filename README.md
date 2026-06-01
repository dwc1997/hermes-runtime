# Hermes Agent Runtime

轻量级 Agent 沙箱部署系统：OpenAI 兼容 API 网关，内嵌 Hermes AIAgent 作为决策引擎，通过 AgentScope Runtime 提供**工具执行沙箱**（Tool Execution Sandbox）隔离。

## 架构设计

### 双 Plane 分离

```
Decision Plane (控制面，当前同进程)         Execution Plane (执行面)
┌──────────────────────────────┐          ┌──────────────────────────┐
│ FastAPI + Hermes AIAgent     │  HTTP    │ AgentScope SandboxManager│
│ • 接收 /chat 请求            │─────────►│ • Docker 容器池管理       │
│ • 调 LLM 推理                │          │ • 心跳 / 回收 / 恢复      │
│ • 工具路由到沙箱              │          │ • 多后端 (Docker/gVisor)  │
│ • 会话管理 (Redis)           │          └──────────────────────────┘
└──────────┬───────────────────┘
           │
    ┌──────▼──────┐
    │    Redis    │
    │ 会话元数据   │
    │ 沙箱绑定    │
    └─────────────┘
```

**Decision Plane**：Agent 逻辑、LLM 推理、对话管理。当前与 FastAPI 同进程运行。

**Execution Plane**：工具执行隔离。Hermes 内置的 `terminal` / `code_execution` 被禁用，替换为 `sandbox_shell` / `sandbox_python`，命令通过 AgentScope SandboxManager 转发到独立 Docker 容器执行。

### 工具执行沙箱 vs Agent 沙箱

| | 工具执行沙箱（当前方案） | Agent 沙箱（MicroVM） |
|---|---|---|
| **隔离对象** | 危险命令（shell/python） | 整个 Agent 实例 |
| **隔离级别** | Docker 容器级 | MicroVM 硬件级 |
| **适用场景** | 可信 Agent，防 LLM 幻觉 | 多租户，不可信 Agent/模型 |
| **资源开销** | 轻量 | 重（完整 OS 内核） |
| **典型产品** | AgentScope, E2B, OpenClaw | 阿里 ACS, 腾讯 Cube, Anthropic Managed Agents |

当前方案定位于**轻量级工具隔离**——Agent 本身是可信的，只需要防止 LLM 生成危险命令影响宿主机或跨 session 串扰。

### 请求链路

```
POST /v1/chat/completions
  │
  ├─► SessionRouter.handle()
  │     ├─ Redis 读/写 session 元数据
  │     ├─ ensure_session_sandbox() → 从池里获取容器，绑定到 session
  │     └─ touch_sandbox_bind_ttl() → 续期 Redis TTL
  │
  ├─► HermesRuntimeBridge.run_turn()
  │     ├─ 创建 AIAgent 实例（禁用 terminal/code_execution，启用 gateway_sandbox）
  │     ├─ 传入 conversation_history（进程内存）
  │     ├─ 调 LLM 推理
  │     ├─ LLM 调用 sandbox_shell/sandbox_python
  │     │     └─► AgentScope mgr.call_tool() → Docker 容器执行 → 返回结果
  │     └─ 更新 conversation_history
  │
  └─► 返回 OpenAI 格式响应
```

## 启动

### 本地 Debug

```bash
pip install -r requirements.txt
python run_debug.py          # hot-reload, 127.0.0.1:8080
```

### 命令行

```bash
python -m uvicorn app.main:app --host 127.0.0.1 --port 8080
```

### 带沙箱池

```bash
export AGENTSCOPE_SANDBOX_POOL_SIZE=1
export CONTAINER_DEPLOYMENT=docker
python run_debug.py
```

### 远程 Sandbox Manager

```bash
export SANDBOX_MANAGER_BASE_URL=http://sandbox-manager:8080
python run_debug.py
```

## 会话绑定与工具路由

| 变量 | 默认 | 作用 |
|------|------|------|
| `SANDBOX_BIND_SESSION` | `1` | 每条消息进 Hermes 前自动 acquire 容器，Redis `sandbox:bind:{session_id}` → `container_name`，TTL = `SESSION_TIMEOUT` |
| `SANDBOX_ROUTE_HERMES_TOOLS` | `1` | 禁用 Hermes 内置 `terminal` / `code_execution`，注册 `sandbox_shell` / `sandbox_python` |
| `HERMES_ENABLED_TOOLSETS` | 未设 | 用白名单时必须包含 `gateway_sandbox`（或自定义的 `SANDBOX_GATEWAY_TOOLSET`） |

核心代码路径：

- **工具替换**：[runtime/agent/agent_factory.py](runtime/agent/agent_factory.py) `_make_agent()` — 禁用 host 工具集，启用 gateway sandbox 工具集
- **工具注册**：[runtime/hermes_gateway_sandbox_tools.py](runtime/hermes_gateway_sandbox_tools.py) `ensure_gateway_sandbox_tools_registered()` — 向 Hermes registry 注册 `sandbox_shell`/`sandbox_python` 及 handler
- **沙箱调度**：[runtime/hermes_gateway_sandbox_tools.py](runtime/hermes_gateway_sandbox_tools.py) `_dispatch_shell()`/`_dispatch_python()` — 解析容器 → AgentScope `mgr.call_tool()` → Docker 执行
- **会话绑定**：[infra/session_sandbox_bind.py](infra/session_sandbox_bind.py) `ensure_session_sandbox()` — session → 容器 acquire/release

## 目录结构

```
├── app/                          # FastAPI 入口 + 路由
│   ├── main.py                   # lifespan：启动/关闭 SandboxManager + Redis
│   └── api/routes.py             # /v1/chat/completions, /health, /sessions, /sandbox/v1/*
├── core/
│   ├── sandbox_service/          # SandboxService facade（acquire/release/run_shell/run_python）
│   ├── scheduler/dispatcher.py   # Dispatcher — FastAPI 入口
│   └── session/session_router.py # SessionRouter — Redis 元数据 + 调 Hermes
├── infra/
│   ├── agentscope_sandbox_service.py  # SandboxManager 启动（remote HTTP 或 embedded pool）
│   ├── session_sandbox_bind.py   # session → 容器绑定（acquire/release/touch）
│   ├── redis_client.py           # 异步 Redis（session 元数据 + sandbox bind）
│   ├── redis_sync_client.py      # 同步 Redis（供 Hermes 工具 handler 线程使用）
│   ├── runtime_sandbox_flags.py  # 功能开关
│   └── config.py                 # 全局配置
├── runtime/
│   ├── agent/agent_factory.py    # HermesRuntimeBridge — AIAgent 创建 + 工具路由
│   ├── hermes_gateway_sandbox_tools.py  # sandbox_shell / sandbox_python 注册 + handler
│   └── hermes_active_context.py  # thread-local bridge 引用（工具 handler 回查 session）
├── models/                       # Pydantic 数据模型
├── scripts/test_local.py         # 本地验证脚本
├── run_debug.py                  # 本地 debug 入口
├── requirements.txt
├── Dockerfile
└── .env.example
```

## API

| 端点 | 方法 | 说明 |
|------|------|------|
| `/v1/chat/completions` | POST | OpenAI 兼容聊天，body: `session_id`, `messages`, `model` |
| `/health` | GET | 健康检查 |
| `/status` | GET | 运行模式 + 沙箱状态 |
| `/sessions/{id}` | DELETE | 销毁会话：释放沙箱 + 清空对话历史 + 删 Redis |
| `/sandbox/v1/status` | GET | 沙箱执行面状态 |
| `/sandbox/v1/acquire` | POST | 申请沙箱容器 |
| `/sandbox/v1/run-python` | POST | 沙箱内执行 Python |
| `/sandbox/v1/run-shell` | POST | 沙箱内执行 shell |
| `/sandbox/v1/release` | POST | 释放沙箱容器 |

## 当前局限 & 未来路线图

### 当前适用场景

- 单 worker 运行（`--workers 1` 或 `run_debug.py`）
- 对话历史存进程内存，进程重启丢失
- 沙箱后端：Docker（AgentScope Runtime embedded pool）
- 无认证 / 无流式响应 / 无 rate limiting

### 生产级路线图

#### P0 — 数据持久化（不丢数据）

当前最大风险：对话历史存进程内存，重启全丢。

- [ ] **对话历史迁入 Redis** — `_histories[session_id]` → `session:{id}:history`（LPUSH + LTRIM 保留最近 N 条）
- [ ] **对话归档到 PostgreSQL** — 会话结束后写 `conversations` 表（摘要）+ `messages` 表（完整消息），Redis 释放内存
- [ ] **消息全文搜索** — PostgreSQL GIN 索引 on `messages.content`，支持"上次聊的那个沙箱问题"类查询
- [ ] **大文件存对象存储** — 用户上传的图片/文档/代码产物 → S3/MinIO，只存 URL 到数据库

#### P1 — 多用户隔离（不同用户不同 AGENTS.md）

当前无用户概念，session_id 客户端自报，无隔离。

- [ ] **用户认证** — JWT / API Key → `user_id`，所有后续数据按 user_id 隔离
- [ ] **用户 Profile 存储** — Redis Hash `user:{id}:profile` 存储：
  - `agents_md` — 用户自定义 Agent 行为规则
  - `user_md` — 用户画像（偏好、习惯、背景）
  - `memory_md` — Agent 跨会话记忆
  - `skills` — 用户积累的可复用技能
- [ ] **Frozen Snapshot 注入** — 每次请求从 Redis 读取用户 profile，拼装到 system prompt，会话中途不变（保护 LLM prefix cache）
- [ ] **新用户初始化** — 注册时写入默认 AGENTS.md 模板，user_md 和 memory_md 留空由 review agent 自动填充
- [ ] **沙箱用户目录注入** — 创建容器时通过环境变量注入用户 profile（`-e USER_AGENTS_MD=...`），不是 volume mount
- [ ] **开启 Hermes memory/context_files** — `HERMES_SKIP_MEMORY=false`, `HERMES_SKIP_CONTEXT_FILES=false`（当前硬编码 true）

#### P2 — 高可用（无状态集群）

当前单实例，进程内存状态，无容错。

- [ ] **Chat Service 无状态化** — 所有状态迁入 Redis，Hermes 实例本身无任何本地状态
- [ ] **负载均衡** — Nginx / ALB 前置，多 Hermes 实例无差别服务
- [ ] **Redis Cluster** — 主从 + 哨兵，防 Redis 单点故障
- [ ] **分布式锁** — `threading.Lock` → Redis SET NX，支持多 worker 并发安全
- [ ] **沙箱池 Redis 化** — `redis_enabled=True`，多 Sandbox Manager 副本共享容器池
- [ ] **服务拆分** — Chat Service（无状态）+ Sandbox Manager（有状态）物理分离，各自独立扩缩
- [ ] **K8s 后端** — `CONTAINER_DEPLOYMENT=k8s`，沙箱容器以 Pod 形式运行
- [ ] **gVisor 加固** — 隔离级别从容器级提升到内核级

#### P3 — 自进化能力（Agent 持续学习）

当前 Agent 无记忆，每次对话从零开始。

- [ ] **后台 Review 机制** — 每轮对话结束后 fork 轻量 LLM 回放对话，判断是否需要保存 memory 或创建/更新 skill
  - 工具白名单：只开放 memory_write + skill_manage
  - 异步守护线程，不阻塞用户响应
  - Review prompt 从 Hermes `background_review.py` 移植（170 行纯文本）
- [ ] **Review 触发策略** — 每 3-5 轮触发一次（不是每轮），用便宜模型（qwen3-flash），控制 token 成本
- [ ] **Skill 生命周期管理（Curator）** — 每 7 天空闲时运行：
  - 30 天没用的 skill → 标记 stale
  - 90 天没用的 skill → 归档（不删除）
  - 合并重叠的 skill
  - 生成审查报告
- [ ] **技能版本化** — PostgreSQL `skills` 表支持 version 字段，`skill_changes` 表记录每次变更的 diff 和触发源
- [ ] **用户偏好捕获** — 用户纠正 style/tone/format/verbosity → review agent 自动更新对应 skill（不是只存 memory）

#### P4 — 生产加固（可观测、可控制）

- [ ] **流式响应** — SSE / WebSocket，前端实时显示 token
- [ ] **Rate Limiting** — 按 user_id 限流（Redis 令牌桶）
- [ ] **配额管理** — 每用户 token 预算，超限拒绝
- [ ] **可观测性** — 请求 trace_id 贯穿全链路，Prometheus 指标 + Grafana 面板
- [ ] **审计日志** — 每次 tool call 记录 user_id/session_id/tool_name/args/result_hash
- [ ] **沙箱资源限制** — 容器 CPU/内存/磁盘/网络配额，防恶意代码耗尽资源
- [ ] **优雅降级** — 沙箱不可用时降级到无沙箱模式（记录 warning，不阻断服务）

## Hermes 配置提示

- **模型与密钥**：与 CLI 一致，优先 `~/.hermes/.env` + `config.yaml`。本项目的 `OPENROUTER_API_KEY` 等仅作可选覆盖（适合 CI/Secret）。宿主已配好 Hermes 时不用在 `.env` 重复写。
- **终端沙箱（A 线）**：`hermes config set terminal.backend docker`，详见 [Docker backend](https://hermes-agent.nousresearch.com/docs/user-guide/configuration#docker-backend)。启用 B 线时 `sandbox_shell` 取代 Hermes Docker terminal。

## AgentScope 沙箱池配置

```bash
AGENTSCOPE_SANDBOX_POOL_SIZE=2     # 预热容器数（每种类型）
CONTAINER_DEPLOYMENT=docker        # docker / gvisor / k8s
AGENTSCOPE_SANDBOX_WATCHER_INTERVAL=15  # 池扫描间隔（秒）
AGENTSCOPE_SANDBOX_MOUNT_DIR=sessions_mount_dir
SANDBOX_MANAGER_BASE_URL=          # 远程 Manager URL（设置后跳过嵌入式池）
SANDBOX_MANAGER_TOKEN=             # 远程 Bearer token
```

完整环境变量见 [.env.example](.env.example)。
