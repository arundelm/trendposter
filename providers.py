"""Concrete LLM provider implementations."""

from __future__ import annotations

import httpx

from trendposter.config import LLMConfig
from trendposter.llm.base import BaseLLMProvider


class AnthropicProvider(BaseLLMProvider):
    """Anthropic Claude provider."""

    async def complete(self, prompt: str) -> str:
        import anthropic

        client = anthropic.AsyncAnthropic(api_key=self.config.api_key)
        message = await client.messages.create(
            model=self.config.model or "claude-sonnet-4-5-20250929",
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        return message.content[0].text


class OpenAIProvider(BaseLLMProvider):
    """OpenAI provider."""

    async def complete(self, prompt: str) -> str:
        import openai

        client = openai.AsyncOpenAI(api_key=self.config.api_key)
        response = await client.chat.completions.create(
            model=self.config.model or "gpt-4o",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1024,
        )
        return response.choices[0].message.content


class GeminiProvider(BaseLLMProvider):
    """Google Gemini provider."""

    async def complete(self, prompt: str) -> str:
        import google.generativeai as genai

        genai.configure(api_key=self.config.api_key)
        model = genai.GenerativeModel(self.config.model or "gemini-2.0-flash")
        response = await model.generate_content_async(prompt)
        return response.text


class OllamaProvider(BaseLLMProvider):
    """Local Ollama provider."""

    async def complete(self, prompt: str) -> str:
        base_url = self.config.base_url or "http://localhost:11434"
        model = self.config.model or "llama3.2"

        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(
                f"{base_url}/api/generate",
                json={"model": model, "prompt": prompt, "stream": False},
            )
            resp.raise_for_status()
            return resp.json()["response"]
