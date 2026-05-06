"""Docker 客户端 — 本地开发用，替代 K8s（WSL 兼容，端口智能分配）"""
import logging
import os
import socket

import docker

from infra.config import collect_sandbox_env, config

logger = logging.getLogger(__name__)
_client: docker.DockerClient = None


def _find_free_port(start: int = 9000, end: int = 9999) -> int:
    """找一个空闲端口"""
    for port in range(start, end):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("", port))
                return port
            except OSError:
                continue
    raise RuntimeError(f"No free port in {start}-{end}")


def get_docker() -> docker.DockerClient:
    global _client
    if _client is None:
        _client = docker.from_env()
    return _client


def _hermes_config_volumes() -> dict | None:
    """
    Optionally share the host Hermes config directory with the container.

    Hermes CLI/library use ~/.hermes (config.yaml, .env). When Docker runs on WSL,
    config.HERMES_CONFIG_HOST_PATH should resolve to that same tree (e.g. /home/you/.hermes).
    """
    if not config.SANDBOX_MOUNT_HERMES_CONFIG:
        return None
    host_path = os.path.abspath(os.path.expanduser(config.HERMES_CONFIG_HOST_PATH))
    if not os.path.isdir(host_path):
        logger.warning(
            "SANDBOX_MOUNT_HERMES_CONFIG is set but host path is not a directory: %s",
            host_path,
        )
        return None
    # runtime image CMD runs as root; Hermes resolves ~/.hermes -> /root/.hermes
    return {host_path: {"bind": "/root/.hermes", "mode": "rw"}}


def create_sandbox_container(image: str = "hermes-runtime:latest") -> tuple[str, int]:
    """创建沙箱容器，返回 (容器 ID, 宿主端口)"""
    host_port = _find_free_port()
    c = get_docker()
    env = collect_sandbox_env()
    run_kw = dict(
        detach=True,
        labels={"managed-by": "agent-runtime", "type": "sandbox"},
        ports={"8000/tcp": host_port},
        mem_limit="512m",
        cpu_quota=50000,
    )
    if env:
        run_kw["environment"] = env
    vols = _hermes_config_volumes()
    if vols:
        run_kw["volumes"] = vols
        logger.info("Mounting host Hermes config into sandbox: %s -> /root/.hermes", list(vols.keys()))
    container = c.containers.run(image, **run_kw)
    logger.info(f"✅ Container created: {container.short_id} → localhost:{host_port}")
    return container.id, host_port


def delete_sandbox_container(container_id: str):
    """删除容器"""
    try:
        c = get_docker()
        container = c.containers.get(container_id)
        container.remove(force=True)
        logger.info(f"🗑️  Container deleted: {container_id[:12]}")
    except Exception as e:
        logger.warning(f"Container delete failed {container_id[:12]}: {e}")


def cleanup_all_sandboxes():
    """清理所有 agent-runtime 管理的容器"""
    c = get_docker()
    containers = c.containers.list(all=True, filters={"label": "managed-by=agent-runtime"})
    for container in containers:
        try:
            container.remove(force=True)
            logger.info(f"🗑️  Cleaned up: {container.short_id}")
        except Exception:
            pass
