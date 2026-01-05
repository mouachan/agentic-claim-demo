"""
MCP OCR Server - Extract text from documents using qwen-vl-7b multimodal model
"""

import asyncio
import base64
import logging
import os
import time
from pathlib import Path
from typing import Dict, Any, Optional

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
    description="OCR processing with qwen-vl-7b multimodal model",
    version="2.0.0",
)

# Configuration
QWEN_VL_ENDPOINT = os.getenv(
    "QWEN_VL_ENDPOINT",
    "http://qwen-vl-7b-predictor.multimodal-demo.svc.cluster.local:8080/v1"
)
LLAMASTACK_ENDPOINT = os.getenv("LLAMASTACK_ENDPOINT", "http://localhost:8090")


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
def image_to_base64(image_path: Path) -> str:
    """Convert image to base64 string."""
    with open(image_path, "rb") as img_file:
        return base64.b64encode(img_file.read()).decode('utf-8')


async def extract_text_with_qwen_vl(image_path: Path) -> tuple[str, float]:
    """
    Extract text from image using qwen-vl-7b multimodal model.

    Qwen-VL is a vision-language model that can understand images and extract text.
    """
    try:
        # Convert image to base64
        image_b64 = image_to_base64(image_path)

        # Prepare prompt for text extraction
        prompt = """Extract all text from this image.

Please transcribe exactly what you see, maintaining the layout and structure.
Include all visible text, numbers, dates, and other textual information."""

        # Call qwen-vl-7b model
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{QWEN_VL_ENDPOINT}/chat/completions",
                json={
                    "model": "qwen-vl-7b",
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": prompt},
                                {
                                    "type": "image_url",
                                    "image_url": {
                                        "url": f"data:image/jpeg;base64,{image_b64}"
                                    }
                                }
                            ]
                        }
                    ],
                    "temperature": 0.1,
                    "max_tokens": 2048
                }
            )

            if response.status_code == 200:
                result = response.json()
                extracted_text = result["choices"][0]["message"]["content"]

                # Qwen-VL is very confident, estimate ~0.9 confidence for successful extraction
                confidence = 0.9

                logger.info(f"Extracted text from {image_path.name} using qwen-vl-7b")
                return extracted_text.strip(), confidence
            else:
                logger.error(f"Qwen-VL API error: {response.status_code} - {response.text}")
                raise HTTPException(
                    status_code=500,
                    detail=f"Qwen-VL API error: {response.status_code}"
                )

    except Exception as e:
        logger.error(f"Error extracting text with qwen-vl: {str(e)}")
        raise


async def extract_text_from_pdf(pdf_path: Path) -> tuple[str, float]:
    """Extract text from PDF by converting to images and using qwen-vl."""
    try:
        # Convert PDF to images
        images = convert_from_path(pdf_path)

        all_text = []
        all_confidences = []

        for i, image in enumerate(images):
            # Optimize image to reduce Qwen-VL processing time
            # Resize to 70% + JPEG quality 85 → ~8s instead of ~12s
            new_size = (int(image.size[0] * 0.7), int(image.size[1] * 0.7))
            optimized_image = image.resize(new_size, Image.Resampling.LANCZOS)
            optimized_image = optimized_image.convert('RGB')  # JPEG needs RGB

            # Save optimized image
            temp_image_path = Path(f"/tmp/page_{i}.jpg")
            optimized_image.save(temp_image_path, "JPEG", quality=85, optimize=True)

            # Extract text from page using qwen-vl
            text, confidence = await extract_text_with_qwen_vl(temp_image_path)
            all_text.append(text)
            all_confidences.append(confidence)

            # Clean up temp file
            temp_image_path.unlink()

        # Combine all pages
        combined_text = "\n\n--- Page Break ---\n\n".join(all_text)
        avg_confidence = sum(all_confidences) / len(all_confidences) if all_confidences else 0.0

        logger.info(f"Extracted text from PDF with {len(images)} pages, confidence: {avg_confidence:.2f}")
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
    Extract text from a document using qwen-vl-7b multimodal model.

    MCP Tool: ocr_document
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
            # Optimize image before OCR
            image = Image.open(document_path)
            new_size = (int(image.size[0] * 0.7), int(image.size[1] * 0.7))
            optimized_image = image.resize(new_size, Image.Resampling.LANCZOS)
            optimized_image = optimized_image.convert('RGB')

            temp_image_path = Path(f"/tmp/optimized_{document_path.stem}.jpg")
            optimized_image.save(temp_image_path, "JPEG", quality=85, optimize=True)

            raw_text, confidence = await extract_text_with_qwen_vl(temp_image_path)
            temp_image_path.unlink()  # Clean up
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

        # Check if we exceeded 10s timeout threshold
        if total_time > 10.0:
            logger.warning(f"⚠️  OCR TOO SLOW: {total_time:.2f}s > 10s LlamaStack timeout!")

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
    return HealthResponse(status="alive", service="mcp-ocr-server-qwen")


@app.get("/health/ready", response_model=HealthResponse)
async def readiness():
    """Readiness probe."""
    # Check if qwen-vl endpoint is accessible
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{QWEN_VL_ENDPOINT}/health")
            if response.status_code == 200:
                return HealthResponse(status="ready", service="mcp-ocr-server-qwen")
            else:
                raise HTTPException(status_code=503, detail="Qwen-VL service not ready")
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Qwen-VL not ready: {str(e)}")


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "service": "MCP OCR Server (Qwen-VL)",
        "version": "2.0.0",
        "status": "running",
        "model": "qwen-vl-7b",
        "tools": ["ocr_document"]
    }


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", "8080"))
    uvicorn.run(app, host="0.0.0.0", port=port)
