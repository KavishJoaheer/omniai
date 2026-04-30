from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator

from omniai.connectors.base import DiscoveredFile, guess_mime

logger = logging.getLogger(__name__)

_MAX_BYTES = 50 * 1024 * 1024


class S3Connector:
    """Mirrors objects from an S3 (or S3-compatible) bucket+prefix.

    Config schema:
        {
          "bucket": "knowledge",
          "prefix": "uploads/",
          "endpoint_url": null,           # null = AWS, set for MinIO etc.
          "region": "us-east-1",
          "access_key": "...",            # encrypted via SecretBox at write time
          "secret_key": "...",            # encrypted via SecretBox
          "extensions": [".pdf", ".md"]   # optional filter
        }

    Credentials are stored in the connector's encrypted config_json (the
    ConnectorService handles encryption). The connector itself just consumes
    plaintext config.
    """

    kind = "s3"

    async def discover(self, config: dict) -> AsyncIterator[DiscoveredFile]:
        try:
            import boto3
            from botocore.config import Config as BotoConfig
        except ImportError:
            logger.warning("s3 connector requires boto3")
            return

        bucket = config.get("bucket")
        if not bucket:
            return
        prefix = config.get("prefix", "") or ""
        allowed_exts = {e.lower() for e in (config.get("extensions") or [])}

        def _client():
            return boto3.client(
                "s3",
                endpoint_url=config.get("endpoint_url") or None,
                region_name=config.get("region") or "us-east-1",
                aws_access_key_id=config.get("access_key") or None,
                aws_secret_access_key=config.get("secret_key") or None,
                config=BotoConfig(signature_version="s3v4"),
            )

        client = await asyncio.to_thread(_client)

        # Page through bucket+prefix
        paginator = client.get_paginator("list_objects_v2")
        try:
            pages = await asyncio.to_thread(
                lambda: list(paginator.paginate(Bucket=bucket, Prefix=prefix))
            )
        except Exception as exc:
            logger.warning("s3 connector: list failed for s3://%s/%s: %s", bucket, prefix, exc)
            return

        for page in pages:
            for obj in page.get("Contents", []) or []:
                key = obj.get("Key")
                size = obj.get("Size", 0)
                if not key or key.endswith("/") or size == 0 or size > _MAX_BYTES:
                    continue
                if allowed_exts:
                    ext = ("." + key.rsplit(".", 1)[-1].lower()) if "." in key else ""
                    if ext not in allowed_exts:
                        continue
                try:
                    body = await asyncio.to_thread(
                        lambda k=key: client.get_object(Bucket=bucket, Key=k)["Body"].read()
                    )
                except Exception as exc:
                    logger.warning("s3 connector: get_object failed for %s: %s", key, exc)
                    continue
                filename = key.rsplit("/", 1)[-1]
                yield DiscoveredFile(
                    source_id=f"s3://{bucket}/{key}",
                    filename=filename,
                    mime_type=guess_mime(filename),
                    content=body,
                )

    @staticmethod
    def validate_config(config: dict) -> None:
        if not config.get("bucket"):
            raise ValueError("s3 config requires 'bucket'.")
