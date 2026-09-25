import os

import pytest


@pytest.fixture(autouse=True)
def clear_settings_cache():
    """Clear LRU cache before each test to ensure isolation."""
    from commons.settings import read_settings

    read_settings.cache_clear()
    yield
    read_settings.cache_clear()


@pytest.fixture
def clean_app_env(monkeypatch):
    """Remove all APP__ prefixed environment variables for test isolation."""
    for key in list(os.environ.keys()):
        if key.startswith("APP__"):
            monkeypatch.delenv(key, raising=False)
