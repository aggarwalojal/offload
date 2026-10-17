"""
Gemini API Client integration for TimeSlice AI Agent.
Handles communication with Google Gemini using google-genai SDK.
"""

import os
import json
import re
from typing import Dict, Any, Optional
from dotenv import load_dotenv

load_dotenv()


def get_api_key() -> str:
    key = os.getenv("GEMINI_API_KEY")
    if not key:
        raise ValueError(
            "GEMINI_API_KEY environment variable is not set. "
            "Please obtain an API key from https://aistudio.google.com/ and set it in backend/.env"
        )
    return key


def call_gemini(system_instruction: str, prompt: str, model_name: str = "gemini-2.5-flash") -> Dict[str, Any]:
    """
    Calls Gemini API with structured JSON output instructions.
    Returns parsed dictionary from Gemini response.
    """
    api_key = get_api_key()

    # Try modern google-genai SDK first
    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=api_key)
        config = types.GenerateContentConfig(
            system_instruction=system_instruction,
            response_mime_type="application/json",
            temperature=0.1,
        )
        response = client.models.generate_content(
            model=model_name,
            contents=prompt,
            config=config,
        )
        raw_text = response.text or "{}"
    except ImportError:
        # Fallback to google-generativeai legacy package if installed
        import google.generativeai as genai_legacy

        genai_legacy.configure(api_key=api_key)
        model = genai_legacy.GenerativeModel(
            model_name=model_name,
            system_instruction=system_instruction,
            generation_config={"response_mime_type": "application/json", "temperature": 0.1},
        )
        response = model.generate_content(prompt)
        raw_text = response.text or "{}"

    # Clean and parse JSON
    cleaned = raw_text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)

    return json.loads(cleaned)
