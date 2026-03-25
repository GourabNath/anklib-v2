from openai import OpenAI
import json
import re

# Initialize OpenAI client (uses API key from environment)
client = OpenAI()

def clean_isbn(isbn):
    # Return None if ISBN is missing or empty
    if not isbn:
        return None
    # Remove all non-numeric characters (except X/x for ISBN-10)
    # This standardizes ISBN for consistency and downstream usage
    return re.sub(r"[^0-9Xx]", "", isbn)


def extract_book_metadata(image_b64: str):

    # Send image + structured extraction instructions to the LLM
    # Base64 encoding is required to embed the image in the request
    response = client.responses.create(
        model="gpt-5.2",
        input=[
            {
                "role": "user",
                "content": [
                    {
                        # Instruction prompt guiding the model to return structured JSON
                        "type": "input_text",
                        "text": """
You are extracting structured metadata from a book image.

Extract the following fields:
- title
- author
- publisher
- isbn
- edition
- price


Rules:
- Return ONLY valid JSON (no markdown, no explanations)
- If a field is not visible, return null
- Do not guess or hallucinate
- Prefer clearly printed text (ignore blur/noise)
- If multiple authors exist, return as a comma-separated string

Field-specific rules:
- isbn: Extract ISBN-10 or ISBN-13 (numbers only, remove dashes/spaces)
- edition: Capture edition info like "2nd Edition", "Third Edition"
- price: Capture price with currency if visible (e.g., "₹499", "$20")

Output format:
{
  "title": "...",
  "author": "...",
  "publisher": "...",
  "isbn": "...",
  "edition": "...",
  "price": "..."
}
"""
                    },
                    {
                        # Attach image as base64 data URL for multimodal processing
                        "type": "input_image",
                        "image_url": f"data:image/jpeg;base64,{image_b64}"
                    }
                ]
            }
        ]
    )

    try:
        # Extract raw text output from model response
        text = response.output_text.strip()

        # Handle cases where model wraps JSON in markdown (```json ... ```)
        if text.startswith("```"):
            text = text.replace("```json", "").replace("```", "").strip()

        # Parse string output into Python dictionary
        data = json.loads(text)

        # Ensure all expected fields exist (even if missing in output)
        # This keeps API response consistent
        for field in ["title", "author", "publisher", "isbn", "edition", "price"]:
            data.setdefault(field, None)

        # Normalize ISBN to remove formatting inconsistencies
        data["isbn"] = clean_isbn(data.get("isbn"))

    except Exception:
        # Fallback: return raw model output if JSON parsing fails
        # Prevents API from crashing and helps debugging
        data = {"raw_output": response.output_text}

    return data