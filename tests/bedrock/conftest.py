# tests/bedrock/conftest.py
import pytest
from pathlib import Path
from src.bedrock.db.migrate import apply_migrations


@pytest.fixture
def tmp_project(tmp_path: Path) -> Path:
    apply_migrations(tmp_path)
    return tmp_path
