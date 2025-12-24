"""
Intelligent Orchestrator using LlamaStack Agents API (not Responses API).

Uses the actual API exposed by our LlamaStack: /agents
"""

import os
import json
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime
import uuid

import httpx
from fastapi import HTTPException

logger = logging.getLogger(__name__)

# Configuration
LLAMASTACK_ENDPOINT = os.getenv("LLAMASTACK_ENDPOINT", "http://claims-llamastack-service.claims-demo.svc.cluster.local:8321")
OCR_SERVER_URL = os.getenv("OCR_SERVER_URL", "http://ocr-server.claims-demo.svc.cluster.local:8080")
RAG_SERVER_URL = os.getenv("RAG_SERVER_URL", "http://rag-server.claims-demo.svc.cluster.local:8080")
LLM_ENDPOINT = os.getenv("LLM_ENDPOINT", "https://llama-instruct-32-3b-llama-instruct-32-3b-demo.apps.cluster-rk6mx.rk6mx.sandbox492.opentlc.com/v1/chat/completions")
LLM_MODEL_NAME = os.getenv("LLM_MODEL_NAME", "llama-instruct-32-3b")


# Agent system prompt
AGENT_SYSTEM_PROMPT = """Tu es un agent intelligent de traitement de claims d'assurance.

## Tools Disponibles:

1. **ocr_document**: Extrait texte d'un PDF
2. **retrieve_user_info**: Récupère contrats utilisateur
3. **retrieve_similar_claims**: Trouve claims similaires (optionnel, si >$5000)
4. **make_final_decision**: Décision finale

## Workflow:
1. ocr_document → extraire infos
2. retrieve_user_info → vérifier contrats
3. (Optionnel) retrieve_similar_claims → si montant >$5000
4. make_final_decision → décider

Sois efficace: n'appelle que les tools nécessaires.
"""


async def call_mcp_server(
    server_url: str,
    endpoint: str,
    payload: Dict[str, Any],
    timeout: int = 60
) -> Optional[Dict[str, Any]]:
    """Call an MCP server endpoint."""
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(f"{server_url}/{endpoint}", json=payload)
            response.raise_for_status()
            result = response.json()
            return result
    except Exception as e:
        logger.error(f"Error calling {server_url}/{endpoint}: {str(e)}")
        return None


async def intelligent_orchestrate_with_llm(
    claim_id: str,
    document_path: str,
    user_id: str,
    claim_type: str
) -> Dict[str, Any]:
    """
    Simplified intelligent orchestration using direct LLM tool calling.

    Since LlamaStack Responses API is not available, we use the inference API
    with tool calling.
    """

    start_time = datetime.now()
    processing_steps = []
    warnings = []

    # Tool definitions
    tools = [
        {
            "type": "function",
            "function": {
                "name": "ocr_document",
                "description": "Extract text from PDF. Always call first.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "document_path": {"type": "string", "description": "PDF path"}
                    },
                    "required": ["document_path"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "retrieve_user_info",
                "description": "Get user contracts. Required before decision.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "user_id": {"type": "string"}
                    },
                    "required": ["user_id"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "retrieve_similar_claims",
                "description": "Find similar claims. Use for amounts >$5000.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "claim_text": {"type": "string"},
                        "top_k": {"type": "integer", "default": 5}
                    },
                    "required": ["claim_text"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "make_final_decision",
                "description": "Final decision. Call when all data gathered.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "claim_id": {"type": "string"},
                        "user_id": {"type": "string"},
                        "decision": {"type": "string", "enum": ["approve", "deny", "manual_review"]},
                        "confidence": {"type": "number"},
                        "reasoning": {"type": "string"}
                    },
                    "required": ["claim_id", "user_id", "decision", "confidence", "reasoning"]
                }
            }
        }
    ]

    # State
    state = {
        "claim_id": claim_id,
        "document_path": document_path,
        "user_id": user_id,
        "claim_type": claim_type
    }

    # Messages
    messages = [
        {"role": "system", "content": AGENT_SYSTEM_PROMPT},
        {"role": "user", "content": f"Process claim {claim_id} (type: {claim_type}, doc: {document_path}, user: {user_id})"}
    ]

    max_iterations = 10
    iteration = 0
    final_decision = None

    while iteration < max_iterations:
        iteration += 1
        logger.info(f"Iteration {iteration}: Asking LLM for next tool...")

        try:
            # Call LLM with tool calling
            logger.debug(f"Calling LLM with {len(tools)} tools and {len(messages)} messages")
            async with httpx.AsyncClient(timeout=90.0) as client:
                response = await client.post(
                    LLM_ENDPOINT,
                    json={
                        "model": LLM_MODEL_NAME,
                        "messages": messages,
                        "tools": tools,
                        "tool_choice": "auto",
                        "temperature": 0.3,
                        "max_tokens": 2000,
                    }
                )

                if response.status_code != 200:
                    logger.error(f"LLM failed: {response.status_code} - {response.text}")
                    break

                result = response.json()
                assistant_message = result["choices"][0]["message"]
                messages.append(assistant_message)

                # Check for tool call
                if assistant_message.get("tool_calls"):
                    tool_call = assistant_message["tool_calls"][0]
                    tool_name = tool_call["function"]["name"]
                    tool_args = json.loads(tool_call["function"]["arguments"])

                    logger.info(f"LLM chose: {tool_name} with {tool_args}")

                    # Execute tool
                    step_start = datetime.now()
                    tool_result = await execute_tool(tool_name, tool_args, state)
                    step_duration = int((datetime.now() - step_start).total_seconds() * 1000)

                    processing_steps.append({
                        "step_name": tool_name,
                        "agent": f"{tool_name.replace('_', '-')}-agent",
                        "status": "completed" if tool_result else "failed",
                        "duration_ms": step_duration,
                        "output": tool_result or {},
                        "started_at": step_start.isoformat(),
                        "completed_at": datetime.now().isoformat()
                    })

                    # Add tool result to messages
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call["id"],
                        "content": json.dumps(tool_result) if tool_result else "Tool failed"
                    })

                    # Check if final decision
                    if tool_name == "make_final_decision" and tool_result:
                        final_decision = tool_result
                        break

                else:
                    # No tool call - done
                    logger.warning(f"LLM did not call any tools. Response: {assistant_message.get('content', 'No content')[:500]}")
                    warnings.append("LLM did not call expected tools")
                    break

        except Exception as e:
            logger.error(f"Iteration {iteration} error: {str(e)}")
            warnings.append(f"Error: {str(e)}")
            break

    total_duration = int((datetime.now() - start_time).total_seconds() * 1000)

    return {
        "claim_id": claim_id,
        "status": "completed" if final_decision else "failed",
        "processing_steps": processing_steps,
        "final_decision": final_decision,
        "total_processing_time_ms": total_duration,
        "warnings": warnings
    }


async def execute_tool(
    tool_name: str,
    arguments: Dict[str, Any],
    state: Dict[str, Any]
) -> Optional[Dict[str, Any]]:
    """Execute a tool."""

    try:
        if tool_name == "ocr_document":
            return await call_mcp_server(
                OCR_SERVER_URL,
                "ocr_document",
                {
                    "document_path": arguments.get("document_path", state["document_path"]),
                    "document_type": "claim_form",
                    "language": "eng"
                }
            )

        elif tool_name == "retrieve_user_info":
            return await call_mcp_server(
                RAG_SERVER_URL,
                "retrieve_user_info",
                {
                    "user_id": arguments.get("user_id", state["user_id"]),
                    "query": "active insurance contracts",
                    "top_k": 5,
                    "include_contracts": True
                }
            )

        elif tool_name == "retrieve_similar_claims":
            return await call_mcp_server(
                RAG_SERVER_URL,
                "retrieve_similar_claims",
                {
                    "claim_text": arguments.get("claim_text", "")[:1000],
                    "top_k": arguments.get("top_k", 5),
                    "min_similarity": 0.7
                }
            )

        elif tool_name == "make_final_decision":
            # LLM has decided, just return it
            return {
                "recommendation": arguments.get("decision", "manual_review"),
                "confidence": arguments.get("confidence", 0.5),
                "reasoning": arguments.get("reasoning", ""),
                "relevant_policies": arguments.get("relevant_policies", [])
            }

    except Exception as e:
        logger.error(f"Tool {tool_name} error: {str(e)}")
        return None
