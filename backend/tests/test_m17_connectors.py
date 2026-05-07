"""M17 — Connector Library Expansion tests.

Covers:
  1. Config validation for all six new connector kinds
  2. Google Drive connector (mocked Drive API)
  3. SharePoint connector (mocked Graph API via httpx)
  4. Notion connector (mocked Notion API via httpx)
  5. Confluence connector (mocked Confluence REST via httpx)
  6. Slack connector (mocked Slack Web API via httpx)
  7. Database connector (real SQLite in-memory via sqlalchemy)
  8. connector_service.preview_connector dry-run
  9. HTTP routes: GET /v1/connectors/kinds, POST /v1/connectors/preview
 10. SUPPORTED_KINDS list completeness
"""
from __future__ import annotations

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient

_ADMIN_EMAIL = "test@local.dev"
_ADMIN_PASSWORD = "TestPassword123!"


@pytest.fixture(scope="module")
def app():
    from omniai.interfaces.http.app import create_app
    return create_app()


@pytest.fixture(scope="module")
def client(app):
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


@pytest.fixture(scope="module")
def admin_token(client):
    r = client.post("/v1/auth/login", json={"email": _ADMIN_EMAIL, "password": _ADMIN_PASSWORD})
    assert r.status_code == 200, r.text
    return r.json()["data"]["accessToken"]


@pytest.fixture(scope="module")
def auth_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


# ══════════════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════════════

def _run(coro):
    """Run an async generator or coroutine synchronously."""
    import asyncio
    return asyncio.get_event_loop().run_until_complete(coro)


async def _collect(agen):
    """Drain an async generator into a list."""
    items = []
    async for item in agen:
        items.append(item)
    return items


# ══════════════════════════════════════════════════════════════════════════════
# 1. Config validation
# ══════════════════════════════════════════════════════════════════════════════

class TestConfigValidation:

    def test_google_drive_requires_credentials_or_token(self):
        from omniai.connectors.google_drive import GoogleDriveConnector
        with pytest.raises(ValueError, match="credentials_json.*access_token"):
            GoogleDriveConnector.validate_config({})

    def test_google_drive_rejects_both(self):
        from omniai.connectors.google_drive import GoogleDriveConnector
        with pytest.raises(ValueError, match="not both"):
            GoogleDriveConnector.validate_config({
                "credentials_json": json.dumps({"type": "service_account"}),
                "access_token": "tok",
            })

    def test_google_drive_validates_service_account_json(self):
        from omniai.connectors.google_drive import GoogleDriveConnector
        with pytest.raises(ValueError, match="service_account"):
            GoogleDriveConnector.validate_config({
                "credentials_json": json.dumps({"type": "user_account"})
            })

    def test_google_drive_access_token_valid(self):
        from omniai.connectors.google_drive import GoogleDriveConnector
        GoogleDriveConnector.validate_config({"access_token": "ya29.sometoken"})

    def test_sharepoint_requires_three_keys(self):
        from omniai.connectors.sharepoint import SharePointConnector
        for missing_key in ("tenant_id", "client_id", "client_secret"):
            cfg = {"tenant_id": "t", "client_id": "c", "client_secret": "s"}
            del cfg[missing_key]
            with pytest.raises(ValueError, match=missing_key):
                SharePointConnector.validate_config(cfg)

    def test_sharepoint_valid(self):
        from omniai.connectors.sharepoint import SharePointConnector
        SharePointConnector.validate_config({
            "tenant_id": "abc", "client_id": "def", "client_secret": "ghi"
        })

    def test_notion_requires_api_key(self):
        from omniai.connectors.notion import NotionConnector
        with pytest.raises(ValueError, match="api_key"):
            NotionConnector.validate_config({})

    def test_notion_valid(self):
        from omniai.connectors.notion import NotionConnector
        NotionConnector.validate_config({"api_key": "secret_abc123"})

    def test_confluence_requires_base_url_and_token(self):
        from omniai.connectors.confluence import ConfluenceConnector
        with pytest.raises(ValueError, match="base_url"):
            ConfluenceConnector.validate_config({"api_token": "t"})
        with pytest.raises(ValueError, match="api_token"):
            ConfluenceConnector.validate_config({"base_url": "https://x.atlassian.net"})

    def test_confluence_rejects_bad_url_scheme(self):
        from omniai.connectors.confluence import ConfluenceConnector
        with pytest.raises(ValueError, match="http"):
            ConfluenceConnector.validate_config({
                "base_url": "ftp://bad", "api_token": "t"
            })

    def test_confluence_valid(self):
        from omniai.connectors.confluence import ConfluenceConnector
        ConfluenceConnector.validate_config({
            "base_url": "https://myco.atlassian.net",
            "api_token": "tok",
        })

    def test_slack_requires_bot_token(self):
        from omniai.connectors.slack import SlackConnector
        with pytest.raises(ValueError, match="bot_token"):
            SlackConnector.validate_config({})

    def test_slack_rejects_invalid_token_prefix(self):
        from omniai.connectors.slack import SlackConnector
        with pytest.raises(ValueError, match="xoxb"):
            SlackConnector.validate_config({"bot_token": "invalid-token"})

    def test_slack_valid(self):
        from omniai.connectors.slack import SlackConnector
        SlackConnector.validate_config({"bot_token": "xoxb-123-456-abc"})

    def test_database_requires_connection_string(self):
        from omniai.connectors.database import DatabaseConnector
        with pytest.raises(ValueError, match="connection_string"):
            DatabaseConnector.validate_config({"table": "docs"})

    def test_database_requires_table(self):
        from omniai.connectors.database import DatabaseConnector
        with pytest.raises(ValueError, match="table"):
            DatabaseConnector.validate_config({"connection_string": "sqlite://"})

    def test_database_rejects_bad_url(self):
        from omniai.connectors.database import DatabaseConnector
        with pytest.raises(ValueError, match="SQLAlchemy URL"):
            DatabaseConnector.validate_config({
                "connection_string": "not-a-url", "table": "t"
            })

    def test_database_valid(self):
        from omniai.connectors.database import DatabaseConnector
        DatabaseConnector.validate_config({
            "connection_string": "sqlite:///:memory:", "table": "docs"
        })


# ══════════════════════════════════════════════════════════════════════════════
# 2. Google Drive connector (mocked)
# ══════════════════════════════════════════════════════════════════════════════

class TestGoogleDriveConnector:

    def _make_config(self):
        return {"access_token": "ya29.fake"}

    def test_discover_yields_files(self):
        """Mock the Drive API service and verify DiscoveredFile is produced."""
        import asyncio
        from omniai.connectors.google_drive import GoogleDriveConnector

        fake_file = {
            "id": "file123",
            "name": "report.pdf",
            "mimeType": "application/pdf",
        }
        fake_list_response = {"files": [fake_file], "nextPageToken": None}
        fake_content = b"%PDF fake content"

        # Mock _build_service and _download_file
        with patch("omniai.connectors.google_drive._build_service") as mock_build, \
             patch("omniai.connectors.google_drive._download_file", new_callable=AsyncMock) as mock_dl:

            mock_service = MagicMock()
            mock_service.files.return_value.list.return_value.execute.return_value = fake_list_response
            mock_build.return_value = mock_service
            mock_dl.return_value = fake_content

            connector = GoogleDriveConnector()
            items = asyncio.get_event_loop().run_until_complete(
                _collect(connector.discover(self._make_config()))
            )

        assert len(items) == 1
        assert items[0].filename == "report.pdf"
        assert items[0].content == fake_content
        assert items[0].source_id == "gdrive:file123"

    def test_discover_skips_non_allowed_mime(self):
        import asyncio
        from omniai.connectors.google_drive import GoogleDriveConnector

        fake_file = {
            "id": "vid1",
            "name": "movie.mp4",
            "mimeType": "video/mp4",
        }
        fake_list_response = {"files": [fake_file], "nextPageToken": None}

        with patch("omniai.connectors.google_drive._build_service") as mock_build:
            mock_service = MagicMock()
            mock_service.files.return_value.list.return_value.execute.return_value = fake_list_response
            mock_build.return_value = mock_service

            connector = GoogleDriveConnector()
            items = asyncio.get_event_loop().run_until_complete(
                _collect(connector.discover(self._make_config()))
            )

        assert items == []

    def test_graceful_import_error(self):
        """If google-api-python-client is absent, discover yields nothing."""
        import asyncio
        from omniai.connectors.google_drive import GoogleDriveConnector

        with patch("omniai.connectors.google_drive._build_service",
                   side_effect=ImportError("no module")):
            connector = GoogleDriveConnector()
            items = asyncio.get_event_loop().run_until_complete(
                _collect(connector.discover(self._make_config()))
            )

        assert items == []


# ══════════════════════════════════════════════════════════════════════════════
# 3. SharePoint connector (mocked httpx)
# ══════════════════════════════════════════════════════════════════════════════

class TestSharePointConnector:

    _CONFIG = {
        "tenant_id": "tenant-abc",
        "client_id": "client-abc",
        "client_secret": "secret-abc",
    }

    def test_discover_yields_files(self):
        import asyncio
        from omniai.connectors.sharepoint import SharePointConnector

        token_resp = MagicMock()
        token_resp.json.return_value = {"access_token": "fake-token"}
        token_resp.raise_for_status = MagicMock()

        list_resp = MagicMock()
        list_resp.json.return_value = {
            "value": [{
                "id": "item1",
                "name": "doc.pdf",
                "file": {"mimeType": "application/pdf"},
                "@microsoft.graph.downloadUrl": "https://fake.download/doc.pdf",
            }]
        }
        list_resp.raise_for_status = MagicMock()

        dl_resp = MagicMock()
        dl_resp.content = b"PDF content here"
        dl_resp.raise_for_status = MagicMock()

        async def fake_get(url, **kwargs):
            if "download" in url:
                return dl_resp
            return list_resp

        async def fake_post(url, **kwargs):
            return token_resp

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.get = fake_get
        mock_client.post = fake_post

        with patch("omniai.connectors.sharepoint.httpx.AsyncClient", return_value=mock_client):
            connector = SharePointConnector()
            items = asyncio.get_event_loop().run_until_complete(
                _collect(connector.discover(self._CONFIG))
            )

        assert len(items) == 1
        assert items[0].filename == "doc.pdf"
        assert items[0].content == b"PDF content here"

    def test_discover_skips_folders(self):
        import asyncio
        from omniai.connectors.sharepoint import SharePointConnector

        token_resp = MagicMock()
        token_resp.json.return_value = {"access_token": "fake-token"}
        token_resp.raise_for_status = MagicMock()

        list_resp = MagicMock()
        list_resp.json.return_value = {
            "value": [
                # A folder — should be skipped
                {"id": "folder1", "name": "MyFolder", "folder": {"childCount": 2}},
            ]
        }
        list_resp.raise_for_status = MagicMock()

        async def fake_get(url, **kwargs):
            return list_resp

        async def fake_post(url, **kwargs):
            return token_resp

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.get = fake_get
        mock_client.post = fake_post

        with patch("omniai.connectors.sharepoint.httpx.AsyncClient", return_value=mock_client):
            connector = SharePointConnector()
            items = asyncio.get_event_loop().run_until_complete(
                _collect(connector.discover(self._CONFIG))
            )

        assert items == []


# ══════════════════════════════════════════════════════════════════════════════
# 4. Notion connector (mocked httpx)
# ══════════════════════════════════════════════════════════════════════════════

class TestNotionConnector:

    _CONFIG = {"api_key": "secret_abc123", "page_ids": ["page-001"]}

    def test_discover_explicit_page(self):
        import asyncio
        from omniai.connectors.notion import NotionConnector

        page_resp = MagicMock()
        page_resp.json.return_value = {
            "id": "page-001",
            "object": "page",
            "properties": {
                "Name": {
                    "type": "title",
                    "title": [{"plain_text": "My Test Page"}]
                }
            }
        }
        page_resp.raise_for_status = MagicMock()
        page_resp.status_code = 200

        blocks_resp = MagicMock()
        blocks_resp.json.return_value = {
            "results": [
                {
                    "type": "paragraph",
                    "paragraph": {"rich_text": [{"plain_text": "Hello world"}]},
                    "has_children": False,
                }
            ],
            "has_more": False,
        }
        blocks_resp.raise_for_status = MagicMock()

        async def fake_get(url, **kwargs):
            if "blocks" in url:
                return blocks_resp
            return page_resp

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.get = fake_get

        with patch("omniai.connectors.notion.httpx.AsyncClient", return_value=mock_client):
            connector = NotionConnector()
            items = asyncio.get_event_loop().run_until_complete(
                _collect(connector.discover(self._CONFIG))
            )

        assert len(items) == 1
        assert items[0].filename == "My Test Page.md"
        assert b"Hello world" in items[0].content

    def test_discover_empty_page_skipped(self):
        """A page with no blocks should still produce a DiscoveredFile (title only)."""
        import asyncio
        from omniai.connectors.notion import NotionConnector

        page_resp = MagicMock()
        page_resp.json.return_value = {
            "id": "page-002",
            "object": "page",
            "properties": {
                "title": {
                    "type": "title",
                    "title": [{"plain_text": "Empty Page"}]
                }
            }
        }
        page_resp.raise_for_status = MagicMock()

        blocks_resp = MagicMock()
        blocks_resp.json.return_value = {"results": [], "has_more": False}
        blocks_resp.raise_for_status = MagicMock()

        async def fake_get(url, **kwargs):
            if "blocks" in url:
                return blocks_resp
            return page_resp

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.get = fake_get

        config = {"api_key": "secret_abc", "page_ids": ["page-002"]}
        with patch("omniai.connectors.notion.httpx.AsyncClient", return_value=mock_client):
            connector = NotionConnector()
            items = asyncio.get_event_loop().run_until_complete(
                _collect(connector.discover(config))
            )

        assert len(items) == 1
        assert b"Empty Page" in items[0].content


# ══════════════════════════════════════════════════════════════════════════════
# 5. Confluence connector (mocked httpx)
# ══════════════════════════════════════════════════════════════════════════════

class TestConfluenceConnector:

    _CONFIG = {
        "base_url": "https://myco.atlassian.net",
        "username": "user@example.com",
        "api_token": "ATATT3xfake",
        "space_keys": ["DEV"],
    }

    def test_discover_yields_pages(self):
        import asyncio
        from omniai.connectors.confluence import ConfluenceConnector

        content_resp = MagicMock()
        content_resp.json.return_value = {
            "results": [
                {
                    "id": "12345",
                    "title": "Architecture Overview",
                    "space": {"key": "DEV"},
                    "body": {
                        "storage": {
                            "value": "<p>This is the architecture overview.</p>"
                        }
                    },
                }
            ],
            "size": 1,
        }
        content_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.get = AsyncMock(return_value=content_resp)
        mock_client.base_url = "https://myco.atlassian.net"

        with patch("omniai.connectors.confluence.httpx.AsyncClient", return_value=mock_client):
            connector = ConfluenceConnector()
            items = asyncio.get_event_loop().run_until_complete(
                _collect(connector.discover(self._CONFIG))
            )

        assert len(items) == 1
        assert items[0].filename == "Architecture Overview.txt"
        assert b"architecture overview" in items[0].content.lower()

    def test_discover_skips_empty_body(self):
        import asyncio
        from omniai.connectors.confluence import ConfluenceConnector

        content_resp = MagicMock()
        content_resp.json.return_value = {
            "results": [
                {
                    "id": "99999",
                    "title": "Empty Page",
                    "space": {"key": "DEV"},
                    "body": {"storage": {"value": ""}},
                }
            ],
            "size": 1,
        }
        content_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.get = AsyncMock(return_value=content_resp)

        with patch("omniai.connectors.confluence.httpx.AsyncClient", return_value=mock_client):
            connector = ConfluenceConnector()
            items = asyncio.get_event_loop().run_until_complete(
                _collect(connector.discover(self._CONFIG))
            )

        assert items == []


# ══════════════════════════════════════════════════════════════════════════════
# 6. Slack connector (mocked httpx)
# ══════════════════════════════════════════════════════════════════════════════

class TestSlackConnector:

    _CONFIG = {
        "bot_token": "xoxb-fake-token",
        "channel_ids": ["C01ABCDEF"],
        "max_messages_per_channel": 10,
    }

    def test_discover_exports_messages(self):
        import asyncio
        from omniai.connectors.slack import SlackConnector

        info_data = {"ok": True, "channel": {"name": "general"}}
        history_data = {
            "ok": True,
            "messages": [
                {"ts": "1700000000.000001", "user": "U001", "text": "Hello team!"},
                {"ts": "1700000001.000001", "user": "U002", "text": "Hi there!"},
            ],
            "response_metadata": {"next_cursor": ""},
        }

        async def fake_get(url, **kwargs):
            resp = MagicMock()
            resp.raise_for_status = MagicMock()
            if "conversations.info" in url:
                resp.json.return_value = info_data
            else:
                resp.json.return_value = history_data
            return resp

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.get = fake_get

        with patch("omniai.connectors.slack.httpx.AsyncClient", return_value=mock_client):
            connector = SlackConnector()
            items = asyncio.get_event_loop().run_until_complete(
                _collect(connector.discover(self._CONFIG))
            )

        assert len(items) == 1
        assert items[0].filename == "slack_general.txt"
        assert b"Hello team!" in items[0].content
        assert b"Hi there!" in items[0].content

    def test_empty_channel_returns_nothing(self):
        import asyncio
        from omniai.connectors.slack import SlackConnector

        info_data = {"ok": True, "channel": {"name": "empty-chan"}}
        history_data = {
            "ok": True,
            "messages": [],
            "response_metadata": {"next_cursor": ""},
        }

        async def fake_get(url, **kwargs):
            resp = MagicMock()
            resp.raise_for_status = MagicMock()
            if "conversations.info" in url:
                resp.json.return_value = info_data
            else:
                resp.json.return_value = history_data
            return resp

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.get = fake_get

        with patch("omniai.connectors.slack.httpx.AsyncClient", return_value=mock_client):
            connector = SlackConnector()
            items = asyncio.get_event_loop().run_until_complete(
                _collect(connector.discover(self._CONFIG))
            )

        assert items == []


# ══════════════════════════════════════════════════════════════════════════════
# 7. Database connector (real SQLite in-memory)
# ══════════════════════════════════════════════════════════════════════════════

class TestDatabaseConnector:

    def _seed_db(self, connection_string: str, table: str, rows: list[dict]) -> None:
        import sqlalchemy as sa
        engine = sa.create_engine(connection_string)
        with engine.begin() as conn:
            cols = ", ".join(
                f'"{k}" TEXT' for k in rows[0].keys()
            )
            conn.execute(sa.text(f'CREATE TABLE IF NOT EXISTS "{table}" (id INTEGER PRIMARY KEY, {cols})'))
            for i, row in enumerate(rows, start=1):
                placeholders = ", ".join(f":{k}" for k in row)
                conn.execute(sa.text(
                    f'INSERT INTO "{table}" (id, {", ".join(row)}) VALUES (:id, {placeholders})'
                ), {"id": i, **row})
        engine.dispose()

    def test_discover_yields_rows(self):
        import asyncio
        from omniai.connectors.database import DatabaseConnector

        # We need a persistent SQLite file for this test
        import tempfile
        import os
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        try:
            file_db_url = f"sqlite:///{db_path}"
            rows = [
                {"title": "Article One", "body": "Content of article one"},
                {"title": "Article Two", "body": "Content of article two"},
            ]
            self._seed_db(file_db_url, "articles", rows)

            connector = DatabaseConnector()
            items = asyncio.get_event_loop().run_until_complete(
                _collect(connector.discover({
                    "connection_string": file_db_url,
                    "table": "articles",
                    "columns": ["title", "body"],
                    "id_column": "id",
                }))
            )

            assert len(items) == 2
            texts = [i.content.decode() for i in items]
            assert any("Article One" in t for t in texts)
            assert any("Article Two" in t for t in texts)
            assert all(i.mime_type == "text/plain" for i in items)
        finally:
            os.unlink(db_path)

    def test_discover_with_where_clause(self):
        import asyncio
        from omniai.connectors.database import DatabaseConnector
        import tempfile
        import os

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        try:
            file_db_url = f"sqlite:///{db_path}"
            rows = [
                {"title": "Active Doc", "status": "active"},
                {"title": "Draft Doc", "status": "draft"},
            ]
            import sqlalchemy as sa
            engine = sa.create_engine(file_db_url)
            with engine.begin() as conn:
                conn.execute(sa.text(
                    'CREATE TABLE docs (id INTEGER PRIMARY KEY, title TEXT, status TEXT)'
                ))
                for i, r in enumerate(rows, 1):
                    conn.execute(sa.text(
                        "INSERT INTO docs (id, title, status) VALUES (:id, :title, :status)"
                    ), {"id": i, **r})
            engine.dispose()

            connector = DatabaseConnector()
            items = asyncio.get_event_loop().run_until_complete(
                _collect(connector.discover({
                    "connection_string": file_db_url,
                    "table": "docs",
                    "columns": ["title", "status"],
                    "where_clause": "status = 'active'",
                }))
            )

            assert len(items) == 1
            assert b"Active Doc" in items[0].content
        finally:
            os.unlink(db_path)

    def test_discover_with_template(self):
        import asyncio
        from omniai.connectors.database import DatabaseConnector
        import tempfile
        import os

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        try:
            file_db_url = f"sqlite:///{db_path}"
            import sqlalchemy as sa
            engine = sa.create_engine(file_db_url)
            with engine.begin() as conn:
                conn.execute(sa.text(
                    'CREATE TABLE posts (id INTEGER PRIMARY KEY, title TEXT, content TEXT)'
                ))
                conn.execute(sa.text(
                    "INSERT INTO posts VALUES (1, 'My Post', 'Post body here')"
                ))
            engine.dispose()

            connector = DatabaseConnector()
            items = asyncio.get_event_loop().run_until_complete(
                _collect(connector.discover({
                    "connection_string": file_db_url,
                    "table": "posts",
                    "columns": ["title", "content"],
                    "document_template": "TITLE: {title}\nBODY: {content}",
                }))
            )

            assert len(items) == 1
            text = items[0].content.decode()
            assert "TITLE: My Post" in text
            assert "BODY: Post body here" in text
        finally:
            os.unlink(db_path)

    def test_discover_invalid_engine_yields_nothing(self):
        import asyncio
        from omniai.connectors.database import DatabaseConnector

        connector = DatabaseConnector()
        items = asyncio.get_event_loop().run_until_complete(
            _collect(connector.discover({
                "connection_string": "postgresql+psycopg2://fake:fake@localhost:9999/fake",
                "table": "docs",
            }))
        )
        # Should not raise; yields nothing on connection error
        assert items == []


# ══════════════════════════════════════════════════════════════════════════════
# 8. connector_service.preview_connector dry-run
# ══════════════════════════════════════════════════════════════════════════════

class TestPreviewConnector:

    def test_preview_local_folder(self, tmp_path):
        import asyncio
        from omniai.application.connector_service import preview_connector

        # Create some text files
        (tmp_path / "a.txt").write_text("Hello from file A")
        (tmp_path / "b.md").write_text("# Hello from file B")

        results = asyncio.get_event_loop().run_until_complete(
            preview_connector("local_folder", {"path": str(tmp_path)}, max_items=5)
        )

        assert len(results) == 2
        for r in results:
            assert "source_id" in r
            assert "filename" in r
            assert "mime_type" in r
            assert "size_bytes" in r
            assert "content_preview" in r

    def test_preview_respects_max_items(self, tmp_path):
        import asyncio
        from omniai.application.connector_service import preview_connector

        for i in range(10):
            (tmp_path / f"file{i}.txt").write_text(f"content {i}")

        results = asyncio.get_event_loop().run_until_complete(
            preview_connector("local_folder", {"path": str(tmp_path)}, max_items=3)
        )

        assert len(results) == 3

    def test_preview_invalid_kind_raises(self):
        import asyncio
        from omniai.application.connector_service import preview_connector

        with pytest.raises(ValueError, match="Unknown connector kind"):
            asyncio.get_event_loop().run_until_complete(
                preview_connector("nonexistent_kind", {}, max_items=5)
            )

    def test_preview_invalid_config_raises(self):
        import asyncio
        from omniai.application.connector_service import preview_connector

        with pytest.raises(ValueError):
            asyncio.get_event_loop().run_until_complete(
                preview_connector("google_drive", {}, max_items=5)
            )


# ══════════════════════════════════════════════════════════════════════════════
# 9. HTTP routes
# ══════════════════════════════════════════════════════════════════════════════

class TestConnectorRoutes:

    def test_list_kinds_returns_all_supported(self, client, auth_headers):
        r = client.get("/v1/connectors/kinds", headers=auth_headers)
        assert r.status_code == 200
        kinds = r.json()["data"]
        assert isinstance(kinds, list)
        for expected in ("local_folder", "s3", "web_crawler", "google_drive",
                         "sharepoint", "notion", "confluence", "slack", "database"):
            assert expected in kinds

    def test_preview_invalid_kind_returns_400(self, client, auth_headers):
        r = client.post(
            "/v1/connectors/preview",
            json={"kind": "totally_unknown", "config": {}, "max_items": 3},
            headers=auth_headers,
        )
        assert r.status_code == 400
        assert "Unknown" in r.json()["detail"] or "unknown" in r.json()["detail"]

    def test_preview_invalid_config_returns_400(self, client, auth_headers):
        r = client.post(
            "/v1/connectors/preview",
            json={"kind": "notion", "config": {}, "max_items": 3},
            headers=auth_headers,
        )
        assert r.status_code == 400

    def test_preview_local_folder_returns_200(self, client, auth_headers, tmp_path):
        (tmp_path / "sample.txt").write_text("Sample document content")

        r = client.post(
            "/v1/connectors/preview",
            json={
                "kind": "local_folder",
                "config": {"path": str(tmp_path)},
                "max_items": 5,
            },
            headers=auth_headers,
        )
        assert r.status_code == 200
        data = r.json()["data"]
        assert "items" in data
        assert "count" in data
        assert data["count"] >= 1

    def test_create_connector_google_drive_kind_accepted(self, client, auth_headers):
        """Verify the new kinds are accepted by the create endpoint (not rejected as 422)."""
        # Create a collection first via the API
        coll_r = client.post(
            "/v1/collections",
            json={"name": "M17 Test Collection", "description": "connector kind test"},
            headers=auth_headers,
        )
        assert coll_r.status_code == 201, coll_r.text
        coll_id = coll_r.json()["data"]["id"]

        r = client.post(
            "/v1/connectors",
            json={
                "collection_id": coll_id,
                "name": "Test GDrive Connector",
                "kind": "google_drive",
                "config": {"access_token": "ya29.fake"},
                "sync_interval_seconds": 300,
            },
            headers=auth_headers,
        )
        # Should be 201 (created) — access_token config is valid per validate_config
        # Must not be 422 Unprocessable Entity (kind regex rejection)
        assert r.status_code != 422, f"Got 422 — kind regex is too restrictive: {r.text}"
        assert r.status_code in (201, 400)


# ══════════════════════════════════════════════════════════════════════════════
# 10. SUPPORTED_KINDS list completeness
# ══════════════════════════════════════════════════════════════════════════════

class TestSupportedKinds:

    def test_all_m17_kinds_in_registry(self):
        from omniai.application.connector_service import SUPPORTED_KINDS
        for kind in ("google_drive", "sharepoint", "notion", "confluence", "slack", "database"):
            assert kind in SUPPORTED_KINDS, f"{kind!r} missing from SUPPORTED_KINDS"

    def test_legacy_kinds_still_present(self):
        from omniai.application.connector_service import SUPPORTED_KINDS
        for kind in ("local_folder", "s3", "web_crawler"):
            assert kind in SUPPORTED_KINDS, f"Legacy kind {kind!r} missing"

    def test_no_duplicates(self):
        from omniai.application.connector_service import SUPPORTED_KINDS
        assert len(SUPPORTED_KINDS) == len(set(SUPPORTED_KINDS))
