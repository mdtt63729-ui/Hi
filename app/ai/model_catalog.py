"""Gitofy AI model catalog.

The catalog deliberately keeps provider identity separate from model naming because
some NIM/OpenRouter model identifiers overlap (for example meta/muse-glimmer-30b).
"""

HEAD_MODELS = [
    "gemini-3.7-flash",
    "gemini-3.5-flash-lite",
    "gemini-3.5-flash",
    "gemma-4-26b-a4b-it",
]

OPENROUTER_FIX_MODELS = [
    "qwen/qwen3.8-flash",
    "meta/muse-glimmer-30b",
    "nvidia/nemotron-3.5-lightning",
    "openai/gpt-4o-mini",
    "cohere/north-mini-code:free",
    "minimax/minimax-m3:free",
    "poolside/laguna-s-2.1",
    "poolside/laguna-xs-2.1",
    "inclusionai/ling-3.0-flash-fin:free",
]

NVIDIA_MODELS = [
    "deepseek-ai/deepseek-v4-pro-0813",
    "deepseek-ai/deepseek-v4-flash-0731",
    "moonshotai/kimi-k3",
    "nvidia/nemotron-3.5-lightning-30b-a3b",
    "meta/muse-glimmer-30b",
    "nvidia/riva-translate-4b-instruct-v2",
    "nvidia/ising-calibration-1.5-31b",
    "nvidia/nemotron-3-embed-1b",
    "poolside/laguna-xs-2.1",
    "minimaxai/minimax-m3",
    "google/diffusiongemma-26b-a4b-it",
    "nvidia/nemotron-3-ultra-550b-a55b",
    "nvidia/nemotron-3.5-content-safety",
    "nvidia/cosmos3-nano",
    "nvidia/cosmos3-nano-reasoner",
    "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning",
    "nvidia/synthetic-video-detector",
    "nvidia/active-speaker-detection",
    "nvidia/ising-calibration-1-35b-a3b",
    "google/gemma-4-31b-it",
    "nvidia/nemotron-voicechat",
    "nvidia/nemotron-3-super-120b-a12b",
    "nvidia/cosmos-transfer2.5-2b",
    "nvidia/riva-translate-4b-instruct-v1_1",
    "nvidia/streampetr",
    "nvidia/llama-3.1-nemotron-safety-guard-8b-v3",
    "openai/gpt-oss-20b",
    "openai/gpt-oss-120b",
    "meta/llama-guard-4-12b",
    "nvidia/cosmos-transfer1-7b",
    "nvidia/background-noise-removal",
    "mistralai/mistral-nemotron",
    "nvidia/magpie-tts-zeroshot",
    "nvidia/sparsedrive",
    "nvidia/bevformer",
    "nvidia/studio-voice",
    "meta/llama-3.2-11b-vision-instruct",
    "meta/llama-3.2-90b-vision-instruct",
    "google/paligemma",
    "parakeet-tdt-0.6b",
    "wan2.2-animate-2-14b",
]

# User-selectable fixer catalog: Gemini + OpenRouter + NVIDIA NIM.
FIX_MODELS = list(dict.fromkeys(
    HEAD_MODELS + OPENROUTER_FIX_MODELS + NVIDIA_MODELS
))

# Explicit provider-qualified options are used for IDs that exist on more than one service.
MODEL_OPTIONS = [("gemini", m) for m in HEAD_MODELS] + [("openrouter", m) for m in OPENROUTER_FIX_MODELS] + [("nvidia", m) for m in NVIDIA_MODELS]

def model_key(provider: str, model: str) -> str:
    return f"{provider}::{model}"

def split_model_key(value: str):
    if "::" in (value or ""):
        return tuple(value.split("::", 1))
    return provider_for(value), value

NVIDIA_VISION_MODELS = {
    "moonshotai/kimi-k3",
    "meta/muse-glimmer-30b",
    "meta/llama-3.2-11b-vision-instruct",
    "meta/llama-3.2-90b-vision-instruct",
    "google/paligemma",
}

NVIDIA_VIDEO_MODELS = {
    "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning",
    "nvidia/cosmos3-nano",
    "nvidia/cosmos3-nano-reasoner",
    "wan2.2-animate-2-14b",
}

NVIDIA_AUDIO_MODELS = {
    "nvidia/nemotron-voicechat",
    "nvidia/riva-translate-4b-instruct-v2",
    "nvidia/riva-translate-4b-instruct-v1_1",
    "parakeet-tdt-0.6b",
}

# IDs that must be sent to NVIDIA NIM even though they contain a slash.
_NVIDIA_IDS = set(NVIDIA_MODELS)

def provider_for(model: str) -> str:
    model = (model or "").strip()
    if model in _NVIDIA_IDS:
        return "nvidia"
    if model in HEAD_MODELS:
        return "gemini"
    if "/" in model:
        return "openrouter"
    return "gemini"

def model_capabilities(model: str) -> set[str]:
    p = provider_for(model)
    if p == "gemini":
        return {"text", "image", "audio", "video", "file"}
    if p == "nvidia":
        caps = {"text"}
        if model in NVIDIA_VISION_MODELS: caps.add("image")
        if model in NVIDIA_VIDEO_MODELS: caps.add("video")
        if model in NVIDIA_AUDIO_MODELS: caps.add("audio")
        return caps
    # OpenRouter capabilities vary by provider/model. Image is enabled for the
    # known vision-capable choices; text remains universal.
    caps = {"text"}
    if model in {"meta/muse-glimmer-30b", "qwen/qwen3.8-flash"}: caps.add("image")
    return caps

def normalize_model_name(value: str) -> str:
    return (value or "").strip()
