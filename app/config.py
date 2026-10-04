from pydantic_settings import BaseSettings, SettingsConfigDict
from pathlib import Path

class Settings(BaseSettings):
    bot_token: str = ""
    database_url: str = "sqlite+aiosqlite:///./gitofy.db"
    redis_url: str | None = None
    encryption_key: str = ""
    storage_backend: str = "local"
    storage_path: str = "./data"
    s3_endpoint: str | None = None
    s3_bucket: str | None = None
    s3_access_key: str | None = None
    s3_secret_key: str | None = None
    s3_region: str = "auto"
    r2_endpoint: str | None = None
    r2_bucket: str | None = None
    r2_access_key: str | None = None
    r2_secret_key: str | None = None
    log_level: str = "INFO"
    health_host: str = "0.0.0.0"
    health_port: int = 8080
    webhook_base_url: str | None = None
    webhook_secret: str | None = None
    admin_ids: str = ""
    session_ttl_seconds: int = 900
    lock_ttl_seconds: int = 300
    cleanup_minutes: int = 30
    poll_initial_seconds: int = 10
    poll_max_seconds: int = 60
    artifact_signing_secret: str = ""
    openrouter_api_key: str = ""
    nvidia_api_key: str = ""
    nvidia_base_url: str = "https://integrate.api.nvidia.com/v1"
    openrouter_model: str = ""
    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.7-flash"
    ai_head_model: str = "gemini-3.7-flash"
    ai_fix_models: str = ",".join([
        "gemini-3.7-flash", "gemini-3.5-flash-lite", "gemini-3.5-flash", "gemma-4-26b-a4b-it",
        "qwen/qwen3.8-flash", "meta/muse-glimmer-30b", "nvidia/nemotron-3.5-lightning",
        "openai/gpt-4o-mini", "cohere/north-mini-code:free", "minimax/minimax-m3:free",
        "poolside/laguna-s-2.1", "poolside/laguna-xs-2.1", "inclusionai/ling-3.0-flash-fin:free",
        "deepseek-ai/deepseek-v4-pro-0813", "deepseek-ai/deepseek-v4-flash-0731", "moonshotai/kimi-k3",
        "nvidia/nemotron-3.5-lightning-30b-a3b", "minimaxai/minimax-m3",
        "google/diffusiongemma-26b-a4b-it", "google/gemma-4-31b-it",
        "meta/llama-3.2-11b-vision-instruct", "meta/llama-3.2-90b-vision-instruct", "google/paligemma",
        "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning", "nvidia/cosmos3-nano-reasoner",
    ])
    ollama_api_key: str = ""
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.2"
    ai_provider: str = "auto"
    ai_autofix_enabled: bool = True
    max_zip_bytes: int = 524288000
    max_extracted_bytes: int = 2147483648
    max_files: int = 20000
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @property
    def ai_fix_models_list(self) -> list[str]:
        return [x.strip() for x in self.ai_fix_models.split(",") if x.strip()]

    @property
    def admin_id_set(self) -> set[int]:
        return {int(x.strip()) for x in self.admin_ids.split(",") if x.strip().isdigit()}

def validate_required_ai_apis():
    """Return missing required AI providers without preventing bot startup.

    Provider keys may be configured securely from Telegram Settings > AI Providers,
    so startup must remain available when the initial .env values are empty.
    Actual AI/Auto-Fix operations still require all three providers.
    """
    if not settings.ai_autofix_enabled:
        return []
    missing=[]
    if not settings.gemini_api_key: missing.append("GEMINI_API_KEY")
    if not settings.openrouter_api_key: missing.append("OPENROUTER_API_KEY")
    if not settings.nvidia_api_key: missing.append("NVIDIA_API_KEY")
    return missing

settings = Settings()
Path(settings.storage_path).mkdir(parents=True, exist_ok=True)
