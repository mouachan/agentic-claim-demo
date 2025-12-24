"""
OCR Server Prompt Templates
"""

OCR_VALIDATION_PROMPT = """
You are an expert at validating and structuring insurance claim documents.

Given the following OCR extracted text, extract and validate these fields: {expected_fields}

OCR Text:
```
{ocr_text}
```

Instructions:
1. Extract each requested field accurately
2. Correct obvious OCR errors (e.g., "0" vs "O", "1" vs "l")
3. Standardize formats (dates, amounts, names)
4. Flag any uncertain or missing fields

Return a JSON object with this structure:
{{
    "fields": {{
        "field_name": {{
            "value": "extracted value or null",
            "confidence": 0.0-1.0,
            "raw_value": "original OCR text",
            "issues": ["list of any issues or corrections made"]
        }}
    }},
    "overall_confidence": 0.0-1.0,
    "requires_manual_review": false,
    "notes": "any additional observations"
}}
"""


def get_ocr_validation_prompt(ocr_text: str, expected_fields: list) -> str:
    """
    Generate OCR validation prompt with provided data.

    Args:
        ocr_text: The raw OCR text to validate
        expected_fields: List of fields expected to extract

    Returns:
        Formatted prompt string
    """
    return OCR_VALIDATION_PROMPT.format(
        ocr_text=ocr_text[:2000],  # Limit to first 2000 chars
        expected_fields=', '.join(expected_fields)
    )
