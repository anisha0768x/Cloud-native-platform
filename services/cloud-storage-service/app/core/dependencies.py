from fastapi import Request

from app.core.config import CloudStorageServiceSettings
from app.services.storage_service import CloudStorageService


def get_settings(request: Request) -> CloudStorageServiceSettings:
    return request.app.state.settings


def get_storage_service(request: Request) -> CloudStorageService:
    settings: CloudStorageServiceSettings = request.app.state.settings
    return CloudStorageService(request.app.state.storage_provider, max_upload_size_bytes=settings.MAX_UPLOAD_SIZE_BYTES)
