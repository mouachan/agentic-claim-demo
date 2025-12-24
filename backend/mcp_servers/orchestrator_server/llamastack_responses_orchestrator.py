"""
Intelligent Orchestrator using LlamaStack Responses API.

Uses the official LlamaStack Responses API which handles ALL orchestration logic.
LlamaStack automatically decides which tools to call, in what order, and when to stop.

References:
- https://developers.redhat.com/articles/2025/08/20/your-agent-your-rules-deep-dive-responses-api-llama-stack
- https://developers.redhat.com/articles/2025/12/09/your-ai-agents-evolved-modernize-llama-stack-agents-migrating-responses-api
"""

import os
import json
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime

import httpx
from fastapi import HTTPException

logger = logging.getLogger(__name__)

# Configuration
LLAMASTACK_ENDPOINT = os.getenv("LLAMASTACK_ENDPOINT", "http://claims-llamastack-service.claims-demo.svc.cluster.local:8321")
OCR_SERVER_URL = os.getenv("OCR_SERVER_URL", "http://ocr-server.claims-demo.svc.cluster.local:8080")
RAG_SERVER_URL = os.getenv("RAG_SERVER_URL", "http://rag-server.claims-demo.svc.cluster.local:8080")
GUARDRAILS_SERVER_URL = os.getenv("GUARDRAILS_SERVER_URL", "http://claims-guardrails.claims-demo.svc.cluster.local:8080")

# System prompt for claim processing agent
CLAIM_PROCESSING_AGENT_PROMPT = """Tu es un agent intelligent de traitement de claims d'assurance.

## Ton Rôle:
Analyser et décider sur les claims d'assurance en appelant les tools appropriés.

## Tools Disponibles:

1. **ocr_document**: Extrait le texte d'un PDF
   - Utilise TOUJOURS en premier
   - Retourne raw_text + structured_data (montant, date, etc.)

2. **retrieve_user_info**: Récupère contrats utilisateur
   - Utilise pour vérifier la couverture
   - Retourne user_info, contracts

3. **retrieve_similar_claims**: Trouve claims similaires
   - Utilise pour montants élevés (>$5000) ou cas complexes
   - Retourne similar_claims avec outcomes

4. **make_final_decision**: Décision finale
   - Utilise quand tu as TOUTES les données nécessaires
   - Retourne decision (approve/deny/manual_review), confidence, reasoning

## Workflow Standard:
1. ocr_document → extraire infos du PDF
2. retrieve_user_info → vérifier contrats actifs
3. (Optionnel) retrieve_similar_claims → si montant >$5000 ou complexe
4. make_final_decision → décision finale

NOTE: Les guardrails (détection PII, données sensibles) sont gérés AUTOMATIQUEMENT par LlamaStack!

## Règles Importantes:
- Si aucun contrat actif pour le type de claim → deny ou manual_review
- Si montant > $10,000 → TOUJOURS appeler retrieve_similar_claims
- Sois efficace: n'appelle que les tools nécessaires

Commence par ocr_document, puis décide intelligemment des prochaines étapes.
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
            logger.info(f"MCP {endpoint} returned: {json.dumps(result, indent=2)[:200]}")
            return result
    except Exception as e:
        logger.error(f"Error calling {server_url}/{endpoint}: {str(e)}")
        return None


async def intelligent_orchestrate_with_llamastack(
    claim_id: str,
    document_path: str,
    user_id: str,
    claim_type: str
) -> Dict[str, Any]:
    """
    Intelligent orchestration using LlamaStack Responses API.

    LlamaStack handles ALL the orchestration:
    - Decides which tools to call
    - Manages the conversation loop
    - Stops when done

    We just provide the tools and initial message!
    """

    start_time = datetime.now()
    processing_steps = []
    warnings = []

    # MCP Tools definitions for LlamaStack
    # NOTE: Guardrails are handled automatically by LlamaStack, no need for check_guardrails tool!
    tools = [
        {
            "type": "function",
            "function": {
                "name": "ocr_document",
                "description": "Extract text and structured data from a claim PDF document using OCR. Always call this first.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "document_path": {
                            "type": "string",
                            "description": "Path to the PDF document to process"
                        }
                    },
                    "required": ["document_path"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "retrieve_user_info",
                "description": "Retrieve user's insurance contracts and history from vector database. Required before making decision.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "user_id": {
                            "type": "string",
                            "description": "User ID to retrieve information for"
                        },
                        "query": {
                            "type": "string",
                            "description": "Query for relevant information (e.g., 'active AUTO contracts')",
                            "default": "active insurance contracts"
                        }
                    },
                    "required": ["user_id"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "retrieve_similar_claims",
                "description": "Find similar historical claims. Use for high amounts (>$5000) or complex cases.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "claim_text": {
                            "type": "string",
                            "description": "Claim description to find similar claims for"
                        },
                        "top_k": {
                            "type": "integer",
                            "description": "Number of similar claims to retrieve",
                            "default": 5
                        }
                    },
                    "required": ["claim_text"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "make_final_decision",
                "description": "Make final decision on the claim. Call only when you have all necessary information.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "claim_id": {
                            "type": "string",
                            "description": "Claim ID"
                        },
                        "user_id": {
                            "type": "string",
                            "description": "User ID"
                        },
                        "decision": {
                            "type": "string",
                            "enum": ["approve", "deny", "manual_review"],
                            "description": "Your decision"
                        },
                        "confidence": {
                            "type": "number",
                            "description": "Confidence in decision (0.0-1.0)"
                        },
                        "reasoning": {
                            "type": "string",
                            "description": "Detailed reasoning for the decision"
                        },
                        "relevant_policies": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "List of relevant policy clauses"
                        }
                    },
                    "required": ["claim_id", "user_id", "decision", "confidence", "reasoning"]
                }
            }
        }
    ]

    # Initial user message
    user_message = f"""Nouveau claim à traiter:

**Claim ID**: {claim_id}
**Type**: {claim_type}
**User ID**: {user_id}
**Document**: {document_path}

Traite ce claim en appelant les tools appropriés. Commence par extraire les données du document.
"""

    # Store state for tool execution
    state = {
        "claim_id": claim_id,
        "document_path": document_path,
        "user_id": user_id,
        "claim_type": claim_type
    }

    try:
        # Call LlamaStack Responses API with built-in guardrails
        # LlamaStack will automatically orchestrate all tool calls AND apply safety guardrails!
        async with httpx.AsyncClient(timeout=180.0) as client:
            logger.info("Calling LlamaStack Responses API with guardrails for intelligent orchestration...")

            response = await client.post(
                f"{LLAMASTACK_ENDPOINT}/responses",
                json={
                    "model": "llama-3.1",  # Or whatever model is configured
                    "messages": [
                        {"role": "system", "content": CLAIM_PROCESSING_AGENT_PROMPT},
                        {"role": "user", "content": user_message}
                    ],
                    "tools": tools,
                    "tool_choice": "auto",  # LlamaStack decides
                    "temperature": 0.3,
                    "max_tokens": 4000,
                    # Enable Red Hat OpenShift AI 3.0 Guardrails (Llama Guard + Prompt Guard)
                    # Reference: https://developers.redhat.com/articles/2025/08/26/implement-ai-safeguards-python-and-llama-stack
                    "shields": [
                        "llama_guard",      # Llama Guard: 13 safety categories (S1-S13)
                        "prompt_guard"      # Prompt Guard: Jailbreak/injection protection
                    ],
                    # Apply shields to both input and output
                    "shield_types": ["input_shield", "output_shield"]
                }
            )

            if response.status_code != 200:
                logger.error(f"LlamaStack Responses API failed: {response.status_code} - {response.text}")
                raise HTTPException(
                    status_code=500,
                    detail=f"LlamaStack orchestration failed: {response.text}"
                )

            result = response.json()

            # Process the response
            # LlamaStack Responses API returns all tool calls that were made
            final_decision = None
            tool_calls_made = result.get("tool_calls", [])

            logger.info(f"LlamaStack made {len(tool_calls_made)} tool calls")

            # Execute each tool call and log
            for idx, tool_call_info in enumerate(tool_calls_made):
                tool_name = tool_call_info.get("function", {}).get("name")
                tool_args = tool_call_info.get("function", {}).get("arguments", {})

                if isinstance(tool_args, str):
                    tool_args = json.loads(tool_args)

                logger.info(f"Tool call {idx+1}: {tool_name} with args: {tool_args}")

                # Execute the tool
                step_start = datetime.now()
                tool_result = await execute_tool(tool_name, tool_args, state)
                step_duration = int((datetime.now() - step_start).total_seconds() * 1000)

                # Log the step
                processing_steps.append({
                    "step_name": tool_name,
                    "agent_name": f"{tool_name.replace('_', '-')}-agent",
                    "status": "completed" if tool_result else "failed",
                    "duration_ms": step_duration,
                    "output_data": tool_result or {},
                    "started_at": step_start.isoformat(),
                    "completed_at": datetime.now().isoformat()
                })

                # Check if this was the final decision
                if tool_name == "make_final_decision":
                    final_decision = tool_result

            # If no final decision was made, check the assistant's final message
            if not final_decision:
                assistant_content = result.get("choices", [{}])[0].get("message", {}).get("content", "")
                logger.warning(f"No final decision tool call. Assistant said: {assistant_content}")
                warnings.append("LlamaStack did not call make_final_decision tool")

                # Fallback decision
                final_decision = {
                    "recommendation": "manual_review",
                    "confidence": 0.0,
                    "reasoning": f"LlamaStack orchestration incomplete: {assistant_content}",
                    "relevant_policies": []
                }

    except Exception as e:
        logger.error(f"Error in LlamaStack orchestration: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

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
    """
    Execute a tool called by LlamaStack.

    This is our implementation that actually calls the MCP servers.
    """

    try:
        if tool_name == "ocr_document":
            return await call_mcp_server(
                OCR_SERVER_URL,
                "ocr_document",
                {
                    "document_path": arguments.get("document_path", state["document_path"]),
                    "document_type": "claim_form",
                    "language": "eng"
                },
                timeout=60
            )

        elif tool_name == "retrieve_user_info":
            return await call_mcp_server(
                RAG_SERVER_URL,
                "retrieve_user_info",
                {
                    "user_id": arguments.get("user_id", state["user_id"]),
                    "query": arguments.get("query", "active insurance contracts"),
                    "top_k": 5,
                    "include_contracts": True
                },
                timeout=60
            )

        elif tool_name == "retrieve_similar_claims":
            return await call_mcp_server(
                RAG_SERVER_URL,
                "retrieve_similar_claims",
                {
                    "claim_text": arguments.get("claim_text", "")[:1000],
                    "top_k": arguments.get("top_k", 5),
                    "min_similarity": 0.7
                },
                timeout=60
            )

        elif tool_name == "make_final_decision":
            # LlamaStack has already made the decision and called this tool
            # Just return what it decided
            return {
                "recommendation": arguments.get("decision", "manual_review"),
                "confidence": arguments.get("confidence", 0.5),
                "reasoning": arguments.get("reasoning", ""),
                "relevant_policies": arguments.get("relevant_policies", [])
            }

        else:
            logger.error(f"Unknown tool: {tool_name}")
            return None

    except Exception as e:
        logger.error(f"Error executing tool {tool_name}: {str(e)}")
        return None
