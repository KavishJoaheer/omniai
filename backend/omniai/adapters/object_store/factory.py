from __future__ import annotations

from omniai.adapters.object_store.local_fs import LocalFsObjectStore
from omniai.adapters.object_store.s3_compatible import S3CompatibleObjectStore
from omniai.config.settings import Settings
from omniai.ports.object_store import ObjectStorePort


def build_object_store(settings: Settings) -> ObjectStorePort:
    kind = settings.object_store_kind.lower()
    if kind == "local":
        return LocalFsObjectStore(settings.object_store_local_dir)
    if kind in {"s3", "minio"}:
        return S3CompatibleObjectStore(
            endpoint_url=settings.object_store_endpoint,
            region=settings.object_store_region,
            access_key=settings.object_store_access_key,
            secret_key=settings.object_store_secret_key,
            bucket=settings.object_store_bucket,
        )
    raise ValueError(f"Unsupported OBJECT_STORE_KIND={kind!r}")
