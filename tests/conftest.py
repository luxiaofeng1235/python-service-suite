"""
============================================
Test Configuration - external storage isolation
============================================
Keep tests independent of real OSS credentials configured in the local environment.
"""

import pytest

from app.core.config import settings


@pytest.fixture(autouse=True)
def disable_external_oss(monkeypatch):
    """Require each OSS test to opt into its mocked object storage explicitly."""
    monkeypatch.setattr(settings, "OSS_ENABLED", False)
