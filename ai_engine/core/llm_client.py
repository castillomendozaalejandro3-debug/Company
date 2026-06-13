"""
LLM Client for Helios AI Engine

Provides a unified interface for interacting with Large Language Models.
Integrates with the CircularContextManager to inject contextual memory
into every prompt, preventing hallucinations and maintaining awareness.
"""

import os
import json
import time
import logging
from typing import Dict, Any, Optional, List, AsyncGenerator
from pathlib import Path

# Setup logger
logger = logging.getLogger("Helios.LLMClient")

try:
    import httpx
    HTTPX_AVAILABLE = True
except ImportError:
    HTTPX_AVAILABLE = False

try:
    import openai
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False

from .memory_manager import get_memory_manager, CircularContextManager


class LLMClientError(Exception):
    """Exception raised when LLM operations fail."""
    pass


class LLMClient:
    """
    Unified LLM client with integrated memory management.
    
    Features:
    - Automatic context injection from CircularContextManager
    - Support for multiple LLM providers (OpenAI, local endpoints)
    - Streaming and non-streaming modes
    - Token usage tracking
    - Error handling with memory logging
    """
    
    # Default configuration
    DEFAULT_MODEL = "gpt-4"
    DEFAULT_MAX_TOKENS = 2048
    DEFAULT_TEMPERATURE = 0.7
    DEFAULT_TIMEOUT = 30.0
    
    def __init__(
        self,
        model: Optional[str] = None,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        temperature: float = DEFAULT_TEMPERATURE,
        timeout: float = DEFAULT_TIMEOUT,
        memory_manager: Optional[CircularContextManager] = None,
        provider: str = "openai"
    ):
        """
        Initialize the LLM Client.
        
        Args:
            model: Model name/identifier
            api_key: API key (or use OPENAI_API_KEY env var)
            base_url: Custom API endpoint (for local models)
            max_tokens: Maximum tokens in response
            temperature: Sampling temperature (0.0-2.0)
            timeout: Request timeout in seconds
            memory_manager: Optional custom memory manager instance
            provider: LLM provider ('openai', 'local', 'anthropic', etc.)
        """
        self.model = model or os.getenv("HELIOS_LLM_MODEL", "cognitivecomputations/dolphin-mistral-7b")
        self.api_key = api_key or os.getenv("OPENROUTER_API_KEY") or os.getenv("OPENAI_API_KEY")
        self.base_url = base_url or os.getenv("OPENROUTER_BASE_URL") or os.getenv("HELIOS_LLM_BASE_URL")
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.timeout = timeout
        self.provider = provider
        
        # Get memory manager (singleton or custom)
        self._memory_manager = memory_manager or get_memory_manager()
        
        # Track token usage
        self._total_tokens_used = 0
        self._request_count = 0
        
        # Initialize provider-specific client
        self._client = self._initialize_client()
        
        logger.info(f"LLM Client initialized: model={self.model}, provider={self.provider}")
    
    def _initialize_client(self) -> Any:
        """Initialize the appropriate client based on provider."""
        if self.provider == "openai" and OPENAI_AVAILABLE:
            if self.api_key:
                if self.base_url:
                    return openai.OpenAI(api_key=self.api_key, base_url=self.base_url)
                else:
                    return openai.OpenAI(api_key=self.api_key)
            else:
                logger.warning("OpenAI API key not set, using mock mode")
                return None
        elif self.provider == "local" and HTTPX_AVAILABLE:
            return httpx.Client(timeout=self.timeout)
        else:
            logger.warning(f"Provider '{self.provider}' not fully configured, using mock mode")
            return None
    
    def _inject_context(self, user_message: str) -> str:
        """
        Inject memory context into the user message.
        
        This is the core integration point with CircularContextManager.
        It prepends system rules, error history, and recent errors to
        every prompt sent to the LLM.
        
        Args:
            user_message: Original user message
            
        Returns:
            str: Message with injected context
        """
        return self._memory_manager.get_context_for_llm(user_message)
    
    def _log_error_to_memory(self, error_content: str) -> None:
        """Log an error to the memory manager for future context."""
        self._memory_manager.add_error(error_content)
    
    async def chat(
        self,
        message: str,
        system_prompt: Optional[str] = None,
        stream: bool = False,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Send a chat message to the LLM with automatic context injection.
        
        Args:
            message: User message
            system_prompt: Optional system prompt override
            stream: Whether to stream the response
            **kwargs: Additional provider-specific parameters
            
        Returns:
            Dictionary with response content and metadata
        """
        self._request_count += 1
        start_time = time.time()
        
        # Inject context automatically
        full_message = self._inject_context(message)
        
        # Build messages array
        messages = []
        
        # Add system prompt (default or custom)
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        else:
            # Default system prompt emphasizing memory awareness
            messages.append({
                "role": "system",
                "content": "You are Helios AI, an intelligent multi-agent system. "
                          "You have access to memory context including system rules, "
                          "error history, and recent issues. Use this context to provide "
                          "accurate, safe responses. Always follow the immutable rules."
            })
        
        # Add user message with injected context
        messages.append({"role": "user", "content": full_message})
        
        try:
            if self.provider == "openai" and self._client:
                response = await self._chat_openai(messages, stream, **kwargs)
            elif self.provider == "local" and self._client:
                response = await self._chat_local(messages, **kwargs)
            else:
                # Mock mode for testing/development
                response = await self._chat_mock(messages, **kwargs)
            
            # Calculate duration
            duration_ms = int((time.time() - start_time) * 1000)
            response["duration_ms"] = duration_ms
            response["context_injected"] = True
            response["memory_stats"] = self._memory_manager.get_statistics()
            
            return response
            
        except Exception as e:
            # Log error to memory
            error_content = f"{type(e).__name__}: {str(e)}"
            self._log_error_to_memory(error_content)
            
            logger.error(f"LLM request failed: {error_content}")
            raise LLMClientError(f"LLM request failed: {str(e)}")
    
    async def _chat_openai(
        self,
        messages: List[Dict[str, str]],
        stream: bool = False,
        **kwargs
    ) -> Dict[str, Any]:
        """Send chat request to OpenAI-compatible API."""
        if not self._client:
            raise LLMClientError("OpenAI client not initialized")
        
        # Prepare parameters
        params = {
            "model": self.model,
            "messages": messages,
            "max_tokens": kwargs.get("max_tokens", self.max_tokens),
            "temperature": kwargs.get("temperature", self.temperature),
            "stream": stream,
        }
        
        if stream:
            # Streaming response
            response_stream = self._client.chat.completions.create(**params)
            content_parts = []
            for chunk in response_stream:
                if chunk.choices[0].delta.content:
                    content_parts.append(chunk.choices[0].delta.content)
            
            content = "".join(content_parts)
            return {
                "success": True,
                "content": content,
                "usage": {"total_tokens": 0},  # Not available in streaming
            }
        else:
            # Non-streaming response
            response = self._client.chat.completions.create(**params)
            
            # Update token usage
            if hasattr(response, "usage") and response.usage:
                self._total_tokens_used += response.usage.total_tokens
            
            return {
                "success": True,
                "content": response.choices[0].message.content,
                "usage": {
                    "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
                    "completion_tokens": response.usage.completion_tokens if response.usage else 0,
                    "total_tokens": response.usage.total_tokens if response.usage else 0,
                },
                "model": response.model,
            }
    
    async def _chat_local(
        self,
        messages: List[Dict[str, str]],
        **kwargs
    ) -> Dict[str, Any]:
        """Send chat request to local/custom endpoint."""
        if not self._client:
            raise LLMClientError("Local client not initialized")
        
        if not self.base_url:
            raise LLMClientError("Base URL not configured for local provider")
        
        payload = {
            "model": self.model,
            "messages": messages,
            "max_tokens": kwargs.get("max_tokens", self.max_tokens),
            "temperature": kwargs.get("temperature", self.temperature),
        }
        
        headers = {
            "Content-Type": "application/json",
        }
        
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        
        response = self._client.post(
            f"{self.base_url}/v1/chat/completions",
            json=payload,
            headers=headers
        )
        response.raise_for_status()
        data = response.json()
        
        return {
            "success": True,
            "content": data["choices"][0]["message"]["content"],
            "usage": data.get("usage", {}),
        }
    
    async def _chat_mock(
        self,
        messages: List[Dict[str, str]],
        **kwargs
    ) -> Dict[str, Any]:
        """Mock response for development/testing without API key."""
        logger.warning("Using mock LLM response (no API key configured)")
        
        # Simulate processing delay
        await asyncio.sleep(0.1)
        
        # Return a helpful mock response
        last_message = messages[-1]["content"] if messages else ""
        
        return {
            "success": True,
            "content": f"[MOCK RESPONSE] I received your request. Context was injected with {len(messages)} messages. "
                      f"Memory stats: {self._memory_manager.get_statistics()}",
            "usage": {"total_tokens": 0},
            "mock": True,
        }
    
    async def complete(
        self,
        prompt: str,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Send a completion request (legacy API style).
        
        Args:
            prompt: Text prompt for completion
            **kwargs: Additional parameters
            
        Returns:
            Dictionary with completion result
        """
        # Wrap in chat format for consistency
        return await self.chat(message=prompt, **kwargs)
    
    def get_usage_stats(self) -> Dict[str, Any]:
        """Get cumulative token usage statistics."""
        return {
            "total_tokens_used": self._total_tokens_used,
            "request_count": self._request_count,
            "average_tokens_per_request": (
                self._total_tokens_used / self._request_count 
                if self._request_count > 0 else 0
            ),
            "memory_stats": self._memory_manager.get_statistics(),
        }
    
    def reset_usage_stats(self) -> None:
        """Reset token usage counters."""
        self._total_tokens_used = 0
        self._request_count = 0
    
    def add_error_to_memory(self, error: str) -> None:
        """Manually add an error to memory (convenience method)."""
        self._memory_manager.add_error(error)
    
    def get_memory_context(self, user_message: str) -> str:
        """Get the formatted context that would be injected (for debugging)."""
        return self._memory_manager.get_context_for_llm(user_message)


# Import asyncio for mock mode
import asyncio

# Singleton instance
_llm_client: Optional[LLMClient] = None


def get_llm_client() -> LLMClient:
    """Get the global LLM client instance (singleton)."""
    global _llm_client
    if _llm_client is None:
        _llm_client = LLMClient()
    return _llm_client


def initialize_llm_client(
    model: Optional[str] = None,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    **kwargs
) -> LLMClient:
    """Initialize the global LLM client with custom settings."""
    global _llm_client
    _llm_client = LLMClient(
        model=model,
        api_key=api_key,
        base_url=base_url,
        **kwargs
    )
    return _llm_client
