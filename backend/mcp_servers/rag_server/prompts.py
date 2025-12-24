"""
RAG Server Prompt Templates
"""

KNOWLEDGE_BASE_SYNTHESIS_PROMPT = """
You are a knowledge synthesis expert for insurance policies and procedures.

Based on the following knowledge base articles, provide a clear, comprehensive answer to the user's question.

User Question: {question}

Relevant Knowledge Base Articles:
{kb_articles}

Synthesize this information into a clear, actionable answer:
{{
    "answer": "comprehensive answer to the question",
    "sources": [
        {{
            "article_id": "id",
            "title": "article title",
            "relevance": "how this article helps answer the question"
        }}
    ],
    "confidence": 0.0-1.0,
    "caveats": ["any limitations or exceptions to note"],
    "related_topics": ["related topics the user might want to explore"],
    "action_items": ["specific steps the user should take"]
}}

Be accurate, cite your sources, and highlight any uncertainties or edge cases.
"""

CONTRACT_COVERAGE_EXTRACTION_PROMPT = """
You are an insurance contract specialist. Extract and structure coverage information from the following contract text.

Contract Text:
{contract_text}

Claim Type: {claim_type}

Extract the following information relevant to this claim type:
1. Coverage limits and amounts
2. Deductibles
3. Co-payment requirements
4. Exclusions
5. Special conditions
6. Pre-authorization requirements
7. Time limits for filing claims

Return a structured JSON object:
{{
    "coverage_summary": {{
        "max_coverage": number,
        "deductible": number,
        "copay_percentage": number,
        "annual_limit": number
    }},
    "applicable_to_claim_type": true,
    "coverage_details": "detailed explanation",
    "exclusions": ["list of exclusions"],
    "conditions": ["list of conditions that must be met"],
    "time_limits": {{
        "filing_deadline_days": number,
        "service_date_limit_days": number
    }},
    "required_documents": ["list of required supporting documents"],
    "pre_authorization_required": false,
    "notes": "any additional important information"
}}
"""

SIMILAR_CLAIMS_SUMMARY_PROMPT = """
You are an expert at analyzing insurance claims patterns.

Given this current claim and a list of similar historical claims, provide a summary analysis.

Current Claim:
{current_claim}

Similar Historical Claims:
{similar_claims}

Provide a JSON response:
{{
    "pattern_analysis": "description of patterns found in similar claims",
    "common_outcomes": {{
        "approved": 0.0,
        "denied": 0.0,
        "manual_review": 0.0
    }},
    "average_processing_time": "time in hours/days",
    "common_issues": ["list of common issues encountered"],
    "success_factors": ["factors that led to approval in similar cases"],
    "denial_reasons": ["common reasons for denial in similar cases"],
    "recommendation_based_on_history": "suggested approach based on historical data",
    "notable_precedents": [
        {{
            "claim_id": "id",
            "similarity_score": 0.0,
            "outcome": "outcome",
            "key_factors": ["relevant factors"]
        }}
    ]
}}
"""


def get_knowledge_base_synthesis_prompt(question: str, kb_articles: str) -> str:
    """
    Generate knowledge base synthesis prompt.

    Args:
        question: User's question
        kb_articles: Formatted knowledge base articles

    Returns:
        Formatted prompt string
    """
    return KNOWLEDGE_BASE_SYNTHESIS_PROMPT.format(
        question=question,
        kb_articles=kb_articles
    )


def get_contract_coverage_prompt(contract_text: str, claim_type: str) -> str:
    """
    Generate contract coverage extraction prompt.

    Args:
        contract_text: The contract text to analyze
        claim_type: Type of claim being processed

    Returns:
        Formatted prompt string
    """
    return CONTRACT_COVERAGE_EXTRACTION_PROMPT.format(
        contract_text=contract_text,
        claim_type=claim_type
    )


def get_similar_claims_prompt(current_claim: str, similar_claims: str) -> str:
    """
    Generate similar claims analysis prompt.

    Args:
        current_claim: Current claim data
        similar_claims: Similar historical claims data

    Returns:
        Formatted prompt string
    """
    return SIMILAR_CLAIMS_SUMMARY_PROMPT.format(
        current_claim=current_claim,
        similar_claims=similar_claims
    )
