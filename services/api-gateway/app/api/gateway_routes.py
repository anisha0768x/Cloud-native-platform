import uuid

from fastapi import APIRouter, Request, Response

from platform_common.exceptions import PlatformError
from platform_common.logging import bind_trace_id, get_logger

from app.core.auth_check import authenticate_request, resolve_rate_limit_key
from app.core.proxy import forward_request, match_route
from app.core.rate_limiter import RateLimiter

router = APIRouter()
logger = get_logger(__name__)


class RateLimitExceeded(PlatformError):
    status_code = 429
    code = "RATE_LIMIT_EXCEEDED"


@router.api_route(
    "/{full_path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
)
async def gateway_catch_all(full_path: str, request: Request):
    """
    Single entrypoint for all proxied traffic. Order of operations matters:
    1. Establish trace id (so even a rejected request is traceable in logs)
    2. Coarse auth check (cheapest reject: bad token never touches Redis or a backend)
    3. Rate limit (protects backends from a valid-but-abusive client)
    4. Route match + proxy (the actual work)
    Each step can short-circuit with a standard PlatformError, which the
    shared exception handler turns into the platform's standard error JSON.
    """
    settings = request.app.state.settings
    path = f"/{full_path}"

    trace_id = request.headers.get("x-trace-id") or str(uuid.uuid4())
    bind_trace_id(trace_id)

    token = authenticate_request(request, settings)

    rate_key = resolve_rate_limit_key(request, token)
    limiter: RateLimiter = request.app.state.rate_limiter
    result = await limiter.check(rate_key)
    if not result.allowed:
        raise RateLimitExceeded(
            "Too many requests", details={"retry_after_seconds": result.retry_after_seconds}
        )

    route = match_route(path, settings.route_table)

    body = await request.body()
    client = request.app.state.http_client
    upstream_response = await forward_request(
        client,
        method=request.method,
        path=path,
        upstream_base_url=route.upstream_base_url,
        headers=dict(request.headers),
        query_params=dict(request.query_params),
        body=body,
        trace_id=trace_id,
    )

    logger.info(
        "proxied request",
        extra={
            "method": request.method,
            "path": path,
            "upstream": route.upstream_base_url,
            "status_code": upstream_response.status_code,
        },
    )

    excluded_headers = {"content-length", "transfer-encoding", "connection"}
    response_headers = {
        k: v for k, v in upstream_response.headers.items() if k.lower() not in excluded_headers
    }
    response_headers["X-Trace-Id"] = trace_id

    return Response(
        content=upstream_response.content,
        status_code=upstream_response.status_code,
        headers=response_headers,
        media_type=upstream_response.headers.get("content-type"),
    )
