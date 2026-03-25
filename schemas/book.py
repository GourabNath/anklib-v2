from pydantic import BaseModel
from typing import Optional

# Pydantic model defining the structure of extracted book metadata
# Used for validation and ensuring consistent API response format
class BookMetadata(BaseModel):

    # Book title (may be missing if not visible in image)
    title: Optional[str]

    # Author name(s), comma-separated if multiple authors exist
    author: Optional[str]

    # Publisher name extracted from the book image
    publisher: Optional[str]

    # ISBN number (normalized to remove dashes/spaces)
    isbn: Optional[str]

    # Edition information (e.g., "2nd Edition", "Third Edition")
    edition: Optional[str]

    # Price with currency symbol if available (e.g., "₹499", "$20")
    price: Optional[str]