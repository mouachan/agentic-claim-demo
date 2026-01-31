"""
Responses API Orchestrator for LlamaStack.

Drop-in replacement for AgentOrchestrator that uses /v1/responses instead of /v1/agents.
Automatic tool execution - no manual loops needed.
"""
import httpx
import logging
from typing import Dict, Any, List, Optional

from app.core.config import settings

logger = logging.getLogger(__name__)


class ResponsesOrchestrator:
    """Orchestrate LLM interactions using Responses API with automatic tool execution."""

    def __init__(self, base_url: Optional[str] = None, timeout: float = 300.0):
        """
        Initialize orchestrator.

        Args:
            base_url: LlamaStack endpoint URL
            timeout: Request timeout in seconds
        """
        self.base_url = base_url or settings.llamastack_endpoint
        self.timeout = timeout
        self.model = settings.llamastack_default_model

        # MCP server configurations
        self.mcp_servers = {
            "ocr-server": {
                "server_label": "ocr-server",
                "server_url": "http://ocr-server.claims-demo.svc.cluster.local:8080/sse"
            },
            "rag-server": {
                "server_label": "rag-server",
                "server_url": "http://rag-server.claims-demo.svc.cluster.local:8080/sse"
            }
        }

    def _build_mcp_tools(self, tools: List[str]) -> List[Dict[str, Any]]:
        """
        Build MCP tool configurations from tool names.

        Args:
            tools: List of tool names (e.g., ["ocr_document", "retrieve_user_info"])

        Returns:
            List of MCP tool configurations
        """
        # Map tools to their servers
        tool_to_server = {
            "ocr_document": "ocr-server",
            "ocr_health_check": "ocr-server",
            "list_supported_formats": "ocr-server",
            "retrieve_user_info": "rag-server",
            "retrieve_similar_claims": "rag-server",
            "search_knowledge_base": "rag-server",
            "rag_health_check": "rag-server"
        }

        # Group tools by server
        servers_with_tools = {}
        for tool_name in tools:
            server = tool_to_server.get(tool_name)
            if not server:
                logger.warning(f"Unknown tool: {tool_name}")
                continue

            if server not in servers_with_tools:
                servers_with_tools[server] = []
            servers_with_tools[server].append(tool_name)

        # Build MCP tool configs
        mcp_tools = []
        for server, server_tools in servers_with_tools.items():
            config = self.mcp_servers[server].copy()
            config["type"] = "mcp"
            config["allowed_tools"] = server_tools
            mcp_tools.append(config)

        return mcp_tools

    async def process_with_agent(
        self,
        agent_config: Dict[str, Any],
        input_message: Any,  # Can be str or List[Dict]
        tools: Optional[List[str]] = None,
        session_name: Optional[str] = None,
        cleanup: bool = True
    ) -> Dict[str, Any]:
        """
        High-level method to process a task with an agent.

        Compatibility method matching AgentOrchestrator interface.
        Uses Responses API instead of Agents API.

        Args:
            agent_config: Agent configuration with instructions
            input_message: Input message (str) or conversation history (List[Dict])
            tools: Optional list of tools to enable
            session_name: Optional session name (ignored - for compatibility)
            cleanup: Whether to cleanup (ignored - for compatibility)

        Returns:
            Agent response with output

        Raises:
            httpx.HTTPError: If any step fails
        """
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            # Build request payload
            payload = {
                "model": agent_config.get("model", self.model),
                "input": input_message,  # Can be string or array of messages
                "stream": False,
                "max_infer_iters": 10
            }

            # Add instructions from agent_config
            if "instructions" in agent_config:
                payload["instructions"] = agent_config["instructions"]

            # Add tools if provided
            if tools:
                payload["tools"] = self._build_mcp_tools(tools)

            # Log input type
            input_type = "message_array" if isinstance(input_message, list) else "string"
            logger.info(f"Calling Responses API with {len(tools or [])} tools, input_type={input_type}")
            if isinstance(input_message, str):
                logger.debug(f"Input: {input_message[:100]}")
            else:
                logger.debug(f"Input: {len(input_message)} messages in conversation")

            # Call Responses API
            response = await client.post(
                f"{self.base_url}/v1/responses",
                json=payload
            )

            response.raise_for_status()
            result = response.json()

            # DEBUG: Log full response structure to see available timing fields
            import json
            logger.info(f"LlamaStack full response: {json.dumps(result, indent=2)}")

            # Extract output
            output_items = result.get("output", [])

            # Find the final message
            final_message = None
            tool_calls = []

            for item in output_items:
                if item.get("type") == "message":
                    final_message = item
                elif item.get("type") == "mcp_call":
                    tool_calls.append({
                        "name": item.get("name"),
                        "server": item.get("server_label"),
                        "output": item.get("output"),
                        "error": item.get("error")
                    })

            # Extract text content
            output_text = ""
            if final_message and "content" in final_message:
                for content_item in final_message["content"]:
                    if content_item.get("type") == "output_text":
                        output_text = content_item.get("text", "")
                        break

            logger.info(f"Response completed: tools_used={len(tool_calls)}")

            # Return in AgentOrchestrator-compatible format
            return {
                "response_id": result.get("id"),
                "turn_result": {
                    "response": {
                        "content": output_text
                    },
                    "tool_calls": tool_calls
                },
                "output": output_text,
                "tool_calls": tool_calls,  # Also at root for easy access
                "usage": result.get("usage", {})
            }
