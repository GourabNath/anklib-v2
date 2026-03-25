# anklib
anklib (Ankita’s Library) is a simple system to extract book metadata from images.

# Goal
Allow a user to upload images of a book (cover, ISBN page, etc.) and automatically extract:

* Title
* Author
* Publisher


## How it works (high level)
1. User uploads an image
2. Backend API receives the image
3. Image is processed using an LLM
4. Structured metadata is returned


## API Design (current)
* `GET /anklib` → Health check
* `POST /anklib/extract` → Upload image and extract metadata


## Status
* Step 0: Basic FastAPI setup ✅
* Step 1: Image upload (next)



