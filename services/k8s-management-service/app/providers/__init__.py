from app.providers.base import ClusterProvider, DeploymentInfo, NodeInfo, PodInfo
from app.providers.demo_provider import DemoClusterProvider


def build_cluster_provider(mode: str) -> ClusterProvider:
    """
    Factory, so main.py doesn't need to know about either concrete
    implementation — it just reads settings.CLUSTER_MODE and gets a
    working provider back.
    """
    if mode == "kubernetes":
        from app.providers.kubernetes_provider import KubernetesClusterProvider

        return KubernetesClusterProvider()
    return DemoClusterProvider()


__all__ = ["ClusterProvider", "NodeInfo", "PodInfo", "DeploymentInfo", "DemoClusterProvider", "build_cluster_provider"]
