"""Local-development endpoints behind the HMAC "signed" storage URLs.

PUT  /storage/upload  - receive an upload for a grant issued by /media/upload-url
GET  /storage/serve   - serve an object for a grant issued by a download URL

Tokens bind method, key, expiry and (for uploads) the byte cap. In production
these are replaced by S3/R2 presigned URLs and this router is not mounted.
"""

from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse

from app.api.deps import DbSession
from app.db.models import MediaAsset, MediaStatus
from app.storage.factory import get_storage

router = APIRouter(prefix="/storage", tags=["storage (local dev)"])


@router.put("/upload", status_code=204)
async def upload(
    request: Request,
    db: DbSession,
    key: str,
    expires: int,
    max_bytes: int,
    token: str,
) -> None:
    storage = get_storage()
    if not storage.verify_token("PUT", key, expires, max_bytes, token):
        raise HTTPException(403, "Invalid or expired upload grant")

    # One grant, one object: the media row must still be waiting for its bytes.
    asset = db.query(MediaAsset).filter(MediaAsset.storage_key == key).first()
    if asset is None or asset.status not in (MediaStatus.pending, MediaStatus.uploading):
        raise HTTPException(409, "Upload grant already used or media asset not found")

    declared = request.headers.get("content-length")
    if declared is not None and declared.isdigit() and int(declared) > max_bytes:
        raise HTTPException(413, "File exceeds the size granted for this upload")

    tmp = storage.root / f"_tmp_{uuid.uuid4().hex}"
    total = 0
    try:
        with tmp.open("wb") as fh:
            async for chunk in request.stream():
                total += len(chunk)
                if total > max_bytes:
                    raise HTTPException(413, "File exceeds the size granted for this upload")
                fh.write(chunk)
        if total == 0:
            raise HTTPException(422, "Empty upload")
        storage.put_file(key, tmp)
    finally:
        Path(tmp).unlink(missing_ok=True)

    asset.status = MediaStatus.uploaded
    asset.file_size_bytes = total
    db.commit()


@router.get("/serve")
def serve(key: str, expires: int, token: str) -> FileResponse:
    storage = get_storage()
    if not storage.verify_token("GET", key, expires, 0, token):
        raise HTTPException(403, "Invalid or expired download link")
    if not storage.exists(key):
        raise HTTPException(404, "Object not found")
    return FileResponse(storage.get_path(key), headers={"Cache-Control": "private, no-store"})
