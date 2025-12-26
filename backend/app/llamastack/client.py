"""
LlamaStack client for connecting to OpenShift AI 3.0 LlamaStack instance.
Uses the official llama-stack-client directly without wrappers.
"""

import logging
from typing import Optional

from llama_stack_client import LlamaStackClient

from app.core.config import settings

logger = logging.getLogger(__name__)


class LlamaStackError(Exception):
    """Exception raised for LlamaStack API errors."""
    pass


# Global client instance
_client: Optional[LlamaStackClient] = None


def get_llamastack_client() -> LlamaStackClient:
    """
    Get or create the global LlamaStack client instance.

    Returns:
        LlamaStackClient instance
    """
    global _client
    if _client is None:
        _client = LlamaStackClient(base_url=settings.llamastack_endpoint)
        logger.info(f"Initialized LlamaStack client: {settings.llamastack_endpoint}")
    return _client
