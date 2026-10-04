# Gitofy AI model configuration

Gitofy uses **Auto mode** by default for build repair.

## Head AI

The head/router model is selected from:

- `gemini-3.7-flash` (default)
- `gemini-3.5-flash-lite`
- `gemini-3.5-flash`
- `gemma-4-26b-a4b-it`

The Head AI analyzes the failure and chooses the best specialist fixer from the pool.

## Specialist/fixer pool

- `gemini-3.5-flash-lite`
- `gemini-3.5-flash`
- `gemma-4-26b-a4b-it`
- `qwen/qwen3.8-flash`
- `meta/muse-glimmer-30b`
- `nvidia/nemotron-3.5-lightning`
- `openai/gpt-4o-mini`
- `cohere/north-mini-code:free`
- `minimax/minimax-m3:free`
- `poolside/laguna-s-2.1`
- `poolside/laguna-xs-2.1`
- `inclusionai/ling-3.0-flash-fin:free`

Google models use `GEMINI_API_KEY`. OpenRouter models use `OPENROUTER_API_KEY`.

The exact model IDs remain environment-configurable because provider model identifiers can change. The UI always shows the exact configured model ID used for the current repair.

## Honest progress

The AI progress percentage represents **completed repair work**, not an invented token-generation percentage. It is based on concrete stages such as log collection, repository inspection, model routing, fix generation, file application, Git push, and workflow verification. It is capped at 99% until the repair/rebuild actually succeeds; only the final successful completion renders 100%.
