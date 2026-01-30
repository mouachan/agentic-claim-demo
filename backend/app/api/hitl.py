"""
Human-in-the-Loop (HITL) WebSocket API for real-time claim review.

WebSocket endpoints:
- /ws/review/{claim_id}  - Join a review room for a specific claim

REST endpoints:
- POST /{claim_id}/action     - Submit a review decision (approve/reject/comment)
- POST /{claim_id}/ask-agent  - Ask agent a question (conversational HITL)
- GET  /{claim_id}/messages   - Get review chat history
- GET  /active                - Get list of active review sessions
"""

import json
import logging
from datetime import datetime, timezone
from typing import Dict, Set
from uuid import UUID

import httpx
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.api import schemas
from app.core.config import settings
from app.core.database import get_db
from app.models import claim as models

logger = logging.getLogger(__name__)

router = APIRouter()


# =============================================================================
# WebSocket Connection Manager
# =============================================================================

class ConnectionManager:
    """
    Manages WebSocket connections for HITL review sessions.

    Features:
    - Multiple reviewers can join the same claim room
    - Presence tracking (who's currently reviewing)
    - Broadcast messages to all reviewers in a room
    """

    def __init__(self):
        # claim_id -> Set of WebSocket connections
        self.active_connections: Dict[str, Set[WebSocket]] = {}
        # websocket -> reviewer info
        self.reviewer_info: Dict[WebSocket, dict] = {}

    async def connect(self, websocket: WebSocket, claim_id: str, reviewer_id: str, reviewer_name: str):
        """Add a new reviewer to a claim review room."""
        await websocket.accept()

        if claim_id not in self.active_connections:
            self.active_connections[claim_id] = set()

        self.active_connections[claim_id].add(websocket)
        self.reviewer_info[websocket] = {
            "reviewer_id": reviewer_id,
            "reviewer_name": reviewer_name,
            "claim_id": claim_id,
            "joined_at": datetime.now(timezone.utc).isoformat()
        }

        logger.info(f"Reviewer {reviewer_name} joined claim {claim_id} review room")

        # Notify other reviewers
        await self.broadcast(claim_id, {
            "type": "reviewer_joined",
            "reviewer_id": reviewer_id,
            "reviewer_name": reviewer_name,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }, exclude=websocket)

    def disconnect(self, websocket: WebSocket):
        """Remove a reviewer from their claim review room."""
        if websocket not in self.reviewer_info:
            return

        info = self.reviewer_info[websocket]
        claim_id = info["claim_id"]
        reviewer_name = info["reviewer_name"]

        if claim_id in self.active_connections:
            self.active_connections[claim_id].discard(websocket)

            # Clean up empty rooms
            if len(self.active_connections[claim_id]) == 0:
                del self.active_connections[claim_id]

        del self.reviewer_info[websocket]
        logger.info(f"Reviewer {reviewer_name} left claim {claim_id} review room")

    async def broadcast(self, claim_id: str, message: dict, exclude: WebSocket = None):
        """Send a message to all reviewers in a claim room."""
        if claim_id not in self.active_connections:
            return

        message_json = json.dumps(message)

        # Send to all connections in this claim's room
        dead_connections = set()
        for connection in self.active_connections[claim_id]:
            if connection == exclude:
                continue

            try:
                await connection.send_text(message_json)
            except Exception as e:
                logger.error(f"Failed to send message to reviewer: {e}")
                dead_connections.add(connection)

        # Clean up dead connections
        for connection in dead_connections:
            self.disconnect(connection)

    async def send_personal(self, websocket: WebSocket, message: dict):
        """Send a message to a specific reviewer."""
        try:
            await websocket.send_text(json.dumps(message))
        except Exception as e:
            logger.error(f"Failed to send personal message: {e}")
            self.disconnect(websocket)

    def get_reviewers(self, claim_id: str) -> list:
        """Get list of active reviewers for a claim."""
        if claim_id not in self.active_connections:
            return []

        reviewers = []
        for ws in self.active_connections[claim_id]:
            if ws in self.reviewer_info:
                info = self.reviewer_info[ws]
                reviewers.append({
                    "reviewer_id": info["reviewer_id"],
                    "reviewer_name": info["reviewer_name"],
                    "joined_at": info["joined_at"]
                })

        return reviewers


# Global connection manager
manager = ConnectionManager()


# =============================================================================
# Pydantic Models
# =============================================================================

class ReviewAction(BaseModel):
    """Review action submitted by a reviewer."""
    action: str  # "approve", "reject", "comment", "request_info"
    comment: str = ""
    reviewer_id: str
    reviewer_name: str


class ReviewMessage(BaseModel):
    """Chat message in review session."""
    message: str
    reviewer_id: str
    reviewer_name: str


# =============================================================================
# WebSocket Endpoint
# =============================================================================

@router.websocket("/ws/review/{claim_id}")
async def websocket_review_endpoint(
    websocket: WebSocket,
    claim_id: UUID,
    reviewer_id: str = "agent_001",
    reviewer_name: str = "Agent Smith"
):
    """
    WebSocket endpoint for real-time claim review.

    Query params:
    - reviewer_id: Unique identifier for the reviewer
    - reviewer_name: Display name for the reviewer

    Message types sent by server:
    - reviewer_joined: Another reviewer joined the room
    - reviewer_left: A reviewer left the room
    - chat_message: Someone sent a chat message
    - action_taken: Someone approved/rejected/commented
    - claim_updated: Claim status was updated

    Message types sent by client:
    - chat: Send a chat message
    - action: Submit a review action
    """
    claim_id_str = str(claim_id)

    await manager.connect(websocket, claim_id_str, reviewer_id, reviewer_name)

    try:
        # Send initial state
        reviewers = manager.get_reviewers(claim_id_str)
        await manager.send_personal(websocket, {
            "type": "connected",
            "claim_id": claim_id_str,
            "active_reviewers": reviewers,
            "message": f"Connected to review room for claim {claim_id}"
        })

        # Listen for messages
        while True:
            data = await websocket.receive_text()

            try:
                message = json.loads(data)
                message_type = message.get("type")

                if message_type == "chat":
                    # Broadcast chat message to all reviewers
                    await manager.broadcast(claim_id_str, {
                        "type": "chat_message",
                        "reviewer_id": reviewer_id,
                        "reviewer_name": reviewer_name,
                        "message": message.get("message", ""),
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    })

                elif message_type == "action":
                    # Broadcast action to all reviewers
                    action = message.get("action")
                    comment = message.get("comment", "")

                    await manager.broadcast(claim_id_str, {
                        "type": "action_taken",
                        "reviewer_id": reviewer_id,
                        "reviewer_name": reviewer_name,
                        "action": action,
                        "comment": comment,
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    }, exclude=websocket)

                    # Acknowledge to sender
                    await manager.send_personal(websocket, {
                        "type": "action_acknowledged",
                        "action": action,
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    })

                elif message_type == "ping":
                    # Keepalive
                    await manager.send_personal(websocket, {
                        "type": "pong",
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    })

                else:
                    logger.warning(f"Unknown message type: {message_type}")

            except json.JSONDecodeError:
                logger.error(f"Invalid JSON received: {data}")
                await manager.send_personal(websocket, {
                    "type": "error",
                    "message": "Invalid JSON format"
                })

    except WebSocketDisconnect:
        manager.disconnect(websocket)

        # Notify other reviewers
        await manager.broadcast(claim_id_str, {
            "type": "reviewer_left",
            "reviewer_id": reviewer_id,
            "reviewer_name": reviewer_name,
            "timestamp": datetime.now(timezone.utc).isoformat()
        })

    except Exception as e:
        logger.error(f"WebSocket error: {e}", exc_info=True)
        manager.disconnect(websocket)


# =============================================================================
# REST Endpoints
# =============================================================================

@router.post("/{claim_id}/action")
async def submit_review_action(
    claim_id: UUID,
    action: ReviewAction,
    db: AsyncSession = Depends(get_db)
):
    """
    Submit a review action (approve/reject/comment).

    This endpoint is an alternative to WebSocket for submitting actions.
    It also broadcasts the action via WebSocket to active reviewers.
    """
    # Get claim
    result = await db.execute(
        select(models.Claim).where(models.Claim.id == claim_id)
    )
    claim = result.scalar_one_or_none()

    if not claim:
        raise HTTPException(status_code=404, detail="Claim not found")

    # Get the claim decision to update it
    decision_result = await db.execute(
        select(models.ClaimDecision).where(models.ClaimDecision.claim_id == claim_id)
    )
    claim_decision = decision_result.scalar_one_or_none()

    # Update claim based on action
    timestamp = datetime.now(timezone.utc)

    if action.action == "approve":
        claim.status = "completed"  # Use 'completed' status for approved claims
        claim.updated_at = timestamp

        # Update ClaimDecision with final reviewer decision
        if claim_decision:
            claim_decision.final_decision = "approve"
            claim_decision.final_decision_by = action.reviewer_id
            claim_decision.final_decision_by_name = action.reviewer_name
            claim_decision.final_decision_at = timestamp
            claim_decision.final_decision_notes = action.comment
            claim_decision.updated_at = timestamp

        # Log the approval in agent_logs
        if not claim.agent_logs:
            claim.agent_logs = []
        claim.agent_logs.append({
            "timestamp": timestamp.isoformat(),
            "reviewer_id": action.reviewer_id,
            "reviewer_name": action.reviewer_name,
            "type": "approve",
            "message": action.comment
        })
        flag_modified(claim, "agent_logs")

    elif action.action == "reject":
        claim.status = "failed"  # Use 'failed' status for rejected claims
        claim.updated_at = timestamp

        # Update ClaimDecision with final reviewer decision
        if claim_decision:
            claim_decision.final_decision = "deny"  # Use 'deny' for consistency with DecisionType enum
            claim_decision.final_decision_by = action.reviewer_id
            claim_decision.final_decision_by_name = action.reviewer_name
            claim_decision.final_decision_at = timestamp
            claim_decision.final_decision_notes = action.comment
            claim_decision.updated_at = timestamp

        # Log the rejection in agent_logs
        if not claim.agent_logs:
            claim.agent_logs = []
        claim.agent_logs.append({
            "timestamp": timestamp.isoformat(),
            "reviewer_id": action.reviewer_id,
            "reviewer_name": action.reviewer_name,
            "type": "reject",
            "message": action.comment
        })
        flag_modified(claim, "agent_logs")

    elif action.action == "comment":
        # Add comment to agent_logs
        if not claim.agent_logs:
            claim.agent_logs = []

        claim.agent_logs.append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "reviewer_id": action.reviewer_id,
            "reviewer_name": action.reviewer_name,
            "type": "comment",
            "message": action.comment
        })
        # Mark as modified for SQLAlchemy
        flag_modified(claim, "agent_logs")

    elif action.action == "request_info":
        claim.status = "pending_info"
        if not claim.agent_logs:
            claim.agent_logs = []

        claim.agent_logs.append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "reviewer_id": action.reviewer_id,
            "reviewer_name": action.reviewer_name,
            "type": "request_info",
            "message": action.comment
        })
        flag_modified(claim, "agent_logs")

    await db.commit()
    await db.refresh(claim)

    # Broadcast action via WebSocket
    await manager.broadcast(str(claim_id), {
        "type": "claim_updated",
        "action": action.action,
        "reviewer_id": action.reviewer_id,
        "reviewer_name": action.reviewer_name,
        "comment": action.comment,
        "new_status": claim.status,
        "timestamp": datetime.now(timezone.utc).isoformat()
    })

    logger.info(f"Review action '{action.action}' by {action.reviewer_name} on claim {claim_id}")

    return {
        "success": True,
        "claim_id": str(claim_id),
        "action": action.action,
        "new_status": claim.status
    }


@router.get("/{claim_id}/messages")
async def get_review_messages(
    claim_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """
    Get chat/action history for a claim review session.

    Returns messages from agent_logs that are review-related.
    """
    result = await db.execute(
        select(models.Claim).where(models.Claim.id == claim_id)
    )
    claim = result.scalar_one_or_none()

    if not claim:
        raise HTTPException(status_code=404, detail="Claim not found")

    # Extract review messages from agent_logs
    messages = []
    if claim.agent_logs:
        for log in claim.agent_logs:
            if log.get("type") in ["comment", "request_info"]:
                messages.append({
                    "timestamp": log.get("timestamp"),
                    "reviewer_id": log.get("reviewer_id"),
                    "reviewer_name": log.get("reviewer_name"),
                    "type": log.get("type"),
                    "message": log.get("message")
                })

    return {
        "claim_id": str(claim_id),
        "messages": messages,
        "total": len(messages)
    }


@router.get("/active")
async def get_active_reviews():
    """
    Get list of active review sessions.

    Returns claims that currently have reviewers connected.
    """
    active_sessions = []

    for claim_id, connections in manager.active_connections.items():
        if len(connections) > 0:
            reviewers = manager.get_reviewers(claim_id)
            active_sessions.append({
                "claim_id": claim_id,
                "reviewer_count": len(reviewers),
                "reviewers": reviewers
            })

    return {
        "active_sessions": active_sessions,
        "total": len(active_sessions)
    }


# =============================================================================
# Utility function for triggering HITL from claims processing
# =============================================================================

async def notify_manual_review_required(claim_id: UUID, reason: str):
    """
    Notify all connected reviewers that a claim requires manual review.

    Call this from the claims processing endpoint when decision = "manual_review"
    """
    await manager.broadcast(str(claim_id), {
        "type": "manual_review_required",
        "claim_id": str(claim_id),
        "reason": reason,
        "timestamp": datetime.now(timezone.utc).isoformat()
    })

    logger.info(f"Notified reviewers: Manual review required for claim {claim_id}")


# =============================================================================
# POST /{claim_id}/ask-agent - Conversational HITL with Agent
# =============================================================================

@router.post("/{claim_id}/ask-agent", response_model=schemas.AskAgentResponse)
async def ask_agent(
    claim_id: UUID,
    request: schemas.AskAgentRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Ask the LlamaStack agent a question about a claim in manual review.

    This enables conversational HITL where reviewers can ask for clarifications
    before making a decision. Each Q&A is logged in agent_logs for audit trail.

    Only available for claims in 'manual_review' or 'pending_info' status.
    """
    try:
        # Get claim
        result = await db.execute(
            select(models.Claim).where(models.Claim.id == claim_id)
        )
        claim = result.scalar_one_or_none()

        if not claim:
            raise HTTPException(status_code=404, detail="Claim not found")

        # Verify claim is in manual review
        if claim.status not in ["manual_review", "pending_info"]:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot ask agent - claim status is '{claim.status}'. Must be 'manual_review' or 'pending_info'."
            )

        logger.info(f"Reviewer {request.reviewer_name} asking agent about claim {claim_id}: {request.question}")

        # Get claim data directly from database (FIX: Don't rely on LlamaStack session)
        ocr_text = ""
        user_info = ""
        contracts_info = ""

        # 1. Get OCR text from claim_documents
        doc_result = await db.execute(
            select(models.ClaimDocument)
            .where(models.ClaimDocument.claim_id == claim_id)
            .order_by(models.ClaimDocument.created_at.desc())
            .limit(1)
        )
        claim_doc = doc_result.scalar_one_or_none()

        if claim_doc and claim_doc.raw_ocr_text:
            ocr_text = claim_doc.raw_ocr_text[:2000]  # First 2000 chars
            logger.info(f"Loaded OCR text ({len(claim_doc.raw_ocr_text)} chars) from claim_documents")
        else:
            logger.warning(f"No OCR text found for claim {claim_id}")

        # 2. Get user info
        user_result = await db.execute(
            select(models.User).where(models.User.user_id == claim.user_id)
        )
        user = user_result.scalar_one_or_none()

        if user:
            user_info = f"User: {user.full_name or 'N/A'}, UserID: {user.user_id}, Email: {user.email or 'N/A'}"

            # 3. Get user contracts
            contracts_result = await db.execute(
                select(models.UserContract)
                .where(models.UserContract.user_id == claim.user_id)
                .where(models.UserContract.is_active == True)
            )
            contracts = contracts_result.scalars().all()

            if contracts:
                contracts_info = f"{len(contracts)} active contract(s)"
                contract_details = []
                for contract in contracts:
                    contract_details.append(
                        f"Contract {contract.contract_number}: {contract.contract_type or 'N/A'}, "
                        f"Coverage: ${contract.coverage_amount or 0}"
                    )
                contracts_info += " - " + "; ".join(contract_details[:3])  # Max 3 contracts
        else:
            user_info = f"UserID: {claim.user_id} (no user details found)"

        # Build prompt for agent
        context_prompt = f"""You are a claims processing assistant helping a human reviewer make a decision.

CLAIM INFORMATION:
- Claim ID: {claim_id}
- Claim Number: {claim.claim_number}
- Claim Type: {claim.claim_type or 'N/A'}
- Status: {claim.status}
- User Info: {user_info or 'Not available'}
- Contracts: {contracts_info or 'Not available'}

DOCUMENT TEXT (OCR):
{ocr_text or 'Document not yet processed'}

REVIEWER QUESTION:
{request.question}

Please provide a detailed, helpful answer to the reviewer's question. Focus on facts from the claim data and be concise but thorough."""

        # Call LlamaStack agent
        async with httpx.AsyncClient(timeout=60.0) as http_client:
            # Create a temporary agent for Q&A
            agent_response = await http_client.post(
                f"{settings.llamastack_endpoint}/v1/agents",
                json={
                    "agent_config": {
                        "model": settings.llamastack_default_model,
                        "instructions": "You are a helpful claims processing assistant. Answer questions about insurance claims accurately and concisely.",
                        "enable_session_persistence": False,
                        "toolgroups": [],
                        "sampling_params": {
                            "strategy": {"type": "greedy"},
                            "max_tokens": 1024
                        }
                    }
                }
            )

            if agent_response.status_code != 200:
                raise HTTPException(status_code=500, detail=f"Failed to create agent: {agent_response.text}")

            agent_id = agent_response.json()["agent_id"]
            logger.info(f"Created Q&A agent: {agent_id}")

            # Create session
            session_response = await http_client.post(
                f"{settings.llamastack_endpoint}/v1/agents/{agent_id}/session",
                json={"session_name": f"qa_{claim_id}"}
            )

            if session_response.status_code != 200:
                raise HTTPException(status_code=500, detail=f"Failed to create session: {session_response.text}")

            session_id = session_response.json()["session_id"]
            logger.info(f"Created Q&A session: {session_id}")

            # Execute turn
            answer = ""
            async with http_client.stream(
                "POST",
                f"{settings.llamastack_endpoint}/v1/agents/{agent_id}/session/{session_id}/turn",
                json={
                    "messages": [{"role": "user", "content": context_prompt}],
                    "stream": True
                },
                timeout=60.0
            ) as response:
                if response.status_code != 200:
                    raise HTTPException(status_code=500, detail=f"Failed to execute turn: {response.text}")

                async for line in response.aiter_lines():
                    if not line.strip() or not line.startswith("data: "):
                        continue

                    data = line[6:]  # Remove "data: " prefix
                    try:
                        event = json.loads(data)
                        if not isinstance(event, dict) or "event" not in event:
                            continue

                        payload = event["event"].get("payload", {})
                        step_type = payload.get("step_type")
                        event_type = payload.get("event_type")

                        # Collect inference text
                        if step_type == "inference":
                            if event_type == "step_progress":
                                step_details = payload.get("step_details", {})
                                text_delta = step_details.get("text_delta", "")
                                if text_delta:
                                    answer += text_delta
                            elif event_type == "step_complete":
                                step_details = payload.get("step_details", {})
                                model_response = step_details.get("model_response", {})
                                content = model_response.get("content", "")
                                if content and not answer:
                                    answer = content

                        # Turn complete
                        elif event_type == "turn_complete":
                            if not answer:
                                turn_response = payload.get("turn", {})
                                output_message = turn_response.get("output_message", {})
                                content = output_message.get("content", "")
                                if content:
                                    answer = content

                    except json.JSONDecodeError:
                        continue

            # Delete temporary agent (cleanup)
            try:
                await http_client.delete(f"{settings.llamastack_endpoint}/v1/agents/{agent_id}")
            except:
                pass  # Ignore cleanup errors

        if not answer:
            answer = "I apologize, but I couldn't generate a response. Please try again or contact support."

        logger.info(f"Agent response ({len(answer)} chars): {answer[:200]}...")

        # Save Q&A to agent_logs
        timestamp = datetime.now(timezone.utc)
        if not claim.agent_logs:
            claim.agent_logs = []

        claim.agent_logs.extend([
            {
                "type": "reviewer_question",
                "timestamp": timestamp.isoformat(),
                "reviewer_id": request.reviewer_id,
                "reviewer_name": request.reviewer_name,
                "message": request.question
            },
            {
                "type": "agent_answer",
                "timestamp": timestamp.isoformat(),
                "message": answer
            }
        ])
        flag_modified(claim, "agent_logs")
        await db.commit()

        logger.info(f"Saved Q&A to agent_logs for claim {claim_id}")

        # Broadcast Q&A via WebSocket
        await manager.broadcast(str(claim_id), {
            "type": "qa_exchange",
            "claim_id": str(claim_id),
            "question": request.question,
            "answer": answer,
            "reviewer_id": request.reviewer_id,
            "reviewer_name": request.reviewer_name,
            "timestamp": timestamp.isoformat()
        })

        return schemas.AskAgentResponse(
            success=True,
            claim_id=str(claim_id),
            question=request.question,
            answer=answer,
            timestamp=timestamp
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in ask-agent: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
