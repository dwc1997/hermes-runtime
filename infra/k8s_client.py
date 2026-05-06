"""K8s 客户端封装"""
import logging
from kubernetes import client, config as k8s_config
from infra.config import config

logger = logging.getLogger(__name__)
_core_v1: client.CoreV1Api = None
_apps_v1: client.AppsV1Api = None


def _init():
    global _core_v1, _apps_v1
    try:
        k8s_config.load_incluster_config()
    except k8s_config.ConfigException:
        k8s_config.load_kube_config(config_file=config.KUBECONFIG or None)
    _core_v1 = client.CoreV1Api()
    _apps_v1 = client.AppsV1Api()


def core_v1() -> client.CoreV1Api:
    global _core_v1
    if _core_v1 is None:
        _init()
    return _core_v1


def apps_v1() -> client.AppsV1Api:
    global _apps_v1
    if _apps_v1 is None:
        _init()
    return _apps_v1
