"""
MCP OCR Server - Extract text from documents using EasyOCR

Performance improvement: Migrated from Qwen-VL 7B to EasyOCR for faster processing.
- Qwen-VL: 30+ seconds per document (exceeded LlamaStack 30s timeout)
- EasyOCR: 2-4 seconds per document (embedded library, no external service)
"""

import asyncio
import logging
import os
import time
from pathlib import Path
from typing import Dict, Any, Optional

import easyocr
import httpx
from fastapi import FastAPI, HTTPException
from PIL import Image
from pdf2image import convert_from_path
from pydantic import BaseModel, Field

# Import prompts
from prompts import get_ocr_validation_prompt

# Configure logging
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)

# FastAPI app
app = FastAPI(
    title="MCP OCR Server",
    description="OCR processing with EasyOCR (fast, embedded)",
    version="3.0.0",
)

# Configuration
LLAMASTACK_ENDPOINT = os.getenv("LLAMASTACK_ENDPOINT", "http://localhost:8090")
OCR_LANGUAGES = os.getenv("OCR_LANGUAGES", "en,fr").split(",")

# Initialize EasyOCR reader (lazy loading on first use)
_ocr_reader = None

def get_ocr_reader():
    """Get or create EasyOCR reader instance (singleton)."""
    global _ocr_reader
    if _ocr_reader is None:
        logger.info(f"Initializing EasyOCR reader with languages: {OCR_LANGUAGES}")
        _ocr_reader = easyocr.Reader(OCR_LANGUAGES, gpu=True)  # Use GPU if available
        logger.info("EasyOCR reader initialized successfully")
    return _ocr_reader


# Pydantic models
class OCRRequest(BaseModel):
    document_path: str = Field(..., description="Path to document image or PDF")
    document_type: str = Field(default="claim_form", description="Type of document")
    language: str = Field(default="eng", description="OCR language code")


class OCRResponse(BaseModel):
    success: bool
    raw_text: Optional[str] = None
    structured_data: Optional[Dict[str, Any]] = None
    confidence: Optional[float] = None
    errors: list[str] = Field(default_factory=list)


class HealthResponse(BaseModel):
    status: str
    service: str


# Helper functions
async def extract_text_with_easyocr(image_path: Path) -> tuple[str, float]:
    """
    Extract text from image using EasyOCR.

    EasyOCR is a lightweight, fast OCR library that supports 80+ languages.
    It runs locally (no external API calls) and is much faster than Qwen-VL.
    """
    try:
        reader = get_ocr_reader()

        # Run OCR on the image
        # readtext returns list of (bbox, text, confidence) tuples
        result = reader.readtext(str(image_path))

        # Extract text and confidence
        if not result:
            logger.warning(f"No text detected in {image_path.name}")
            return "", 0.0

        # Combine all detected text blocks
        text_blocks = []
        confidences = []

        for bbox, text, confidence in result:
            text_blocks.append(text)
            confidences.append(confidence)

        # Join text blocks with spaces
        extracted_text = " ".join(text_blocks)

        # Calculate average confidence
        avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0

        logger.info(f"Extracted text from {image_path.name} using EasyOCR (confidence: {avg_confidence:.2f})")
        return extracted_text.strip(), avg_confidence

    except Exception as e:
        logger.error(f"Error extracting text with EasyOCR: {str(e)}")
        raise


async def extract_text_from_pdf(pdf_path: Path) -> tuple[str, float]:
    """Extract text from PDF by converting to images and using EasyOCR."""
    try:
        # Convert PDF to images
        images = convert_from_path(pdf_path, dpi=200)  # 200 DPI for good quality + speed

        all_text = []
        all_confidences = []

        for i, image in enumerate(images):
            # Save image temporarily for EasyOCR
            temp_image_path = Path(f"/tmp/page_{i}.jpg")
            image.save(temp_image_path, "JPEG", quality=90)

            # Extract text from page using EasyOCR
            text, confidence = await extract_text_with_easyocr(temp_image_path)
            all_text.append(text)
            all_confidences.append(confidence)

            # Clean up temp file
            temp_image_path.unlink()

        # Combine all pages
        combined_text = "\n\n--- Page Break ---\n\n".join(all_text)
        avg_confidence = sum(all_confidences) / len(all_confidences) if all_confidences else 0.0

        logger.info(f"Extracted text from PDF with {len(images)} pages using EasyOCR, confidence: {avg_confidence:.2f}")
        return combined_text, avg_confidence

    except Exception as e:
        logger.error(f"Error extracting text from PDF: {str(e)}")
        raise


async def validate_with_llm(raw_text: str, document_type: str) -> Dict[str, Any]:
    """Validate and structure OCR text using LLM."""
    try:
        # Define expected fields based on document type
        field_mapping = {
            "claim_form": ["claim_number", "claimant_name", "date_of_service", "provider_name", "diagnosis", "amount"],
            "invoice": ["invoice_number", "date", "vendor_name", "total_amount", "line_items"],
            "medical_record": ["patient_name", "date_of_birth", "diagnosis", "treatment", "provider"],
            "id_card": ["name", "id_number", "date_of_birth", "address"],
            "other": ["key_information"]
        }

        expected_fields = field_mapping.get(document_type, field_mapping["other"])

        # Prepare LLM prompt
        prompt = get_ocr_validation_prompt(raw_text, expected_fields)

        # Call LlamaStack
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{LLAMASTACK_ENDPOINT}/inference/generate",
                json={
                    "model": "llama-instruct-32-3b",
                    "prompt": prompt,
                    "temperature": 0.1,
                    "max_tokens": 1024,
                }
            )

            if response.status_code == 200:
                result = response.json()
                # Parse the generated text as JSON
                import json
                try:
                    structured_data = json.loads(result.get("generated_text", "{}"))
                    logger.info("Successfully validated OCR text with LLM")
                    return structured_data
                except json.JSONDecodeError:
                    logger.warning("LLM response was not valid JSON, returning raw text")
                    return {
                        "fields": {"raw_text": {"value": raw_text, "confidence": 0.8}},
                        "overall_confidence": 0.8,
                        "requires_manual_review": True,
                        "notes": "LLM validation failed to parse"
                    }
            else:
                logger.error(f"LlamaStack API error: {response.status_code}")
                return {
                    "fields": {"raw_text": {"value": raw_text, "confidence": 0.7}},
                    "overall_confidence": 0.7,
                    "requires_manual_review": True,
                    "notes": "LLM validation unavailable"
                }

    except Exception as e:
        logger.error(f"Error validating with LLM: {str(e)}")
        return {
            "fields": {"raw_text": {"value": raw_text, "confidence": 0.7}},
            "overall_confidence": 0.7,
            "requires_manual_review": True,
            "notes": f"Error: {str(e)}"
        }


# API Endpoints
@app.post("/ocr_document", response_model=OCRResponse)
async def ocr_document(request: OCRRequest) -> OCRResponse:
    """
    Extract text from a document using EasyOCR.

    MCP Tool: ocr_document

    Performance: 2-4 seconds per document (much faster than Qwen-VL's 30+ seconds)
    """
    # ============== TIMING START ==============
    start_time = time.time()
    logger.info(f"⏱️  OCR STARTED for document: {request.document_path}")

    try:
        document_path = Path(request.document_path)

        # Check if file exists
        if not document_path.exists():
            logger.error(f"Document not found: {request.document_path}")
            raise HTTPException(
                status_code=404,
                detail=f"Document not found: {request.document_path}"
            )

        # Determine file type and extract text
        file_extension = document_path.suffix.lower()

        # ============== TIMING: OCR Extraction ==============
        extraction_start = time.time()
        if file_extension in ['.pdf']:
            raw_text, confidence = await extract_text_from_pdf(document_path)
        elif file_extension in ['.jpg', '.jpeg', '.png', '.tiff', '.bmp']:
            raw_text, confidence = await extract_text_with_easyocr(document_path)
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported file type: {file_extension}"
            )
        extraction_time = time.time() - extraction_start
        logger.info(f"⏱️  OCR Extraction completed in {extraction_time:.2f}s (confidence: {confidence:.2f})")

        # ============== TIMING: LLM Validation ==============
        validation_start = time.time()
        structured_data = await validate_with_llm(raw_text, request.document_type)
        validation_time = time.time() - validation_start
        logger.info(f"⏱️  LLM Validation completed in {validation_time:.2f}s")

        # ============== TIMING END ==============
        total_time = time.time() - start_time
        logger.info(f"⏱️  OCR COMPLETED in {total_time:.2f}s (Extraction: {extraction_time:.2f}s, Validation: {validation_time:.2f}s)")

        # Check if we exceeded LlamaStack timeout threshold (30s)
        if total_time > 25.0:
            logger.warning(f"⚠️  OCR approaching timeout: {total_time:.2f}s (LlamaStack timeout: 30s)")

        return OCRResponse(
            success=True,
            raw_text=raw_text,
            structured_data=structured_data,
            confidence=confidence,
            errors=[]
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing OCR request: {str(e)}")
        return OCRResponse(
            success=False,
            raw_text=None,
            structured_data=None,
            confidence=0.0,
            errors=[str(e)]
        )


@app.get("/health/live", response_model=HealthResponse)
async def liveness():
    """Liveness probe."""
    return HealthResponse(status="alive", service="mcp-ocr-server-easyocr")


@app.get("/health/ready", response_model=HealthResponse)
async def readiness():
    """Readiness probe - EasyOCR is embedded, always ready if server is alive."""
    try:
        # EasyOCR is embedded, just check if we can initialize it
        reader = get_ocr_reader()
        if reader:
            return HealthResponse(status="ready", service="mcp-ocr-server-easyocr")
        else:
            raise HTTPException(status_code=503, detail="EasyOCR reader not initialized")
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"EasyOCR not ready: {str(e)}")


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "service": "MCP OCR Server (EasyOCR)",
        "version": "3.0.0",
        "status": "running",
        "model": "easyocr",
        "languages": OCR_LANGUAGES,
        "tools": ["ocr_document"],
        "performance": "2-4 seconds per document (vs 30+ seconds with Qwen-VL)"
    }


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", "8080"))
    uvicorn.run(app, host="0.0.0.0", port=port)
