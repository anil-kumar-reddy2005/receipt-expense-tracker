"""
Receipt image validation, Gemini Vision API invocation, and JSON extraction engine.
"""

import os
import json
import re
from typing import Dict, Any, Tuple, Optional
import streamlit as st
from google import genai
from google.genai import types
from google.genai.errors import APIError

from prompts import SYSTEM_PROMPT, EXTRACTION_PROMPT

# Supported formats and size limit
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
ALLOWED_MIME_TYPES = {"image/jpeg", "image/png", "image/webp"}
MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB

DEFAULT_MODEL_ID = "gemini-2.5-flash"
FALLBACK_MODEL_IDS = ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash"]


def validate_image(
    file_bytes: bytes,
    filename: str,
    content_type: Optional[str] = None
) -> Tuple[bool, str]:
    """
    Validates uploaded receipt image extension, MIME type, and size.
    Returns (is_valid, error_message).
    """
    if not file_bytes or len(file_bytes) == 0:
        return False, "Uploaded file is empty."

    if len(file_bytes) > MAX_FILE_SIZE_BYTES:
        size_mb = len(file_bytes) / (1024 * 1024)
        return False, f"File size ({size_mb:.2f} MB) exceeds maximum allowed limit of 10 MB."

    ext = os.path.splitext(filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        return False, f"Unsupported file extension '{ext}'. Allowed: JPG, JPEG, PNG, WEBP."

    if content_type and content_type.lower() not in ALLOWED_MIME_TYPES:
        # Warning only if extension is valid but browser mime type differs slightly
        pass

    return True, ""


def resolve_api_key(provided_key: Optional[str] = None) -> Optional[str]:
    """
    Resolves Gemini API key from parameter, Streamlit secrets, or environment variables.
    """
    if provided_key and provided_key.strip():
        return provided_key.strip()
    
    # Try streamlit secrets
    try:
        if "GEMINI_API_KEY" in st.secrets:
            return str(st.secrets["GEMINI_API_KEY"]).strip()
    except Exception:
        pass

    # Try environment variable
    env_key = os.environ.get("GEMINI_API_KEY")
    if env_key and env_key.strip():
        return env_key.strip()

    return None


def get_gemini_client(api_key: Optional[str] = None) -> genai.Client:
    """
    Instantiates google-genai Client with resolved API key.
    """
    key = resolve_api_key(api_key)
    if not key:
        raise ValueError(
            "Gemini API key is missing. Please set GEMINI_API_KEY in .streamlit/secrets.toml "
            "or enter your key in the app Settings."
        )
    return genai.Client(api_key=key)


def clean_json_response(raw_text: str) -> str:
    """
    Strips markdown code fence blocks (e.g. ```json ... ```) from raw Gemini response.
    """
    text = raw_text.strip()
    # Remove markdown code blocks if present
    match = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return text


def sanitize_extracted_data(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Ensures extracted receipt data matches expected structure and default types.
    """
    if not isinstance(data, dict):
        raise ValueError("Extraction output is not a JSON object.")

    # Normalize fields
    merchant = str(data.get("merchant") or "Unknown Merchant").strip()
    date_str = data.get("date")
    if not date_str or date_str == "null" or date_str == "None":
        date_str = None
    else:
        date_str = str(date_str).strip()

    currency = str(data.get("currency") or "USD").strip().upper()
    if len(currency) > 5:
        currency = "USD"

    payment_method = str(data.get("payment_method") or "Unknown").strip()
    notes = str(data.get("notes") or "").strip()
    suggested_category = str(data.get("suggested_category") or "Other").strip()

    def safe_float(val, default=0.0):
        if val is None:
            return default
        try:
            # Handle currency symbols if mistakenly included in numbers
            cleaned = re.sub(r"[^\d.-]", "", str(val))
            return float(cleaned) if cleaned else default
        except (ValueError, TypeError):
            return default

    subtotal = safe_float(data.get("subtotal"), 0.0)
    tax = safe_float(data.get("tax"), 0.0)
    discount = safe_float(data.get("discount"), 0.0)
    service_charge = safe_float(data.get("service_charge"), 0.0)
    final_total = safe_float(data.get("final_total"), 0.0)

    # Sanitize line items
    items_raw = data.get("items")
    sanitized_items = []

    if isinstance(items_raw, list):
        for item in items_raw:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "Unnamed Item").strip()
            qty = safe_float(item.get("quantity"), 1.0)
            if qty <= 0:
                qty = 1.0
            total_price = safe_float(item.get("total"), 0.0)
            unit_price = safe_float(item.get("unit_price"), 0.0)
            
            if total_price == 0.0 and unit_price > 0.0:
                total_price = round(unit_price * qty, 2)
            elif unit_price == 0.0 and total_price > 0.0:
                unit_price = round(total_price / qty, 2)

            cat = str(item.get("category") or suggested_category).strip()

            sanitized_items.append({
                "name": name,
                "quantity": float(qty),
                "unit_price": float(unit_price),
                "total": float(total_price),
                "category": cat
            })

    # If subtotal was 0, sum item totals
    if subtotal == 0.0 and sanitized_items:
        subtotal = round(sum(i["total"] for i in sanitized_items), 2)

    # If final_total is 0, calculate it
    if final_total == 0.0:
        final_total = round(subtotal + tax + service_charge - discount, 2)

    return {
        "merchant": merchant,
        "date": date_str,
        "currency": currency,
        "items": sanitized_items,
        "subtotal": float(subtotal),
        "tax": float(tax),
        "discount": float(discount),
        "service_charge": float(service_charge),
        "final_total": float(final_total),
        "payment_method": payment_method,
        "suggested_category": suggested_category,
        "notes": notes
    }


def extract_receipt_data(
    image_bytes: bytes,
    mime_type: str = "image/jpeg",
    api_key: Optional[str] = None,
    model_id: str = DEFAULT_MODEL_ID
) -> Dict[str, Any]:
    """
    Sends receipt image to Gemini AI Vision and extracts structured data.
    Raises descriptive exceptions on failure.
    """
    client = get_gemini_client(api_key)
    
    # Prepare image part for Gemini API
    image_part = types.Part.from_bytes(
        data=image_bytes,
        mime_type=mime_type
    )

    prompt = EXTRACTION_PROMPT

    config = types.GenerateContentConfig(
        system_instruction=SYSTEM_PROMPT,
        temperature=0.1,
        response_mime_type="application/json",
    )

    models_to_try = [model_id] + [m for m in FALLBACK_MODEL_IDS if m != model_id]
    
    last_error = None
    response_text = None

    for model in models_to_try:
        try:
            response = client.models.generate_content(
                model=model,
                contents=[image_part, prompt],
                config=config
            )
            response_text = response.text
            if response_text:
                break
        except APIError as e:
            last_error = f"Gemini API Error ({model}): {str(e)}"
        except Exception as e:
            last_error = f"Model execution error ({model}): {str(e)}"

    if not response_text:
        raise RuntimeError(last_error or "Failed to receive a response from Gemini API.")

    cleaned_text = clean_json_response(response_text)
    
    try:
        raw_data = json.loads(cleaned_text)
    except json.JSONDecodeError as e:
        raise ValueError(
            f"Failed to parse Gemini output as structured JSON. Raw text preview: {cleaned_text[:200]}..."
        ) from e

    return sanitize_extracted_data(raw_data)
