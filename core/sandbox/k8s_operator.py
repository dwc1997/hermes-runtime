"""K8s/Docker 操作层 — 创建/销毁 Pod/Container"""
import logging
import uuid
import os
from infra.config import config

logger = logging.getLogger(__name__)

# 根据环境选择 backend
USE_DOCKER = os.getenv("USE_DOCKER", "true").lower() == "true"


def create_sandbox_pod() -> tuple[str, str, int | None]:
    """创建沙箱，返回 (Pod/Container 名, IP, 宿主端口)"""
    if USE_DOCKER:
        return _create_docker()
    else:
        return _create_k8s_pod()


def delete_sandbox_pod(pod_name: str):
    """删除 Pod/Container"""
    if USE_DOCKER:
        _delete_docker(pod_name)
    else:
        _delete_k8s_pod(pod_name)


def get_pod_ip(pod_name: str) -> str | None:
    """获取 Pod/Container IP"""
    if USE_DOCKER:
        return _get_docker_ip(pod_name)
    else:
        return _get_k8s_pod_ip(pod_name)


# ─── Docker 实现 ───────────────────────────

def _create_docker() -> tuple[str, str, int | None]:
    from infra.docker_client import create_sandbox_container
    container_id, host_port = create_sandbox_container(config.SANDBOX_IMAGE)
    logger.info(f"✅ Docker container created: {container_id[:12]} → localhost:{host_port}")
    return container_id, "127.0.0.1", host_port


def _delete_docker(container_id: str):
    from infra.docker_client import delete_sandbox_container
    delete_sandbox_container(container_id)


def _get_docker_ip(container_id: str) -> str | None:
    return "127.0.0.1"


def _create_k8s_pod() -> tuple[str, str, int | None]:
    from kubernetes import client as k8s_client
    from infra.k8s_client import core_v1

    pod_name = f"hermes-sandbox-{uuid.uuid4().hex[:12]}"
    pod = k8s_client.V1Pod(
        metadata=k8s_client.V1ObjectMeta(
            name=pod_name,
            labels={"app": "hermes-sandbox", "managed-by": "agent-runtime"},
        ),
        spec=k8s_client.V1PodSpec(
            containers=[
                k8s_client.V1Container(
                    name="runtime",
                    image=config.SANDBOX_IMAGE,
                    ports=[k8s_client.V1ContainerPort(container_port=config.SANDBOX_PORT)],
                    env_from=[
                        k8s_client.V1EnvFromSource(
                            secret_ref=k8s_client.V1SecretEnvSource(
                                name=config.SANDBOX_ENV_SECRET,
                                optional=True,
                            ),
                        ),
                    ],
                    resources=k8s_client.V1ResourceRequirements(
                        requests={"cpu": "200m", "memory": "256Mi"},
                        limits={"cpu": "1", "memory": "1Gi"},
                    ),
                )
            ],
            restart_policy="Never",
        ),
    )
    core_v1().create_namespaced_pod(namespace=config.K8S_NAMESPACE, body=pod)
    logger.info(f"✅ K8s Pod created: {pod_name}")
    return pod_name, "", None


def _delete_k8s_pod(pod_name: str):
    from infra.k8s_client import core_v1
    try:
        core_v1().delete_namespaced_pod(name=pod_name, namespace=config.K8S_NAMESPACE)
        logger.info(f"🗑️  K8s Pod deleted: {pod_name}")
    except Exception as e:
        logger.warning(f"Pod delete failed {pod_name}: {e}")


def _get_k8s_pod_ip(pod_name: str) -> str | None:
    from infra.k8s_client import core_v1
    try:
        pod = core_v1().read_namespaced_pod(name=pod_name, namespace=config.K8S_NAMESPACE)
        return pod.status.pod_ip
    except Exception:
        return None
