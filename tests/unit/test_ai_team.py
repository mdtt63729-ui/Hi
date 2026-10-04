from app.ai.model_catalog import *
from app.ai.manager import AIProviderManager
from app.services.ai_progress import AIFixProgress
from app.config import settings

def test_nvidia_catalog_is_present():
    assert 'deepseek-ai/deepseek-v4-pro-0813' in NVIDIA_MODELS
    assert 'moonshotai/kimi-k3' in NVIDIA_MODELS
    assert 'nvidia/nemotron-3.5-lightning-30b-a3b' in NVIDIA_MODELS

def test_provider_identity_handles_overlapping_ids():
    assert provider_for('meta/muse-glimmer-30b') == 'nvidia'
    assert provider_for('qwen/qwen3.8-flash') == 'openrouter'
    assert provider_for('gemini-3.7-flash') == 'gemini'

def test_three_api_status_fields_exist():
    assert hasattr(settings,'nvidia_api_key')
    assert hasattr(settings,'openrouter_api_key')
    assert hasattr(settings,'gemini_api_key')

def test_progress_only_reaches_100_on_finish():
    assert AIFixProgress.bar(99).count('█') < AIFixProgress.bar(100).count('█')
