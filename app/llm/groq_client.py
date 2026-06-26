"""Groq API client with dual-key failover.

On 429 from key 1, automatically retries with key 2.
On both failing, returns None so the fallback generator is used.
"""

from __future__ import annotations

import json
import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


class GroqClient:
    """Async Groq chat completion client with dual API key failover."""

    def __init__(self) -> None:
        self._keys = settings.groq_keys
        self._model = settings.GROQ_MODEL
        self._url = settings.GROQ_API_URL
        self._timeout = settings.GROQ_TIMEOUT_SECONDS
        self._temperature = settings.LLM_TEMPERATURE
        self._max_tokens = settings.LLM_MAX_TOKENS

    async def chat_completion(
        self,
        system_prompt: str,
        user_prompt: str,
    ) -> dict | None:
        """Call Groq and return parsed JSON, or None on failure.

        Tries each API key in order. On 429 or error, moves to next key.
        Returns None if all keys fail (triggers fallback).
        """
        if not self._keys:
            logger.warning("No Groq API keys configured, using fallback")
            return None

        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": self._temperature,
            "max_tokens": self._max_tokens,
            "response_format": {"type": "json_object"},
        }

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            for i, key in enumerate(self._keys):
                try:
                    logger.info(f"Attempting Groq API call with key {i + 1}")
                    response = await client.post(
                        self._url,
                        headers={
                            "Authorization": f"Bearer {key}",
                            "Content-Type": "application/json",
                        },
                        json=payload,
                    )

                    if response.status_code == 200:
                        data = response.json()
                        content = data["choices"][0]["message"]["content"]
                        try:
                            return json.loads(content)
                        except json.JSONDecodeError:
                            logger.error(f"Key {i + 1}: Invalid JSON in response")
                            continue

                    elif response.status_code == 429:
                        logger.warning(
                            f"Key {i + 1}: Rate limited (429), trying next key"
                        )
                        continue

                    else:
                        logger.error(
                            f"Key {i + 1}: Groq API error {response.status_code}: "
                            f"{response.text[:200]}"
                        )
                        continue

                except httpx.TimeoutException:
                    logger.error(f"Key {i + 1}: Groq API timeout")
                    continue
                except Exception as e:
                    logger.error(f"Key {i + 1}: Unexpected error: {e}")
                    continue

        logger.warning("All Groq API keys failed, falling back to rule-based")
        return None
