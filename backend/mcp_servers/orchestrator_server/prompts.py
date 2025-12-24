"""
Orchestrator Server Prompt Templates
"""

CLAIM_ANALYSIS_DECISION_PROMPT = """
You are an expert insurance claims analyst. Analyze this claim and respond with ONLY a JSON object, no other text.

Claim: {claim_id} for User: {user_id}

OCR Data: {ocr_data}

User Contracts: {user_contracts}

Similar Claims: {similar_claims}

Guardrails: {guardrails_results}

Respond with ONLY this JSON format:
{{
    "recommendation": "approve|deny|manual_review",
    "confidence": 0.85,
    "reasoning": "Brief explanation of decision",
    "relevant_policies": ["POLICY-001", "POLICY-002"]
}}
"""

ORCHESTRATOR_WORKFLOW_PROMPT = """
You are a workflow orchestration specialist for insurance claims processing.

Based on the claim information and initial analysis, determine the optimal processing workflow.

Claim Information:
{claim_info}

Initial OCR Results:
{ocr_results}

Available Processing Options:
1. Standard workflow: OCR → Guardrails → RAG → LLM Decision
2. Expedited workflow: OCR → LLM Decision (skip RAG if not needed)
3. Manual review workflow: Flag for immediate human review

Determine the best workflow and return:
{{
    "recommended_workflow": "standard|expedited|manual_review",
    "reasoning": "explanation of why this workflow was chosen",
    "workflow_steps": [
        {{
            "step": "step name",
            "agent": "agent to use",
            "required": true,
            "estimated_time_seconds": 0,
            "conditions": "any conditions for executing this step"
        }}
    ],
    "skip_steps": ["list of steps that can be skipped and why"],
    "priority_level": "low|medium|high|urgent",
    "estimated_total_time_seconds": 0,
    "risk_factors": ["any risk factors identified"],
    "confidence": 0.0
}}

Consider claim complexity, urgency, data quality, and available information when making your recommendation.
"""

PII_DETECTION_PROMPT = """
You are a privacy protection specialist. Analyze the following text and identify any Personal Identifiable Information (PII) that should be protected.

Text to analyze:
```
{text}
```

Look for:
- Full names combined with sensitive information
- Social Security Numbers (even partial)
- Credit card numbers
- Bank account numbers
- Medical information (diagnoses, treatments, medications)
- Biometric data
- Government ID numbers
- Financial details
- Health insurance information
- Date of birth combined with other identifiers

Return a JSON object:
{{
    "has_pii": false,
    "pii_types": ["list of PII types found"],
    "sensitive_spans": [
        {{
            "type": "pii type",
            "text": "the sensitive text span",
            "severity": "low|medium|high",
            "recommendation": "flag|redact|block"
        }}
    ],
    "risk_level": "low|medium|high",
    "requires_redaction": false,
    "notes": "additional context or observations"
}}

Be conservative - flag anything that could potentially identify an individual when combined with other data.
"""


def get_claim_decision_prompt(
    claim_id: str,
    user_id: str,
    ocr_data: str,
    user_contracts: str,
    similar_claims: str,
    guardrails_results: str = "No issues detected"
) -> str:
    """
    Generate claim analysis decision prompt.

    Args:
        claim_id: Claim identifier
        user_id: User identifier
        ocr_data: OCR extracted data
        user_contracts: User's active contracts
        similar_claims: Similar historical claims
        guardrails_results: Guardrails analysis results

    Returns:
        Formatted prompt string
    """
    return CLAIM_ANALYSIS_DECISION_PROMPT.format(
        claim_id=claim_id,
        user_id=user_id,
        ocr_data=ocr_data,
        user_contracts=user_contracts,
        similar_claims=similar_claims,
        guardrails_results=guardrails_results
    )


def get_workflow_orchestration_prompt(claim_info: str, ocr_results: str) -> str:
    """
    Generate workflow orchestration prompt.

    Args:
        claim_info: Claim information
        ocr_results: Initial OCR results

    Returns:
        Formatted prompt string
    """
    return ORCHESTRATOR_WORKFLOW_PROMPT.format(
        claim_info=claim_info,
        ocr_results=ocr_results
    )


def get_pii_detection_prompt(text: str) -> str:
    """
    Generate PII detection prompt.

    Args:
        text: Text to analyze for PII

    Returns:
        Formatted prompt string
    """
    return PII_DETECTION_PROMPT.format(text=text[:2000])  # Limit to first 2000 chars
