import base64

def encode_image(content: bytes) -> str:
    # Convert raw image bytes → base64 encoded string
    # Required because the OpenAI API expects images as base64 data URLs
    return base64.b64encode(content).decode("utf-8")