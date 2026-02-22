"""
Shared OpenAI GPT helper for the generation pipeline.

Used by:
  - pattern_interpreter.py  (Step 1)
  - question_generator.py   (Step 4)
  - validator.py            (Step 7)

Model: gpt-4o-mini  (override with GPT_MODEL env var, e.g. "gpt-4o")
"""

import os
from openai import AsyncOpenAI

# ── Model config ───────────────────────────────────────────────────────────────
GPT_MODEL = os.getenv("GPT_MODEL", "gpt-4o-mini")

# Lazy singleton
_client: AsyncOpenAI | None = None


def _get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError(
                "OPENAI_API_KEY is not set. Add it to your .env file."
            )
        _client = AsyncOpenAI(api_key=api_key)
    return _client


async def call_gpt(
    prompt: str,
    system: str = "You are a helpful academic assistant. Output only what is asked.",
    temperature: float = 0.4,
    max_tokens: int = 2048,
) -> str:
    """
    Call OpenAI Chat Completions and return the assistant message text.

    Args:
        prompt:      User-turn message (the actual instruction/question)
        system:      System prompt
        temperature: Sampling temperature (lower = more deterministic)
        max_tokens:  Max response tokens

    Returns:
        Raw string content of the model response
    """
    client = _get_client()
    response = await client.chat.completions.create(
        model=GPT_MODEL,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return response.choices[0].message.content or ""
