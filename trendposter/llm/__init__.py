"""LLM provider package — factory and re-exports."""

from trendposter.config import LLMConfig
from trendposter.llm.base import BaseLLMProvider, TweetAnalysis


def create_provider(config: LLMConfig) -> BaseLLMProvider:
    """Create an LLM provider instance based on config."""
    from trendposter.llm.providers import (
        AnthropicProvider,
        GeminiProvider,
        OllamaProvider,
        OpenAIProvider,
    )

    providers = {
        "anthropic": AnthropicProvider,
        "openai": OpenAIProvider,
        "gemini": GeminiProvider,
        "ollama": OllamaProvider,
    }

    cls = providers.get(config.provider)
    if not cls:
        raise ValueError(f"Unknown LLM provider: {config.provider}")
    return cls(config)


__all__ = ["BaseLLMProvider", "TweetAnalysis", "create_provider"]
