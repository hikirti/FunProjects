"""
LLM Client with OpenAI/Anthropic provider switch.
"""

import os
import json
from abc import ABC, abstractmethod
from typing import Optional
from enum import Enum

from .logger import get_module_logger
from .exceptions import LLMClientError

logger = get_module_logger("llm_client")


class LLMProvider(Enum):
    """Supported LLM providers."""
    OPENAI = "openai"
    ANTHROPIC = "anthropic"


class BaseLLMClient(ABC):
    """Abstract base class for LLM clients."""

    @abstractmethod
    def complete(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        """
        Send a prompt to the LLM and return the response.

        Args:
            prompt: The user prompt
            system_prompt: Optional system prompt

        Returns:
            The LLM's response text
        """
        pass

    @abstractmethod
    def complete_json(self, prompt: str, system_prompt: Optional[str] = None) -> dict:
        """
        Send a prompt and parse the response as JSON.

        Args:
            prompt: The user prompt
            system_prompt: Optional system prompt

        Returns:
            Parsed JSON response as dict
        """
        pass


class OpenAIClient(BaseLLMClient):
    """OpenAI API client."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "gpt-4o"
    ):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise LLMClientError(
                "OpenAI API key not provided",
                provider="openai"
            )
        self.model = model

        # Import here to avoid import errors if not using OpenAI
        try:
            from openai import OpenAI
            self.client = OpenAI(api_key=self.api_key)
        except ImportError:
            raise LLMClientError(
                "openai package not installed. Run: pip install openai",
                provider="openai"
            )

    def complete(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        """Send prompt to OpenAI and return response."""
        messages = []

        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        messages.append({"role": "user", "content": prompt})

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=0.1  # Low temperature for consistent output
            )
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"OpenAI API error: {e}")
            raise LLMClientError(
                f"OpenAI API call failed: {str(e)}",
                provider="openai",
                details={"error": str(e)}
            )

    def complete_json(self, prompt: str, system_prompt: Optional[str] = None) -> dict:
        """Send prompt to OpenAI and parse JSON response."""
        messages = []

        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        messages.append({"role": "user", "content": prompt})

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=0.1,
                response_format={"type": "json_object"}
            )
            content = response.choices[0].message.content
            return json.loads(content)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse OpenAI response as JSON: {e}")
            raise LLMClientError(
                f"Failed to parse response as JSON: {str(e)}",
                provider="openai",
                details={"response": content}
            )
        except Exception as e:
            logger.error(f"OpenAI API error: {e}")
            raise LLMClientError(
                f"OpenAI API call failed: {str(e)}",
                provider="openai",
                details={"error": str(e)}
            )


class AnthropicClient(BaseLLMClient):
    """Anthropic API client."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "claude-sonnet-4-20250514"
    ):
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise LLMClientError(
                "Anthropic API key not provided",
                provider="anthropic"
            )
        self.model = model

        # Import here to avoid import errors if not using Anthropic
        try:
            import anthropic
            self.client = anthropic.Anthropic(api_key=self.api_key)
        except ImportError:
            raise LLMClientError(
                "anthropic package not installed. Run: pip install anthropic",
                provider="anthropic"
            )

    def complete(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        """Send prompt to Anthropic and return response."""
        try:
            kwargs = {
                "model": self.model,
                "max_tokens": 4096,
                "messages": [{"role": "user", "content": prompt}]
            }

            if system_prompt:
                kwargs["system"] = system_prompt

            response = self.client.messages.create(**kwargs)
            return response.content[0].text
        except Exception as e:
            logger.error(f"Anthropic API error: {e}")
            raise LLMClientError(
                f"Anthropic API call failed: {str(e)}",
                provider="anthropic",
                details={"error": str(e)}
            )

    def complete_json(self, prompt: str, system_prompt: Optional[str] = None) -> dict:
        """Send prompt to Anthropic and parse JSON response."""
        # Add JSON instruction to prompt
        json_prompt = f"{prompt}\n\nRespond with valid JSON only, no additional text."

        try:
            response_text = self.complete(json_prompt, system_prompt)

            # Try to extract JSON from response
            # Handle case where response might have markdown code blocks
            text = response_text.strip()
            if text.startswith("```json"):
                text = text[7:]
            if text.startswith("```"):
                text = text[3:]
            if text.endswith("```"):
                text = text[:-3]

            return json.loads(text.strip())
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse Anthropic response as JSON: {e}")
            raise LLMClientError(
                f"Failed to parse response as JSON: {str(e)}",
                provider="anthropic",
                details={"response": response_text}
            )


class LLMClient:
    """
    Factory class for creating LLM clients with provider switch.

    Usage:
        # Using environment variable LLM_PROVIDER
        client = LLMClient.create()

        # Explicit provider
        client = LLMClient.create(provider=LLMProvider.OPENAI)
        client = LLMClient.create(provider=LLMProvider.ANTHROPIC)
    """

    @staticmethod
    def create(
        provider: Optional[LLMProvider] = None,
        api_key: Optional[str] = None,
        model: Optional[str] = None
    ) -> BaseLLMClient:
        """
        Create an LLM client for the specified provider.

        Args:
            provider: LLM provider (defaults to env var LLM_PROVIDER or 'openai')
            api_key: API key (defaults to provider-specific env var)
            model: Model name (defaults to provider-specific default)

        Returns:
            Configured LLM client
        """
        if provider is None:
            provider_str = os.getenv("LLM_PROVIDER", "openai").lower()
            try:
                provider = LLMProvider(provider_str)
            except ValueError:
                logger.warning(
                    f"Unknown LLM_PROVIDER '{provider_str}', defaulting to openai"
                )
                provider = LLMProvider.OPENAI

        logger.info(f"Creating LLM client for provider: {provider.value}")

        if provider == LLMProvider.OPENAI:
            kwargs = {"api_key": api_key}
            if model:
                kwargs["model"] = model
            return OpenAIClient(**kwargs)

        elif provider == LLMProvider.ANTHROPIC:
            kwargs = {"api_key": api_key}
            if model:
                kwargs["model"] = model
            return AnthropicClient(**kwargs)

        else:
            raise LLMClientError(
                f"Unsupported provider: {provider}",
                provider=str(provider)
            )
