"""
Claim Service - Business logic for claims processing.

Uses agent services for AI orchestration while keeping
business logic separate and testable.
"""
import logging
from typing import Dict, Any, Optional
from datetime import datetime, timezone
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from fastapi import HTTPException

from app.models import claim as models
from app.core.config import settings
from app.llamastack.prompts import (
    CLAIMS_PROCESSING_AGENT_INSTRUCTIONS,
    USER_MESSAGE_FULL_WORKFLOW_TEMPLATE
)
from .agent.responses_orchestrator import ResponsesOrchestrator
from .agent.context_builder import ContextBuilder
from .agent.response_parser import ResponseParser

logger = logging.getLogger(__name__)


class ClaimService:
    """Service for claim processing business logic."""

    def __init__(
        self,
        orchestrator: Optional[ResponsesOrchestrator] = None,
        context_builder: Optional[ContextBuilder] = None,
        response_parser: Optional[ResponseParser] = None
    ):
        """
        Initialize claim service.

        Args:
            orchestrator: Responses orchestrator
            context_builder: Context builder
            response_parser: Response parser
        """
        self.orchestrator = orchestrator or ResponsesOrchestrator()
        self.context_builder = context_builder or ContextBuilder()
        self.response_parser = response_parser or ResponseParser()

    async def get_claim_by_id(
        self,
        db: AsyncSession,
        claim_id: str
    ) -> Optional[models.Claim]:
        """
        Get claim by ID.

        Args:
            db: Database session
            claim_id: Claim identifier

        Returns:
            Claim model or None
        """
        result = await db.execute(
            select(models.Claim).where(models.Claim.id == claim_id)
        )
        return result.scalar_one_or_none()

    async def build_claim_context(
        self,
        db: AsyncSession,
        claim: models.Claim
    ) -> Dict[str, Any]:
        """
        Build complete context for claim processing.

        Args:
            db: Database session
            claim: Claim model

        Returns:
            Complete claim context with OCR and RAG data
        """
        context = {
            "entity_type": "claim",
            "entity_id": str(claim.id),
            "entity_data": {
                "claim_number": claim.claim_number,
                "user_id": claim.user_id,
                "claim_type": claim.claim_type,
                "document_path": claim.document_path,
                "status": claim.status.value,
                "submitted_at": claim.submitted_at.isoformat() if claim.submitted_at else None
            }
        }

        # Add OCR data if available
        ocr_result = await db.execute(
            select(models.ClaimDocument)
            .where(models.ClaimDocument.claim_id == claim.id)
            .order_by(models.ClaimDocument.created_at.desc())
            .limit(1)
        )
        claim_doc = ocr_result.scalar_one_or_none()

        if claim_doc:
            ocr_context = self.context_builder.extract_ocr_context({
                "raw_ocr_text": claim_doc.raw_ocr_text,
                "structured_data": claim_doc.structured_data
            })
            context["additional_context"] = {"OCR Data": ocr_context}

        return context

    async def process_claim_with_agent(
        self,
        db: AsyncSession,
        claim_id: str,
        agent_config: Dict[str, Any],
        tools: Optional[list] = None
    ) -> Dict[str, Any]:
        """
        Process claim using an agent.

        Args:
            db: Database session
            claim_id: Claim identifier
            agent_config: Agent configuration
            tools: Optional list of tools to enable

        Returns:
            Processing result with decision

        Raises:
            ValueError: If claim not found
            Exception: If processing fails
        """
        # Get claim
        claim = await self.get_claim_by_id(db, claim_id)
        if not claim:
            raise ValueError(f"Claim {claim_id} not found")

        # Update status
        claim.status = models.ClaimStatus.processing
        await db.commit()

        try:
            # Build context
            context = await self.build_claim_context(db, claim)

            # Build processing message
            context_str = self.context_builder.build_processing_context(
                entity_type="claim",
                entity_id=str(claim_id),
                entity_data=context["entity_data"],
                additional_context=context.get("additional_context")
            )

            processing_message = f"{USER_MESSAGE_FULL_WORKFLOW_TEMPLATE}\n\n{context_str}"

            # Process with Responses API (automatic tool execution)
            result = await self.orchestrator.process_with_agent(
                agent_config=agent_config,
                input_message=processing_message,
                tools=tools,
                session_name=f"claim_{claim.claim_number}_{datetime.now().isoformat()}"
            )

            # Parse decision
            response_content = result.get('output', '')
            decision_data = self.response_parser.parse_decision(response_content)

            # Extract processing steps from tool_calls
            tool_calls = result.get('tool_calls', [])
            processing_steps = []

            for tc in tool_calls:
                tool_name = tc.get('name', 'unknown')

                # Map tool to agent name
                if 'ocr' in tool_name.lower():
                    agent_name = 'ocr-agent'
                elif tool_name in ['retrieve_user_info', 'retrieve_similar_claims', 'search_knowledge_base']:
                    agent_name = 'rag-agent'
                else:
                    agent_name = 'unknown'

                # Parse output and extract timing
                output_data = None
                duration_ms = None

                if tc.get('output'):
                    try:
                        import json as json_lib
                        output_data = json_lib.loads(tc['output'])

                        # Extract processing time if available in tool output
                        if isinstance(output_data, dict) and 'processing_time_seconds' in output_data:
                            duration_ms = int(output_data['processing_time_seconds'] * 1000)
                    except:
                        output_data = {'raw_text': tc['output']}

                processing_steps.append({
                    'step_name': tool_name,
                    'agent_name': agent_name,
                    'status': 'failed' if tc.get('error') else 'completed',
                    'output_data': output_data,
                    'error_message': tc.get('error'),
                    'duration_ms': duration_ms
                })

            # Update claim status based on decision
            recommendation = decision_data.get('recommendation', 'manual_review')
            if recommendation == 'approve':
                claim.status = models.ClaimStatus.completed
            elif recommendation == 'deny':
                claim.status = models.ClaimStatus.failed
            else:
                claim.status = models.ClaimStatus.manual_review

            # Calculate processing time from sum of step durations
            claim.processed_at = datetime.now(timezone.utc)

            # Sum all step durations to get accurate total processing time
            total_duration_ms = sum(
                step.get('duration_ms', 0) for step in processing_steps if step.get('duration_ms')
            )
            claim.total_processing_time_ms = total_duration_ms if total_duration_ms > 0 else None

            # Save processing metadata
            if not claim.claim_metadata:
                claim.claim_metadata = {}
            claim.claim_metadata['response_id'] = result.get('response_id')
            claim.claim_metadata['processing_steps'] = processing_steps
            claim.claim_metadata['usage'] = result.get('usage', {})

            await db.commit()

            return {
                "response_id": result.get("response_id"),
                "decision": decision_data,
                "claim_status": claim.status.value,
                "processing_steps": processing_steps,
                "tool_calls": tool_calls,  # Include tool_calls for PII detection
                "usage": result.get("usage", {})
            }

        except Exception as e:
            logger.error(f"Error processing claim {claim_id}: {e}", exc_info=True)
            claim.status = models.ClaimStatus.failed
            await db.commit()
            raise

    async def save_decision(
        self,
        db: AsyncSession,
        claim_id: str,
        decision_data: Dict[str, Any]
    ) -> models.ClaimDecision:
        """
        Save claim decision to database.

        Args:
            db: Database session
            claim_id: Claim identifier
            decision_data: Decision data from agent

        Returns:
            Created ClaimDecision model
        """
        recommendation = decision_data.get('recommendation', 'manual_review')

        decision = models.ClaimDecision(
            claim_id=claim_id,
            # Initial system decision
            initial_decision=recommendation,
            initial_confidence=decision_data.get('confidence', 0.0),
            initial_reasoning=decision_data.get('reasoning', ''),
            initial_decided_at=datetime.now(timezone.utc),
            # Legacy fields
            decision=recommendation,
            confidence=decision_data.get('confidence', 0.0),
            reasoning=decision_data.get('reasoning', ''),
            # Evidence
            relevant_policies=decision_data.get('evidence', {}),
            llm_model=settings.llamastack_default_model,
            requires_manual_review=(recommendation == 'manual_review')
        )

        db.add(decision)
        await db.commit()
        await db.refresh(decision)

        logger.info(f"Decision saved for claim {claim_id}: {recommendation}")

        return decision

    async def check_pii_shield(
        self,
        text: str,
        claim_id: str
    ) -> Dict[str, Any]:
        """
        Check text for PII using LlamaStack shield.
        
        Args:
            text: Text to check for PII
            claim_id: Claim ID for logging
            
        Returns:
            Dict with detection results
        """
        if not settings.enable_pii_detection:
            return {"violations_found": False, "detections": []}
            
        try:
            import httpx
            
            # Call LlamaStack shield API
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{settings.llamastack_endpoint}/v1/safety/run-shield",
                    json={
                        "shield_id": settings.pii_shield_id,
                        "messages": [{"content": text, "role": "user"}]
                    },
                    timeout=30.0
                )
                
                if response.status_code != 200:
                    logger.warning(f"Shield API returned {response.status_code}: {response.text}")
                    return {"violations_found": False, "detections": []}
                
                result = response.json()
                violation_data = result.get("violation", {})
                metadata = violation_data.get("metadata", {})
                status = metadata.get("status", "pass")
                
                if status == "violation":
                    detections = metadata.get("results", [])
                    logger.info(f"PII detected in claim {claim_id}: {len(detections)} violations")
                    return {
                        "violations_found": True,
                        "detections": detections,
                        "summary": metadata.get("summary", {})
                    }
                    
        except Exception as e:
            logger.error(f"Error checking PII shield: {e}", exc_info=True)
            
        return {"violations_found": False, "detections": []}

    async def save_pii_detections(
        self,
        db: AsyncSession,
        claim_id: str,
        detections: list
    ) -> None:
        """
        Save PII detections to database.
        
        Args:
            db: Database session
            claim_id: Claim ID
            detections: List of detection results from shield
        """
        for detection in detections:
            detection_entry = models.GuardrailsDetection(
                claim_id=UUID(claim_id),
                detection_type="pii",
                severity="medium",
                action_taken="logged",
                detected_at=datetime.now(timezone.utc),
                record_metadata={
                    "text": detection.get("text", ""),
                    "detection_type": detection.get("detection_type", ""),
                    "score": detection.get("score", 0.0),
                    "detector_results": detection.get("individual_detector_results", []),
                    "source_step": detection.get("source_step", "unknown"),
                    "detected_fields": detection.get("detected_fields", [])
                }
            )
            db.add(detection_entry)
        
        await db.commit()
        logger.info(f"Saved {len(detections)} PII detections for claim {claim_id}")
