import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    """Application configuration loaded from environment variables."""

    GROQ_API_KEY_1: str = os.getenv("GROQ_API_KEY_1", "")
    GROQ_API_KEY_2: str = os.getenv("GROQ_API_KEY_2", "")
    GROQ_MODEL: str = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
    PORT: int = int(os.getenv("PORT", "8000"))

    # Groq API endpoint
    GROQ_API_URL: str = "https://api.groq.com/openai/v1/chat/completions"

    # Timeout for Groq API calls (leave 10s buffer from 30s judge timeout)
    GROQ_TIMEOUT_SECONDS: float = 20.0

    # LLM generation parameters
    LLM_TEMPERATURE: float = 0.1
    LLM_MAX_TOKENS: int = 1024

    @property
    def groq_keys(self) -> list[str]:
        """Return list of available Groq API keys dynamically from environment variables."""
        keys_dict = {}
        # Scan os.environ for any variable starting with GROQ_API_KEY_
        for env_name, env_val in os.environ.items():
            if env_name.startswith("GROQ_API_KEY_") and env_val.strip():
                keys_dict[env_name] = env_val.strip()
        
        # Fallback to hardcoded settings if os.environ scanning did not find them
        if not keys_dict:
            if self.GROQ_API_KEY_1:
                keys_dict["GROQ_API_KEY_1"] = self.GROQ_API_KEY_1
            if self.GROQ_API_KEY_2:
                keys_dict["GROQ_API_KEY_2"] = self.GROQ_API_KEY_2

        # Return the key values sorted by variable name to preserve order (1, 2, 3...)
        return [keys_dict[k] for k in sorted(keys_dict.keys())]

    @property
    def has_groq_keys(self) -> bool:
        return len(self.groq_keys) > 0


settings = Settings()
