"""MinIO async wrapper."""
import io
import asyncio
from functools import partial
from minio import Minio
from minio.error import S3Error
from app.config import settings

_client: Minio | None = None


def _get_client() -> Minio:
    global _client
    if _client is None:
        _client = Minio(
            settings.MINIO_ENDPOINT,
            access_key=settings.MINIO_ACCESS_KEY,
            secret_key=settings.MINIO_SECRET_KEY,
            secure=settings.MINIO_SECURE,
        )
    return _client


async def ensure_bucket() -> None:
    loop   = asyncio.get_event_loop()
    client = _get_client()
    exists = await loop.run_in_executor(
        None, partial(client.bucket_exists, settings.MINIO_BUCKET)
    )
    if not exists:
        await loop.run_in_executor(
            None, partial(client.make_bucket, settings.MINIO_BUCKET)
        )


async def put_object(object_name: str, data: bytes, content_type: str) -> None:
    loop   = asyncio.get_event_loop()
    client = _get_client()
    await loop.run_in_executor(
        None,
        partial(
            client.put_object,
            settings.MINIO_BUCKET,
            object_name,
            io.BytesIO(data),
            len(data),
            content_type=content_type,
        ),
    )


async def get_object(object_name: str) -> bytes:
    loop   = asyncio.get_event_loop()
    client = _get_client()

    def _read():
        response = client.get_object(settings.MINIO_BUCKET, object_name)
        try:
            return response.read()
        finally:
            response.close()
            response.release_conn()

    return await loop.run_in_executor(None, _read)


async def remove_object(object_name: str) -> None:
    loop   = asyncio.get_event_loop()
    client = _get_client()
    try:
        await loop.run_in_executor(
            None,
            partial(client.remove_object, settings.MINIO_BUCKET, object_name),
        )
    except S3Error:
        pass


async def list_objects(prefix: str) -> list[str]:
    loop   = asyncio.get_event_loop()
    client = _get_client()

    def _list():
        return [
            obj.object_name
            for obj in client.list_objects(settings.MINIO_BUCKET, prefix=prefix, recursive=True)
        ]

    return await loop.run_in_executor(None, _list)


                                
def get_object_sync(object_name: str) -> bytes:
    client   = _get_client()
    response = client.get_object(settings.MINIO_BUCKET, object_name)
    try:
        return response.read()
    finally:
        response.close()
        response.release_conn()


def put_object_sync(object_name: str, data: bytes, content_type: str) -> None:
    client = _get_client()
    client.put_object(
        settings.MINIO_BUCKET, object_name,
        io.BytesIO(data), len(data), content_type=content_type,
    )
