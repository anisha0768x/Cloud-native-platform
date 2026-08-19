from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.clients.anthropic_client import AnthropicClient
from app.clients.metrics_client import MetricsClient
from app.core.config import GenAiLogAnalysisServiceSettings
from app.repositories.analysis_repository import AnalysisRepository
from app.services.analysis_service import GenAiAnalysisService


def get_settings(request: Request) -> GenAiLogAnalysisServiceSettings:
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


def get_analysis_service(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> GenAiAnalysisService:
    settings: GenAiLogAnalysisServiceSettings = request.app.state.settings
    metrics_client = MetricsClient(
        request.app.state.http_client, settings.METRICS_SERVICE_URL, timeout=settings.BACKEND_CALL_TIMEOUT_SECONDS
    )
    llm_client = AnthropicClient(
        request.app.state.http_client,
        api_key=settings.ANTHROPIC_API_KEY,
        model=settings.ANTHROPIC_MODEL,
        timeout=settings.LLM_TIMEOUT_SECONDS,
        api_url=settings.ANTHROPIC_API_URL,
    )
    return GenAiAnalysisService(
        request.app.state.log_store,
        metrics_client,
        llm_client,
        AnalysisRepository(session),
        request.app.state.redis,
        recent_error_limit=settings.RECENT_ERROR_LOG_LIMIT,
        cache_ttl_seconds=settings.ANALYSIS_CACHE_TTL_SECONDS,
    )
