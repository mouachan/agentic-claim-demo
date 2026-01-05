"""
BACKUP: Version originale avec ReActAgent SDK

⚠️ IMPORTANT: Cette version causait des OOM (Exit Code 137) à cause de EventLogger().log(response)
même avec 8GB de RAM. Elle a été remplacée par des appels HTTP directs.

📝 À RETESTER après mise à jour de llama-stack-client qui fixe le memory leak dans EventLogger

Différences clés entre SDK et HTTP direct:
1. SDK: Utilise ReActAgent avec session streaming
2. HTTP: Appels directs à /v1/conversations + /v1/responses
3. SDK: EventLogger consomme énormément de mémoire
4. HTTP: Mémoire stable, pas de leak

Performance:
- SDK: OOM crash après ~10s de processing
- HTTP: Complet en 3-4s sans crash

Quand retester:
- Après llama-stack-client >= 0.4.0 (si le fix est inclus)
- Vérifier les release notes pour "EventLogger memory fix"
"""

import logging
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import schemas
from app.core.config import settings
from app.core.database import get_db
from app.models import claim as models

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/{claim_id}/process", response_model=schemas.ProcessClaimResponse)
async def process_claim_with_reactagent_sdk(
    claim_id: UUID,
    process_request: schemas.ProcessClaimRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    BACKUP VERSION: Process claim using ReActAgent SDK (CAUSES OOM!)

    Cette version utilise le SDK llama-stack-client avec:
    - LlamaStackClient
    - Agent.create() avec AgentConfig
    - EventLogger pour logger les events

    PROBLÈME: EventLogger().log(response) cause un memory leak massif
    Même avec 8GB RAM, le pod crash avec Exit Code 137 (OOM)

    SOLUTION TEMPORAIRE: Utiliser process_claim() avec appels HTTP directs

    À RETESTER QUAND:
    - llama-stack-client est mis à jour avec fix du memory leak
    - Vérifier: pip show llama-stack-client (version actuelle: 0.3.0rc3)
    """
    import time
    import json
    import llama_stack_client
    from llama_stack_client import LlamaStackClient
    from llama_stack_client.lib.agents.agent import Agent
    from llama_stack_client.lib.agents.event_logger import EventLogger
    from llama_stack_client.types.agent_create_params import AgentConfig
    from app.llamastack.prompts import CLAIMS_PROCESSING_AGENT_INSTRUCTIONS

    try:
        # Get the claim
        query = select(models.Claim).where(models.Claim.id == claim_id)
        result = await db.execute(query)
        claim = result.scalar_one_or_none()

        if not claim:
            raise HTTPException(status_code=404, detail="Claim not found")

        # Update status to processing
        claim.status = models.ClaimStatus.processing
        await db.commit()

        # Track processing start time
        start_time = time.time()

        try:
            # Initialize LlamaStack client
            client = LlamaStackClient(base_url=settings.llamastack_endpoint)

            # Build MCP tools list
            # Format correct découvert en examinant llama-stack-client source:
            # {"type": "mcp", "server_label": "...", "server_url": "..."}
            mcp_tools = []
            if not process_request.skip_ocr:
                mcp_tools.append({
                    "type": "mcp",
                    "server_label": "ocr-server",
                    "server_url": "http://ocr-server.claims-demo.svc.cluster.local:8080/sse"
                })
            if process_request.enable_rag:
                mcp_tools.append({
                    "type": "mcp",
                    "server_label": "rag-server",
                    "server_url": "http://rag-server.claims-demo.svc.cluster.local:8080/sse"
                })

            # Create Agent with configuration
            agent = Agent(
                client=client,
                agent_config=AgentConfig(
                    model=settings.llamastack_default_model,
                    instructions=CLAIMS_PROCESSING_AGENT_INSTRUCTIONS,
                    enable_session_persistence=False,
                    tools=mcp_tools,
                    tool_choice="auto",
                    tool_prompt_format="json",  # ou "function_tag"
                    max_infer_iters=10,
                )
            )

            # Create session
            session_id = agent.create_session(session_name=f"claim_{claim_id}")
            logger.info(f"Created ReActAgent session: {session_id}")

            # Prepare user message
            user_message = f"""
Process this insurance claim:

Claim ID: {claim_id}
User ID: {claim.user_id}
Document Path: {claim.document_path}
Claim Type: {claim.claim_type if hasattr(claim, 'claim_type') else 'general'}

Please:
1. Extract all information from the document using OCR
2. Retrieve the user's insurance contracts and coverage details
3. Find similar historical claims for precedent
4. Determine if the claim should be approved, denied, or requires manual review
5. Provide detailed reasoning citing relevant policy sections

Workflow configuration:
- Skip OCR: {process_request.skip_ocr}
- Enable RAG retrieval: {process_request.enable_rag}
"""

            # Execute agent (streaming mode)
            logger.info("Starting ReActAgent execution...")

            # ⚠️ PROBLÈME ICI: EventLogger().log() cause OOM
            # Même si on ne log pas, la réponse peut être trop grosse en mémoire
            response = agent.create_turn(
                messages=[
                    {"role": "user", "content": user_message}
                ],
                session_id=session_id,
                stream=True  # ou False, les deux causent des problèmes
            )

            # Collect all events
            # ⚠️ CRASH ICI AVEC OOM!
            event_logger = EventLogger()
            for chunk in response:
                # EventLogger.log() consomme énormément de mémoire
                event_logger.log(chunk)

            # Get final response
            final_response = event_logger.get_response()

            if not final_response:
                raise ValueError("Agent did not provide a final response")

            # Parse the agent's decision
            try:
                decision_data = json.loads(final_response) if "{" in final_response else {
                    "recommendation": "manual_review",
                    "confidence": 0.5,
                    "reasoning": final_response
                }
            except json.JSONDecodeError:
                logger.warning("Could not parse agent response as JSON")
                decision_data = {
                    "recommendation": "manual_review",
                    "confidence": 0.5,
                    "reasoning": final_response
                }

            # Calculate processing time
            processing_time_ms = int((time.time() - start_time) * 1000)

            # Update claim based on recommendation
            recommendation = decision_data.get("recommendation", "manual_review")
            if recommendation == "approve":
                claim.status = models.ClaimStatus.completed
            elif recommendation == "deny":
                claim.status = models.ClaimStatus.failed
            else:  # manual_review
                claim.status = models.ClaimStatus.manual_review

            claim.total_processing_time_ms = processing_time_ms

            # Create decision record
            decision = models.ClaimDecision(
                claim_id=claim_id,
                decision=recommendation,
                confidence=decision_data.get("confidence", 0.0),
                reasoning=decision_data.get("reasoning", ""),
                relevant_policies={
                    "policies": decision_data.get("relevant_policies", []),
                    "estimated_coverage": decision_data.get("estimated_coverage_amount")
                },
                llm_model=settings.llamastack_default_model,
                requires_manual_review=(recommendation == "manual_review")
            )
            db.add(decision)

            await db.commit()

            logger.info(f"Claim {claim_id} processed via ReActAgent SDK: {recommendation}")
            return schemas.ProcessClaimResponse(
                claim_id=claim_id,
                status=claim.status.value,
                message=f"Processing completed: {recommendation}",
                processing_started_at=claim.submitted_at
            )

        except llama_stack_client.APIConnectionError as e:
            claim.status = models.ClaimStatus.failed
            await db.commit()
            logger.error(f"LlamaStack connection error: {str(e)}")
            raise HTTPException(
                status_code=503,
                detail=f"Cannot connect to LlamaStack server: {str(e)}"
            )
        except llama_stack_client.APIStatusError as e:
            claim.status = models.ClaimStatus.failed
            await db.commit()
            logger.error(f"LlamaStack API error: {e.status_code} - {str(e)}")
            raise HTTPException(
                status_code=503,
                detail=f"LlamaStack API error: {str(e)}"
            )
        except llama_stack_client.APIError as e:
            claim.status = models.ClaimStatus.failed
            await db.commit()
            logger.error(f"LlamaStack error: {str(e)}")
            raise HTTPException(
                status_code=503,
                detail=f"Agent processing failed: {str(e)}"
            )

    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error processing claim with SDK: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# NOTES SUR LES DIFFÉRENCES SDK vs HTTP
# ============================================================================

"""
1. IMPORTS SDK (à garder):
   from llama_stack_client import LlamaStackClient
   from llama_stack_client.lib.agents.agent import Agent
   from llama_stack_client.lib.agents.event_logger import EventLogger
   from llama_stack_client.types.agent_create_params import AgentConfig

2. FORMAT MCP TOOLS (identique pour SDK et HTTP):
   {
       "type": "mcp",
       "server_label": "ocr-server",
       "server_url": "http://ocr-server.claims-demo.svc.cluster.local:8080/sse"
   }

3. CRÉATION AGENT (SDK uniquement):
   agent = Agent(
       client=client,
       agent_config=AgentConfig(
           model="llama-instruct-32-3b",
           instructions="...",
           tools=mcp_tools,
           tool_choice="auto",
           max_infer_iters=10
       )
   )

4. STREAMING (SDK):
   response = agent.create_turn(messages=[...], session_id=session_id, stream=True)

   # Problème: EventLogger consomme trop de mémoire
   event_logger = EventLogger()
   for chunk in response:
       event_logger.log(chunk)  # ❌ CRASH OOM ICI

   final_response = event_logger.get_response()

5. HTTP DIRECT (version actuelle, stable):
   # Create conversation
   conv_response = await http_client.post(
       f"{settings.llamastack_endpoint}/v1/conversations",
       json={"name": f"claim_{claim_id}"}
   )
   conversation_id = conv_response.json()["conversation_id"]

   # Get response
   agent_response = await http_client.post(
       f"{settings.llamastack_endpoint}/v1/responses",
       json={
           "model": "llama-instruct-32-3b",
           "conversation_id": conversation_id,
           "messages": [...],
           "tools": mcp_tools,
           "stream": False
       }
   )

   response_data = agent_response.json()
   final_response = response_data["choices"][0]["message"]["content"]

6. AVANTAGES SDK:
   - Code plus propre et pythonic
   - Gestion automatique des sessions
   - Type hints complets
   - EventLogger pour debug (quand il ne leak pas)

7. AVANTAGES HTTP:
   - Pas de memory leak
   - Contrôle complet sur la requête
   - Plus facile à debug (voir requête/réponse brute)
   - Fonctionne avec n'importe quelle version de LlamaStack

8. QUAND REVENIR AU SDK:
   - Vérifier llama-stack-client release notes
   - Chercher: "EventLogger", "memory leak", "OOM"
   - Tester avec petit claim d'abord
   - Monitorer mémoire: `oc adm top pod -n claims-demo`
   - Si stable après 10 tests, migrer complètement

9. COMMAND POUR TESTER:
   # Dans le code, remplacer process_claim par process_claim_with_reactagent_sdk
   # Puis rebuild backend et watch memory:
   oc adm top pod -n claims-demo -l app=backend --watch

   # Si memory monte au-delà de 6GB → encore un problème
   # Si memory reste stable ~2-3GB → SDK est fixé!
"""
