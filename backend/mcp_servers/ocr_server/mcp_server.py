"""
MCP OCR Server - Using FastMCP SDK
Direct function calls (no HTTP overhead)
"""

import os
import logging
from mcp.server.fastmcp import FastMCP

# Import backend functions
from server import (
    ocr_document,
    OCRRequest
)

# Configure logging
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)

# Create FastMCP server
mcp = FastMCP("ocr-server")


@mcp.tool()
async def ocr_document_tool(
    document_path: str,
    document_type: str = "claim_form",
    extract_structured: bool = True,
    language: str = "eng"
) -> str:
    """
    Extract text and structured data from insurance claim documents using OCR.

    Supports PDF, JPG, PNG, and TIFF formats. Uses vision models for accurate text extraction
    and LLM validation for structured data extraction.

    Args:
        document_path: Path to the document file (PDF, image, etc.)
        document_type: Type of document to optimize OCR processing.
                      Options: claim_form, invoice, medical_record, id_card, other
                      Default: claim_form
        extract_structured: Whether to extract structured data (dates, amounts, names) using LLM
                          Default: True
        language: OCR language code (eng, fra, deu, etc.)
                 Default: eng

    Returns:
        JSON string with OCR text, structured data, and confidence scores
    """
    logger.info(
        f"ocr_document called: document_path={document_path}, "
        f"type={document_type}, extract_structured={extract_structured}"
    )

    try:
        request = OCRRequest(
            document_path=document_path,
            document_type=document_type,
            extract_structured=extract_structured,
            language=language
        )
        response = await ocr_document(request)
        return response.model_dump_json()
    except Exception as e:
        logger.error(f"Error in ocr_document: {e}")
        return f'{{"error": "Failed to process OCR document: {str(e)}"}}'


if __name__ == "__main__":
    import uvicorn

    # Get port from environment or use default
    port = int(os.getenv("PORT", "8080"))

    logger.info(f"Starting MCP OCR Server (FastMCP) on port {port}")

    # Run FastMCP server with SSE transport using uvicorn
    uvicorn.run(mcp.sse_app, host="0.0.0.0", port=port)
