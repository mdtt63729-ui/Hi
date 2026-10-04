import pytest
from app.ai.manager import AIProviderManager
from app.config import settings

def test_catalog_contains_manual_models():
    m=AIProviderManager(settings)
    assert 'minimax/minimax-m3:free' in m.fix_models
