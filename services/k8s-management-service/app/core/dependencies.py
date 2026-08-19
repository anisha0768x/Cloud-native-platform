from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import K8sManagementServiceSettings
from app.repositories.k8s_repository import K8sRepository
from app.services.k8s_service import K8sService


def get_settings(request: Request) -> K8sManagementServiceSettings:
    return request.app.state.settings


async def get_db_session(request: Request) -> AsyncSession:
    async with request.app.state.db.session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


def get_k8s_service(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> K8sService:
    # The cluster provider is built ONCE at app startup (see main.py) and
    # stored on app.state — constructing a KubernetesClusterProvider per
    # request would reload kubeconfig/ServiceAccount credentials on every
    # single call, which is wasteful and unnecessary since the client is
    # safe to reuse across requests.
    return K8sService(request.app.state.cluster_provider, K8sRepository(session))
