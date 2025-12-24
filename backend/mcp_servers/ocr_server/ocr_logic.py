"""
OCR Logic - Extract text from documents using Tesseract OCR and validate with LLM
"""

import logging
import os
from pathlib import Path
from typing import Dict, Any, Tuple

import pytesseract
from PIL import Image
from pdf2image import convert_from_path
import httpx

from prompts import get_ocr_validation_prompt

logger = logging.getLogger(__name__)

# LlamaStack configuration
LLAMASTACK_ENDPOINT = os.getenv("LLAMASTACK_ENDPOINT", "http://llamastack.claims-demo.svc.cluster.local:8321")
LLM_MODEL = os.getenv("LLM_MODEL", "llama-instruct-32-3b")


async def extract_text_from_image(image_path: Path, language: str = "eng") -> Tuple[str, float]:
    """
    Extract text from image using Tesseract OCR.

    Returns:
        Tuple of (extracted_text, confidence_score)
    """
    try:
        image = Image.open(image_path)

        # Get detailed OCR data including confidence
        ocr_data = pytesseract.image_to_data(
            image,
            lang=language,
            output_type=pytesseract.Output.DICT
        )

        # Extract text
        text = pytesseract.image_to_string(image, lang=language)

        # Calculate average confidence
        confidences = [int(conf) for conf in ocr_data['conf'] if conf != '-1']
        avg_confidence = sum(confidences) / len(confidences) / 100 if confidences else 0.0

        logger.info(f"Extracted text from {image_path.name}, confidence: {avg_confidence:.2f}")
        return text.strip(), avg_confidence

    except Exception as e:
        logger.error(f"Error extracting text from image: {str(e)}")
        raise


async def extract_text_from_pdf(pdf_path: Path, language: str = "eng") -> Tuple[str, float]:
    """
    Extract text from PDF by converting to images first.

    Returns:
        Tuple of (extracted_text, confidence_score)
    """
    try:
        # Convert PDF to images
        images = convert_from_path(pdf_path)

        all_text = []
        all_confidences = []

        for i, image in enumerate(images):
            # Save temp image
            temp_image_path = f"/tmp/page_{i}.png"
            image.save(temp_image_path, "PNG")

            # Extract text from page
            text, confidence = await extract_text_from_image(
                Path(temp_image_path),
                language
            )
            all_text.append(text)
            all_confidences.append(confidence)

            # Clean up temp file
            os.remove(temp_image_path)

        # Combine all pages
        combined_text = "\n\n--- Page Break ---\n\n".join(all_text)
        avg_confidence = sum(all_confidences) / len(all_confidences) if all_confidences else 0.0

        logger.info(f"Extracted text from PDF with {len(images)} pages, confidence: {avg_confidence:.2f}")
        return combined_text, avg_confidence

    except Exception as e:
        logger.error(f"Error extracting text from PDF: {str(e)}")
        raise


async def validate_with_llm(raw_text: str, document_type: str) -> Dict[str, Any]:
    """
    Validate and structure OCR text using LLM.

    Args:
        raw_text: Raw OCR extracted text
        document_type: Type of document (claim_form, invoice, etc.)

    Returns:
        Structured data with validated fields
    """
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

        # Prepare LLM prompt using centralized prompts
        prompt = get_ocr_validation_prompt(raw_text, expected_fields)

        # Call LlamaStack Inference API
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{LLAMASTACK_ENDPOINT}/v1/chat/completions",
                json={
                    "model": LLM_MODEL,
                    "messages": [
                        {
                            "role": "system",
                            "content": "You are a document processing assistant that validates and structures OCR text. Always respond with valid JSON."
                        },
                        {
                            "role": "user",
                            "content": prompt
                        }
                    ],
                    "temperature": 0.1,
                    "max_tokens": 1024,
                }
            )

            if response.status_code == 200:
                result = response.json()
                # Extract generated text from OpenAI-compatible format
                generated_text = result.get("choices", [{}])[0].get("message", {}).get("content", "{}")

                # Parse the generated text as JSON
                import json
                try:
                    structured_data = json.loads(generated_text)
                    logger.info("Successfully validated OCR text with LLM")
                    return structured_data
                except json.JSONDecodeError:
                    logger.warning("LLM response was not valid JSON, returning raw text")
                    return {
                        "fields": {"raw_text": {"value": raw_text, "confidence": 0.5}},
                        "overall_confidence": 0.5,
                        "requires_manual_review": True,
                        "notes": "LLM validation failed to parse"
                    }
            else:
                logger.error(f"LlamaStack API error: {response.status_code}")
                return {
                    "fields": {"raw_text": {"value": raw_text, "confidence": 0.5}},
                    "overall_confidence": 0.5,
                    "requires_manual_review": True,
                    "notes": "LLM validation unavailable"
                }

    except Exception as e:
        logger.error(f"Error validating with LLM: {str(e)}")
        return {
            "fields": {"raw_text": {"value": raw_text, "confidence": 0.5}},
            "overall_confidence": 0.5,
            "requires_manual_review": True,
            "notes": f"Error: {str(e)}"
        }


async def process_ocr_document(
    document_path: str,
    document_type: str = "claim_form",
    language: str = "eng"
) -> Dict[str, Any]:
    """
    Main OCR processing function.

    Args:
        document_path: Path to document image or PDF
        document_type: Type of document
        language: OCR language code

    Returns:
        Dict with success, raw_text, structured_data, confidence, errors
    """
    try:
        doc_path = Path(document_path)

        # Check if file exists
        if not doc_path.exists():
            logger.error(f"Document not found: {document_path}")
            return {
                "success": False,
                "raw_text": None,
                "structured_data": None,
                "confidence": 0.0,
                "errors": [f"Document not found: {document_path}"]
            }

        # Determine file type and extract text
        file_extension = doc_path.suffix.lower()

        if file_extension in ['.pdf']:
            raw_text, confidence = await extract_text_from_pdf(doc_path, language)
        elif file_extension in ['.jpg', '.jpeg', '.png', '.tiff', '.bmp']:
            raw_text, confidence = await extract_text_from_image(doc_path, language)
        else:
            return {
                "success": False,
                "raw_text": None,
                "structured_data": None,
                "confidence": 0.0,
                "errors": [f"Unsupported file type: {file_extension}"]
            }

        # Validate with LLM
        structured_data = await validate_with_llm(raw_text, document_type)

        return {
            "success": True,
            "raw_text": raw_text,
            "structured_data": structured_data,
            "confidence": confidence,
            "errors": []
        }

    except Exception as e:
        logger.error(f"Error processing OCR request: {str(e)}")
        return {
            "success": False,
            "raw_text": None,
            "structured_data": None,
            "confidence": 0.0,
            "errors": [str(e)]
        }
