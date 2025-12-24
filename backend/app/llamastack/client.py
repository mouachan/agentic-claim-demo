"""
LlamaStack client for connecting to OpenShift AI 3.0 LlamaStack instance.
Provides methods for inference, embeddings, and agent runtime capabilities.
"""

import asyncio
import logging
from typing import Any, Dict, List, Optional

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.core.config import settings

logger = logging.getLogger(__name__)


class LlamaStackError(Exception):
    """Base exception for LlamaStack client errors."""

    pass


class LlamaStackClient:
    """
    Client for interacting with LlamaStack in OpenShift AI.

    This client connects to the LlamaStack instance deployed in RHOAI 3.0
    and provides methods for:
    - Text generation (inference)
    - Creating embeddings for RAG
    - Agent runtime capabilities
    """

    def __init__(
        self,
        endpoint: str = settings.llamastack_endpoint,
        api_key: Optional[str] = settings.llamastack_api_key,
        timeout: int = settings.llamastack_timeout,
        max_retries: int = settings.llamastack_max_retries,
    ):
        """
        Initialize LlamaStack client.

        Args:
            endpoint: LlamaStack API endpoint
            api_key: Optional API key for authentication
            timeout: Request timeout in seconds
            max_retries: Maximum number of retry attempts
        """
        self.endpoint = endpoint.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self.max_retries = max_retries

        # Setup HTTP client
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        self.client = httpx.AsyncClient(
            base_url=self.endpoint,
            headers=headers,
            timeout=httpx.Timeout(timeout=timeout),
        )

        logger.info(f"Initialized LlamaStack client for endpoint: {self.endpoint}")

    async def close(self):
        """Close the HTTP client."""
        await self.client.aclose()

    @retry(
        retry=retry_if_exception_type((httpx.HTTPError, httpx.TimeoutException)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
    )
    async def generate_text(
        self,
        prompt: str,
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
        top_p: float = 0.9,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Generate text using LlamaStack inference API.

        Args:
            prompt: Input prompt text
            model: Model name (defaults to configured default model)
            temperature: Sampling temperature (0.0 to 1.0)
            max_tokens: Maximum tokens to generate
            top_p: Top-p sampling parameter
            **kwargs: Additional model parameters

        Returns:
            Dictionary with generated text and metadata

        Raises:
            LlamaStackError: If the API request fails
        """
        model = model or settings.llamastack_default_model

        payload = {
            "model": model,
            "prompt": prompt,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "top_p": top_p,
            **kwargs,
        }

        try:
            response = await self.client.post("/inference/generate", json=payload)
            response.raise_for_status()
            result = response.json()

            logger.debug(f"Generated text using model {model}")
            return result

        except httpx.HTTPStatusError as e:
            error_msg = f"LlamaStack inference API error: {e.response.status_code} - {e.response.text}"
            logger.error(error_msg)
            raise LlamaStackError(error_msg) from e
        except httpx.RequestError as e:
            error_msg = f"LlamaStack connection error: {str(e)}"
            logger.error(error_msg)
            raise LlamaStackError(error_msg) from e

    @retry(
        retry=retry_if_exception_type((httpx.HTTPError, httpx.TimeoutException)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
    )
    async def create_embedding(
        self,
        text: str | List[str],
        model: Optional[str] = None,
    ) -> List[List[float]]:
        """
        Create embeddings for text using LlamaStack embeddings API.

        Args:
            text: Text string or list of strings to embed
            model: Embedding model name (defaults to configured embedding model)

        Returns:
            List of embedding vectors

        Raises:
            LlamaStackError: If the API request fails
        """
        model = model or settings.llamastack_embedding_model

        # Ensure text is a list
        if isinstance(text, str):
            texts = [text]
        else:
            texts = text

        payload = {
            "model": model,
            "input": texts,
        }

        try:
            response = await self.client.post("/embeddings", json=payload)
            response.raise_for_status()
            result = response.json()

            # Extract embeddings from response
            embeddings = [item["embedding"] for item in result.get("data", [])]

            logger.debug(f"Created {len(embeddings)} embeddings using model {model}")
            return embeddings

        except httpx.HTTPStatusError as e:
            error_msg = f"LlamaStack embeddings API error: {e.response.status_code} - {e.response.text}"
            logger.error(error_msg)
            raise LlamaStackError(error_msg) from e
        except httpx.RequestError as e:
            error_msg = f"LlamaStack connection error: {str(e)}"
            logger.error(error_msg)
            raise LlamaStackError(error_msg) from e

    async def chat_completion(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Chat completion using LlamaStack chat API.

        Args:
            messages: List of message dictionaries with 'role' and 'content'
            model: Model name
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
            **kwargs: Additional parameters

        Returns:
            Chat completion response

        Raises:
            LlamaStackError: If the API request fails
        """
        model = model or settings.llamastack_default_model

        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            **kwargs,
        }

        try:
            response = await self.client.post("/chat/completions", json=payload)
            response.raise_for_status()
            result = response.json()

            logger.debug(f"Chat completion with {len(messages)} messages")
            return result

        except httpx.HTTPStatusError as e:
            error_msg = f"LlamaStack chat API error: {e.response.status_code} - {e.response.text}"
            logger.error(error_msg)
            raise LlamaStackError(error_msg) from e
        except httpx.RequestError as e:
            error_msg = f"LlamaStack connection error: {str(e)}"
            logger.error(error_msg)
            raise LlamaStackError(error_msg) from e

    async def validate_extracted_data(
        self,
        ocr_text: str,
        expected_fields: List[str],
    ) -> Dict[str, Any]:
        """
        Validate and structure OCR extracted data using LLM.

        Args:
            ocr_text: Raw OCR extracted text
            expected_fields: List of expected fields to extract

        Returns:
            Dictionary with validated and structured data
        """
        prompt = f"""
You are an expert at validating and structuring insurance claim documents.

Given the following OCR extracted text, extract and validate these fields: {', '.join(expected_fields)}

OCR Text:
{ocr_text}

Return a JSON object with the extracted fields. If a field is not found or unclear, set it to null.
Also include a "confidence" score (0-1) for each field.
"""

        result = await self.generate_text(
            prompt=prompt,
            temperature=0.1,  # Low temperature for consistent extraction
            max_tokens=1024,
        )

        return result

    async def analyze_claim(
        self,
        claim_data: Dict[str, Any],
        user_contracts: List[Dict[str, Any]],
        similar_claims: List[Dict[str, Any]],
        policies: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Analyze claim and make a decision recommendation.

        Args:
            claim_data: Structured claim data
            user_contracts: User's active contracts
            similar_claims: Similar historical claims
            policies: Relevant policy documents

        Returns:
            Analysis result with recommendation and reasoning
        """
        messages = [
            {
                "role": "system",
                "content": "You are an expert insurance claims analyst. Analyze claims and provide recommendations based on policy coverage, user contracts, and historical data.",
            },
            {
                "role": "user",
                "content": f"""
Analyze this insurance claim and provide a recommendation.

Claim Data:
{claim_data}

User Contracts:
{user_contracts}

Similar Historical Claims:
{similar_claims}

Relevant Policies:
{policies}

Provide your analysis in JSON format with:
{{
    "recommendation": "approve" | "deny" | "manual_review",
    "confidence": 0.0-1.0,
    "reasoning": "detailed explanation",
    "relevant_policy_sections": ["list of relevant policy sections"],
    "coverage_amount": estimated coverage amount if applicable
}}
""",
            },
        ]

        result = await self.chat_completion(
            messages=messages,
            temperature=0.3,
            max_tokens=2048,
        )

        return result

    async def create_agent_session(
        self,
        agent_config: Dict[str, Any],
        session_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Create a new agent session with LlamaStack Agents API.

        Args:
            agent_config: Agent configuration including model, tools, instructions
            session_name: Optional session name for tracking

        Returns:
            Session information with session_id

        Raises:
            LlamaStackError: If the API request fails
        """
        payload = {
            "agent_config": agent_config,
            "session_name": session_name or f"session_{asyncio.get_event_loop().time()}",
        }

        try:
            response = await self.client.post("/agents/session/create", json=payload)
            response.raise_for_status()
            result = response.json()

            logger.info(f"Created agent session: {result.get('session_id')}")
            return result

        except httpx.HTTPStatusError as e:
            error_msg = f"LlamaStack agents API error: {e.response.status_code} - {e.response.text}"
            logger.error(error_msg)
            raise LlamaStackError(error_msg) from e
        except httpx.RequestError as e:
            error_msg = f"LlamaStack connection error: {str(e)}"
            logger.error(error_msg)
            raise LlamaStackError(error_msg) from e

    @retry(
        retry=retry_if_exception_type((httpx.HTTPError, httpx.TimeoutException)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
    )
    async def run_agent_turn(
        self,
        session_id: str,
        messages: List[Dict[str, str]],
        stream: bool = False,
    ) -> Dict[str, Any]:
        """
        Run one turn of the agent in a session.

        The agent will automatically:
        - Analyze the user message
        - Determine which tools to call
        - Execute tools in the right order
        - Synthesize a final response

        Args:
            session_id: Session ID from create_agent_session()
            messages: List of messages to send (typically user message)
            stream: Whether to stream the response (not implemented yet)

        Returns:
            Agent turn result with messages, tool calls, and final response

        Raises:
            LlamaStackError: If the API request fails
        """
        payload = {
            "session_id": session_id,
            "messages": messages,
            "stream": stream,
        }

        try:
            response = await self.client.post("/agents/turn", json=payload)
            response.raise_for_status()
            result = response.json()

            logger.debug(f"Executed agent turn in session {session_id}")
            return result

        except httpx.HTTPStatusError as e:
            error_msg = f"LlamaStack agents turn API error: {e.response.status_code} - {e.response.text}"
            logger.error(error_msg)
            raise LlamaStackError(error_msg) from e
        except httpx.RequestError as e:
            error_msg = f"LlamaStack connection error: {str(e)}"
            logger.error(error_msg)
            raise LlamaStackError(error_msg) from e

    async def get_session_messages(
        self,
        session_id: str,
    ) -> List[Dict[str, Any]]:
        """
        Get all messages from an agent session.

        Args:
            session_id: Session ID

        Returns:
            List of messages with role, content, tool_calls, etc.

        Raises:
            LlamaStackError: If the API request fails
        """
        try:
            response = await self.client.get(f"/agents/session/{session_id}/messages")
            response.raise_for_status()
            result = response.json()

            messages = result.get("messages", [])
            logger.debug(f"Retrieved {len(messages)} messages from session {session_id}")
            return messages

        except httpx.HTTPStatusError as e:
            error_msg = f"LlamaStack agents session API error: {e.response.status_code} - {e.response.text}"
            logger.error(error_msg)
            raise LlamaStackError(error_msg) from e
        except httpx.RequestError as e:
            error_msg = f"LlamaStack connection error: {str(e)}"
            logger.error(error_msg)
            raise LlamaStackError(error_msg) from e

    async def health_check(self) -> bool:
        """
        Check if LlamaStack service is healthy.

        Returns:
            True if healthy, False otherwise
        """
        try:
            response = await self.client.get("/health")
            return response.status_code == 200
        except Exception as e:
            logger.error(f"LlamaStack health check failed: {str(e)}")
            return False


# Global client instance
_llamastack_client: Optional[LlamaStackClient] = None


def get_llamastack_client() -> LlamaStackClient:
    """
    Get or create global LlamaStack client instance.

    Returns:
        LlamaStackClient instance
    """
    global _llamastack_client

    if _llamastack_client is None:
        _llamastack_client = LlamaStackClient()

    return _llamastack_client
