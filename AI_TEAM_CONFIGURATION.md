# Gitofy AI Team

Gitofy uses three required AI API families when `AI_AUTOFIX_ENABLED=true`:

1. **Gemini** — Head AI. It analyzes failed workflows and routes the problem.
2. **OpenRouter** — specialist pool.
3. **NVIDIA NIM** — specialist pool and selected vision/video/audio-capable models.

Required environment variables:

```text
GEMINI_API_KEY=...
OPENROUTER_API_KEY=...
NVIDIA_API_KEY=...
NVIDIA_BASE_URL=https://integrate.api.nvidia.com/v1
AI_HEAD_MODEL=gemini-3.7-flash
AI_AUTOFIX_ENABLED=true
```

Auto mode is the default. The Head AI chooses a configured specialist from OpenRouter or NVIDIA, with Gemini models also available in the manual picker.

The Telegram AI attachment flow accepts photos, videos and documents. Gemini is the first multimodal reader; its findings are passed to the selected specialist as a team hand-off. Text files are extracted locally before analysis. Large/unsupported binary files are represented by safe metadata rather than blindly uploaded.

NVIDIA NIM calls use the OpenAI-compatible `/v1/chat/completions` endpoint. Image-capable models receive `image_url` content using data URLs; the provider/model capability catalog prevents unsuitable specialist selection.
