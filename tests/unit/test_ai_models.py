from app.ai.model_catalog import HEAD_MODELS, FIX_MODELS, provider_for
from app.ai.manager import AIProviderManager
from app.services.ai_progress import AIFixProgress

def test_requested_head_models_are_present():
    assert HEAD_MODELS == ['gemini-3.7-flash','gemini-3.5-flash-lite','gemini-3.5-flash','gemma-4-26b-a4b-it']

def test_requested_openrouter_models_are_present():
    expected=['qwen/qwen3.8-flash','meta/muse-glimmer-30b','nvidia/nemotron-3.5-lightning','openai/gpt-4o-mini','cohere/north-mini-code:free','minimax/minimax-m3:free','poolside/laguna-s-2.1','poolside/laguna-xs-2.1','inclusionai/ling-3.0-flash-fin:free']
    assert all(x in FIX_MODELS for x in expected)

def test_provider_routing():
    assert provider_for('minimax/minimax-m3:free') == 'openrouter'
    assert provider_for('moonshotai/kimi-k3') == 'nvidia'
    assert provider_for('gemini-3.7-flash') == 'gemini'

def test_ai_progress_never_renders_complete_before_finish():
    assert AIFixProgress.bar(99).count('█') < len(AIFixProgress.bar(100))
