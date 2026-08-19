from fastapi import APIRouter, Depends, Query, Request, Response, UploadFile

from platform_common.security import TokenPayload, require_permission

from app.core.dependencies import get_storage_service
from app.schemas.storage import ObjectInfoResponse, PresignedUrlResponse, UploadResponse
from app.services.storage_service import CloudStorageService

router = APIRouter(prefix="/api/v1/storage", tags=["storage"])


@router.put("/objects/{key:path}", response_model=UploadResponse)
async def upload_object(
    key: str,
    file: UploadFile,
    storage: CloudStorageService = Depends(get_storage_service),
    _: TokenPayload = Depends(require_permission("storage:write")),
):
    data = await file.read()
    info = await storage.upload(key=key, data=data, content_type=file.content_type)
    return UploadResponse(key=info.key, size_bytes=info.size_bytes)


@router.get("/objects/{key:path}/presigned-url", response_model=PresignedUrlResponse)
async def presigned_url(
    key: str,
    request: Request,
    storage: CloudStorageService = Depends(get_storage_service),
    _: TokenPayload = Depends(require_permission("storage:read")),
):
    settings = request.app.state.settings
    url = await storage.presigned_url(key=key, expires_in_seconds=settings.PRESIGNED_URL_EXPIRY_SECONDS)
    return PresignedUrlResponse(key=key, url=url, expires_in_seconds=settings.PRESIGNED_URL_EXPIRY_SECONDS)


@router.get("/objects/{key:path}")
async def download_object(
    key: str,
    storage: CloudStorageService = Depends(get_storage_service),
    _: TokenPayload = Depends(require_permission("storage:read")),
):
    data = await storage.download(key=key)
    return Response(content=data, media_type="application/octet-stream")


@router.delete("/objects/{key:path}", status_code=204)
async def delete_object(
    key: str,
    storage: CloudStorageService = Depends(get_storage_service),
    _: TokenPayload = Depends(require_permission("storage:write")),
):
    await storage.delete(key=key)


@router.get("/objects", response_model=list[ObjectInfoResponse])
async def list_objects(
    prefix: str = Query(default=""),
    limit: int = Query(default=100, ge=1, le=1000),
    storage: CloudStorageService = Depends(get_storage_service),
    _: TokenPayload = Depends(require_permission("storage:read")),
):
    return await storage.list_objects(prefix=prefix, limit=limit)
