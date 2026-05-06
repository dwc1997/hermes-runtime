# Agent Runtime

OpenAI 兼容网关：**宿主机（控制面进程）内嵌单一 Hermes `AIAgent`**；与 [Hermes 官方 Docker 文档](https://hermes-agent.nousresearch.com/docs/user-guide/docker) 一致——**工具/终端隔离走 Hermes 自己的 terminal backend（如 Docker）**，而不是「每个会话起一个内置 Hermes 的沙箱 Pod」。

## 架构

```
POST /v1/chat/completions  （OpenAI 形状，带 session_id）
       │
       ▼
┌────────────────────────────────────────────────────────────┐
│  FastAPI 控制面（单进程，uvicorn）                          │
│  Dispatcher → SessionRouter（Redis：会话元数据）             │
│  → HermesRuntimeBridge.run_conversation（run_agent.AIAgent）│
└────────────────────────────────────────────────────────────┘
       │  terminal / exec 等工具（若启用）
       ▼
┌────────────────────────────────────────────────────────────┐
│  Hermes 配置的隔离后端（宿主机 Docker / SSH / …）            │
│  见：hermes config / ~/.hermes/config.yaml                   │
└────────────────────────────────────────────────────────────┘
```

- **会话隔离**：`session_id` → `conversation_history` + `task_id`（进程内字典；销毁会话可 `DELETE /sessions/{id}`）。
- **`core/sandbox/*`**：旧版「每会话 K8s Pod / Docker 沙箱跑 Hermes」代码仍保留在仓库中，**默认路径已不再调用**。

## 验证（幂等）

```bash
bash scripts/verify_host_hermes.sh
# Uses Redis on host port 16379 by default (avoids conflict with local :6379).
# VERIFY_REDIS_HOST_PORT=26379 bash scripts/verify_host_hermes.sh   # if 16379 is busy
# Uses ./.venv or creates it — avoids Ubuntu/Debian PEP 668 (externally-managed-environment).
# If venv has no pip: script bootstraps via ensurepip or get-pip.py; or run:
#   sudo apt install python3-pip python3-venv python3-full
```

密钥：**不必**再设 `OPENROUTER_API_KEY`。若本机已用 `hermes model` 配好 **`~/.hermes`**，`AIAgent` 会像 CLI 一样读 **`~/.hermes/.env`** 与 **`config.yaml`**（代码里只有设置了环境变量才会覆盖）。脚本在检测到 `~/.hermes/.env` 或相关 env 时会自动跑一轮 chat。

脚本会：**删除**带 `managed-by=agent-runtime` 的旧沙箱容器、**重建** `agent-runtime-redis`、`pip install`、临时启动 `:8080` 并 `curl /health`。

## 清理（手动；破坏性）

此前若构建过「每会话 Hermes」镜像、或跑过 Kind：

```bash
docker rm -f agent-runtime-redis
docker ps -aq --filter label=managed-by=agent-runtime | xargs -r docker rm -f   # Linux
docker rmi hermes-runtime:latest    # 旧 Dockerfile.runtime 镜像，不需要可删
kind delete cluster --name hermes-runtime
```

## Kind / K8s

```bash
bash scripts/setup_kind.sh
# k8s/secret.yaml：默认只有开关项；密钥请放在挂载的 ~/.hermes 或按需增加 Secret 键
bash scripts/deploy.sh
bash scripts/test.sh
```

控制面镜像 **`Dockerfile`** 内含 `hermes-agent`。若要在集群里使用 **terminal.backend docker**，需在 Deployment 上挂宿主 **`/var/run/docker.sock`**（有安全风险，仅建议测试环境）。

## 目录结构（节选）

```
├── app/                 # FastAPI
├── core/session/        # SessionRouter
├── core/sandbox/        # 遗留：按会话起 Pod（未接默认路径）
├── runtime/agent/       # HermesRuntimeBridge
├── scripts/verify_host_hermes.sh
├── Dockerfile           # 生产控制面镜像（含 Hermes）
└── Dockerfile.runtime   # 遗留：独立 /execute Pod 镜像
```

## API

请求体里的 **`model`**：默认占位符 **`hermes`** 表示「交给 Hermes 按 `~/.hermes` 解析」。若嵌入库未正确读出你在 YAML 里配的型号（个别提供商会出现空 model），请在 JSON 里写上 **`config.yaml` 里同一套模型 id**，或设置环境变量 **`HERMES_MODEL`**。

| 端点 | 方法 | 说明 |
|------|------|------|
| `/v1/chat/completions` | POST | OpenAI 兼容聊天 |
| `/health` | GET | 健康检查 |
| `/status` | GET | 运行模式说明 |
| `/sessions/{id}` | DELETE | 丢弃进程内历史并删 Redis 会话键 |

## Hermes 配置提示

- **不要用顶层包名 `tools/`**：会与 **`hermes-agent` 自带的 `tools` 包**冲突（`ModuleNotFoundError: tools.registry`）。旧的示例已改名为 **`demo_tools/`**。
- **模型与密钥**：与 CLI 相同，优先 **`~/.hermes/.env`** + **`config.yaml`**。本项目的 `OPENROUTER_API_KEY` 等**仅作可选覆盖**（适合 K8s Secret、CI）；宿主已配好 Hermes 时**不用**在 `.env` 里重复写。
- **终端沙箱**：在宿主执行例如 `hermes config set terminal.backend docker`，详见 [Docker backend](https://hermes-agent.nousresearch.com/docs/user-guide/configuration#docker-backend)。
