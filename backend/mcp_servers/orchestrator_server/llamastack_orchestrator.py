"""
Intelligent Orchestrator using LlamaStack Agent Runtime.

LlamaStack manages the agent loop and decides which tools to call.
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
LLM_ENDPOINT = os.getenv("LLM_ENDPOINT", "https://mistral-3-14b-instruct-edg-demo.apps.cluster-rk6mx.rk6mx.sandbox492.opentlc.com/v1/chat/completions")
LLM_MODEL_NAME = os.getenv("LLM_MODEL_NAME", "mistral-3-14b-instruct")


# System prompt for the intelligent orchestrator
AGENT_SYSTEM_PROMPT = """Tu es un orchestrateur intelligent pour le traitement de claims d'assurance.

## Agents/Tools Disponibles:

### 1. ocr_document
Extrait le texte d'un document PDF de claim.
**Utilise quand**: Le document n'a pas encore été traité par OCR
**Input**: {"document_path": "string"}
**Output**: {"raw_text": "string", "structured_data": {...}}

### 2. check_guardrails
Vérifie les données sensibles et PII dans le texte.
**Utilise quand**: Après OCR, avant tout traitement impliquant données sensibles
**Input**: {"text": "string", "structured_data": {...}}
**Output**: {"has_pii": bool, "sensitive_data_detected": [...], "cleared": bool}

### 3. retrieve_user_info
Récupère les contrats et l'historique de l'utilisateur.
**Utilise quand**: Besoin de contexte utilisateur pour décision
**Input**: {"user_id": "string", "query": "string"}
**Output**: {"user_info": {...}, "contracts": [...]}

### 4. retrieve_similar_claims
Trouve des claims similaires dans l'historique.
**Utilise quand**: Besoin de précédents pour la décision
**Input**: {"claim_text": "string", "top_k": int}
**Output**: {"similar_claims": [...]}

### 5. make_final_decision
Prend la décision finale sur le claim (approve/deny/manual_review).
**Utilise quand**: Toutes les données nécessaires ont été collectées
**Input**: {"claim_id": "string", "user_id": "string", "ocr_data": {...}, "rag_data": {...}}
**Output**: {"decision": "string", "confidence": float, "reasoning": "string"}

## Workflow Recommandé:

### Claim Simple (montant < $5000):
1. ocr_document
2. check_guardrails
3. retrieve_user_info
4. make_final_decision

### Claim Complexe (montant >= $5000 ou nouveau user):
1. ocr_document
2. check_guardrails
3. retrieve_user_info
4. retrieve_similar_claims
5. make_final_decision

## Règles Importantes:
- TOUJOURS commencer par ocr_document
- TOUJOURS appeler check_guardrails après OCR
- Si guardrails détecte PII non masqué → STOP et recommande manual_review
- retrieve_user_info est REQUIS avant make_final_decision
- retrieve_similar_claims est OPTIONNEL (uniquement si montant élevé ou cas complexe)
- Ne PAS répéter un tool déjà appelé avec succès

## Instructions:
Analyse le claim étape par étape. Pour chaque étape:
1. Regarde quels tools ont déjà été appelés
2. Décide du prochain tool approprié
3. Appelle le tool avec les bons paramètres
4. Continue jusqu'à avoir assez d'informations pour make_final_decision

Sois efficace: n'appelle que les tools nécessaires pour ce claim spécifique.
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
            return response.json()
    except Exception as e:
        logger.error(f"Error calling {server_url}/{endpoint}: {str(e)}")
        return None


async def intelligent_orchestrate_claim(
    claim_id: str,
    document_path: str,
    user_id: str,
    claim_type: str
) -> Dict[str, Any]:
    """
    Intelligent orchestration using LlamaStack Agent Runtime.

    The LLM decides which tools to call and in what order.
    """

    start_time = datetime.now()
    processing_steps = []
    warnings = []

    # State tracking
    state = {
        "claim_id": claim_id,
        "document_path": document_path,
        "user_id": user_id,
        "claim_type": claim_type,
        "completed_tools": [],
        "collected_data": {}
    }

    # Tool definitions for LlamaStack
    tools = [
        {
            "type": "function",
            "function": {
                "name": "ocr_document",
                "description": "Extract text from a claim PDF document using OCR",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "document_path": {
                            "type": "string",
                            "description": "Path to the PDF document"
                        }
                    },
                    "required": ["document_path"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "check_guardrails",
                "description": "Check for sensitive data and PII in extracted text",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "text": {
                            "type": "string",
                            "description": "Text to check for sensitive data"
                        },
                        "structured_data": {
                            "type": "object",
                            "description": "Structured data extracted from OCR"
                        }
                    },
                    "required": ["text"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "retrieve_user_info",
                "description": "Retrieve user contracts and information from vector database",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "user_id": {
                            "type": "string",
                            "description": "User ID to retrieve information for"
                        },
                        "query": {
                            "type": "string",
                            "description": "Query for retrieving relevant information"
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
                "description": "Find similar historical claims for context",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "claim_text": {
                            "type": "string",
                            "description": "Claim text to find similar claims for"
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
                "description": "Make final decision on the claim (approve/deny/manual_review)",
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
                        "summary": {
                            "type": "string",
                            "description": "Summary of all gathered information"
                        }
                    },
                    "required": ["claim_id", "user_id", "summary"]
                }
            }
        }
    ]

    # Prepare initial context message
    initial_context = f"""Nouveau claim à traiter:
- Claim ID: {claim_id}
- Type: {claim_type}
- User ID: {user_id}
- Document: {document_path}

Commence le traitement en appelant les tools appropriés.
"""

    # Messages for LLM conversation
    messages = [
        {"role": "system", "content": AGENT_SYSTEM_PROMPT},
        {"role": "user", "content": initial_context}
    ]

    max_iterations = 10
    iteration = 0
    final_decision = None

    while iteration < max_iterations:
        iteration += 1
        logger.info(f"Iteration {iteration}: Asking LLM for next tool...")

        try:
            # Call LLM with tools
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
                    logger.error(f"LLM request failed: {response.status_code} - {response.text}")
                    break

                result = response.json()
                assistant_message = result["choices"][0]["message"]

                # Add assistant message to conversation
                messages.append(assistant_message)

                # Check if LLM wants to call a tool
                if assistant_message.get("tool_calls"):
                    tool_call = assistant_message["tool_calls"][0]
                    tool_name = tool_call["function"]["name"]
                    tool_args = json.loads(tool_call["function"]["arguments"])

                    logger.info(f"LLM chose to call: {tool_name} with args: {tool_args}")

                    # Execute the tool
                    step_start = datetime.now()
                    tool_result = await execute_tool(tool_name, tool_args, state)
                    step_duration = int((datetime.now() - step_start).total_seconds() * 1000)

                    # Track execution
                    state["completed_tools"].append(tool_name)
                    state["collected_data"][tool_name] = tool_result

                    processing_steps.append({
                        "step_name": tool_name,
                        "agent_name": f"{tool_name}-agent",
                        "status": "completed" if tool_result else "failed",
                        "duration_ms": step_duration,
                        "output_data": tool_result or {},
                        "started_at": step_start.isoformat(),
                        "completed_at": datetime.now().isoformat()
                    })

                    # Add tool result to conversation
                    tool_message = {
                        "role": "tool",
                        "tool_call_id": tool_call["id"],
                        "content": json.dumps(tool_result) if tool_result else "Tool execution failed"
                    }
                    messages.append(tool_message)

                    # Check if this was the final decision
                    if tool_name == "make_final_decision" and tool_result:
                        final_decision = tool_result
                        logger.info("Final decision made, terminating loop")
                        break

                else:
                    # No tool call - LLM finished or error
                    content = assistant_message.get("content", "")
                    logger.info(f"LLM response (no tool call): {content}")

                    # Check if we have a decision
                    if final_decision:
                        break
                    else:
                        # LLM might be asking a question or finished
                        warnings.append("LLM did not call expected tools")
                        break

        except Exception as e:
            logger.error(f"Error in iteration {iteration}: {str(e)}")
            warnings.append(f"Iteration {iteration} failed: {str(e)}")
            break

    total_duration = int((datetime.now() - start_time).total_seconds() * 1000)

    return {
        "claim_id": claim_id,
        "status": "completed" if final_decision else "failed",
        "processing_steps": processing_steps,
        "final_decision": final_decision,
        "total_processing_time_ms": total_duration,
        "iterations": iteration,
        "warnings": warnings
    }


async def execute_tool(
    tool_name: str,
    arguments: Dict[str, Any],
    state: Dict[str, Any]
) -> Optional[Dict[str, Any]]:
    """Execute a tool based on its name."""

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

        elif tool_name == "check_guardrails":
            return await call_mcp_server(
                GUARDRAILS_SERVER_URL,
                "check_sensitive_data",
                {
                    "text": arguments.get("text", ""),
                    "structured_data": arguments.get("structured_data", {})
                },
                timeout=30
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
            # Use LLM to make decision based on all gathered data
            summary = arguments.get("summary", "")
            ocr_data = state["collected_data"].get("ocr_document", {})
            rag_data = state["collected_data"].get("retrieve_user_info", {})

            decision_prompt = f"""Basé sur les informations suivantes, prends une décision finale sur le claim:

Claim ID: {state['claim_id']}
User ID: {state['user_id']}
Type: {state['claim_type']}

{summary}

Données OCR: {json.dumps(ocr_data.get('structured_data', {}), indent=2) if ocr_data else 'Non disponible'}

Contrats utilisateur: {len(rag_data.get('contracts', []))} contrats actifs

Réponds UNIQUEMENT avec un JSON dans ce format:
{{
  "decision": "approve" | "deny" | "manual_review",
  "confidence": 0.0-1.0,
  "reasoning": "Explication détaillée de la décision",
  "relevant_policies": ["policy1", "policy2"]
}}
"""

            async with httpx.AsyncClient(timeout=90.0) as client:
                response = await client.post(
                    LLM_ENDPOINT,
                    json={
                        "model": LLM_MODEL_NAME,
                        "messages": [
                            {"role": "system", "content": "Tu es un expert en décision de claims d'assurance. Réponds UNIQUEMENT en JSON valide."},
                            {"role": "user", "content": decision_prompt}
                        ],
                        "temperature": 0.3,
                        "max_tokens": 1024,
                    }
                )

                if response.status_code == 200:
                    result = response.json()
                    generated_text = result["choices"][0]["message"]["content"]

                    # Extract JSON
                    if "```json" in generated_text:
                        json_start = generated_text.find("```json") + 7
                        json_end = generated_text.find("```", json_start)
                        generated_text = generated_text[json_start:json_end].strip()

                    decision_data = json.loads(generated_text)
                    return {
                        "recommendation": decision_data.get("decision", "manual_review"),
                        "confidence": decision_data.get("confidence", 0.5),
                        "reasoning": decision_data.get("reasoning", ""),
                        "relevant_policies": decision_data.get("relevant_policies", [])
                    }
                else:
                    logger.error(f"Decision LLM failed: {response.status_code}")
                    return {
                        "recommendation": "manual_review",
                        "confidence": 0.0,
                        "reasoning": "LLM decision failed",
                        "relevant_policies": []
                    }

        else:
            logger.error(f"Unknown tool: {tool_name}")
            return None

    except Exception as e:
        logger.error(f"Error executing tool {tool_name}: {str(e)}")
        return None
