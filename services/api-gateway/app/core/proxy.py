"""
Reverse proxy core.

WHY a thin httpx-based forwarder instead of a full proxy library: the
gateway's proxying needs are simple (forward method/path/headers/body,
return the response verbatim) — a dedicated proxy library would add a
dependency for functionality httpx already gives us in ~30 lines, and
keeping it this small means the auth/rate-limit logic around it (which is
the part actually worth testing carefully) isn't buried in framework code.
"""

import httpx

from platform_common.exceptions import DependencyUnavailableError, NotFoundError

from app.core.config import RouteEntry

# Headers that are connection-specific and must NOT be forwarded as-is —
# forwarding them would either break the proxied connection (hop-by-hop
# headers) or leak the gateway's own host details.
_HOP_BY_HOP_HEADERS = {
    "connection",
    "keep-alive",
    "transfer-encoding",
    "te",
    "trailer",
    "upgrade",
    "host",
    "content-length",  # httpx recalculates this from the actual body we send
}


def match_route(path: str, route_table: list[RouteEntry]) -> RouteEntry:
    for entry in route_table:
        if path.startswith(entry.prefix):
            return entry
    raise NotFoundError(f"No upstream service registered for path '{path}'")


async def forward_request(
    client: httpx.AsyncClient,
    *,
    method: str,
    path: str,
    upstream_base_url: str,
    headers: dict[str, str],
    query_params: dict[str, str],
    body: bytes,
    trace_id: str,
) -> httpx.Response:
    outgoing_headers = {k: v for k, v in headers.items() if k.lower() not in _HOP_BY_HOP_HEADERS}
    outgoing_headers["X-Trace-Id"] = trace_id
    outgoing_headers["X-Forwarded-By"] = "api-gateway"

    url = f"{upstream_base_url}{path}"

    try:
        return await client.request(
            method,
            url,
            headers=outgoing_headers,
            params=query_params,
            content=body,
        )
    except (httpx.ConnectError, httpx.ConnectTimeout):
        raise DependencyUnavailableError(
            "Upstream service is unreachable", details={"upstream": upstream_base_url}
        )
    except httpx.TimeoutException:
        raise DependencyUnavailableError(
            "Upstream service timed out", details={"upstream": upstream_base_url}
        )
