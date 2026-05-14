"""Pytest fixtures for wiki project tests."""
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from wiki_core.store import WikiStore


def create_mock_response(content: str) -> MagicMock:
    """Create a mock OpenAI response object with the given content."""
    response = MagicMock()
    response.choices = [MagicMock()]
    response.choices[0].message = MagicMock()
    response.choices[0].message.content = content
    return response


@pytest.fixture
def temp_wiki_root(tmp_path: Path) -> Path:
    """Create a temporary directory for wiki tests."""
    return tmp_path


@pytest.fixture
def wiki_store(temp_wiki_root: Path) -> WikiStore:
    """Create a WikiStore instance with a temporary root."""
    store = WikiStore(temp_wiki_root)
    store.init()
    return store


@pytest.fixture
def mock_openai_client():
    """Create a mock OpenAI client."""
    client = MagicMock()
    # Create a mock response object
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message = MagicMock()
    mock_response.choices[0].message.content = ""
    client.chat.completions.create.return_value = mock_response
    return client


@pytest.fixture(autouse=True)
def patch_get_client(mock_openai_client, monkeypatch):
    """Automatically patch get_client in all modules that use it."""
    monkeypatch.setattr("wiki_core.llm.get_client", lambda: mock_openai_client)
    monkeypatch.setattr("wiki_core.ingest.get_client", lambda: mock_openai_client)
    monkeypatch.setattr("wiki_core.query.get_client", lambda: mock_openai_client)
    monkeypatch.setattr("wiki_core.lint.get_client", lambda: mock_openai_client)


@pytest.fixture
def mock_llm_client(mock_openai_client):
    """Return the mock client (get_client is already patched by autouse fixture)."""
    yield mock_openai_client


@pytest.fixture
def sample_page_content():
    """Sample wiki page content for testing."""
    return """---
tags: [test, sample]
updated: 2024-01-15
sources: [test-source.md]
---

# Sample Page

This is a summary of the sample page.

## Details

More detailed information goes here.

## Related
- [[Other Page]]
- [[Third Page]]
"""


@pytest.fixture
def populated_wiki_store(wiki_store: WikiStore, sample_page_content: str):
    """Create a WikiStore with some sample pages."""
    # Create sample pages
    wiki_store.write_page("pages/sample-page.md", sample_page_content)
    wiki_store.write_page("pages/other-page.md", sample_page_content.replace("Sample Page", "Other Page"))
    wiki_store.write_page("pages/third-page.md", sample_page_content.replace("Sample Page", "Third Page"))
    wiki_store.rebuild_index()
    return wiki_store
