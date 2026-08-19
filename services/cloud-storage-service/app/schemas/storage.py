from datetime import datetime

from pydantic import BaseModel


class ObjectInfoResponse(BaseModel):
    key: str
    size_bytes: int
    last_modified: datetime
    content_type: str | None = None


class UploadResponse(BaseModel):
    key: str
    size_bytes: int
    uploaded: bool = True


class PresignedUrlResponse(BaseModel):
    key: str
    url: str
    expires_in_seconds: int
