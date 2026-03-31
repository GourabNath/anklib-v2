from fastapi import FastAPI, File, UploadFile, Request
from fastapi.responses import HTMLResponse
from typing import List
import hashlib  # ✅ NEW: for image hashing

from services.extractor import extract_book_metadata
from utils.image import encode_image
from services.sheets import save_to_sheets

app = FastAPI()

# --------------------------------------------------
# ✅ NEW: In-memory cache for image-level results
# Key   = image hash
# Value = extracted metadata
# --------------------------------------------------
IMAGE_CACHE = {}


def get_image_hash(content: bytes) -> str:
    """
    Generate a unique hash for an image.
    Used to identify duplicate images across uploads.
    """
    return hashlib.md5(content).hexdigest()


@app.get("/anklib")
def home():
    return {"message": "Welcome to Anklib API"}


# -------------------------------
# SINGLE IMAGE
# -------------------------------
@app.post("/anklib/extract")
async def extract(file: UploadFile = File(...)):

    if not file.content_type.startswith("image/"):
        return {"error": "Only image files are supported"}

    content = await file.read()
    image_b64 = encode_image(content)
    result = extract_book_metadata(image_b64)

    return {"status": "success", "data": result}


# -------------------------------
# MULTI IMAGE
# -------------------------------
def merge_metadata(results):
    """
    Merge metadata from multiple images.
    Strategy: first non-empty value wins.
    """
    final = {}

    for res in results:
        for key, value in res.items():
            if key not in final or not final[key]:
                final[key] = value

    return final


@app.post("/anklib/extract-multiple")
async def extract_multiple(files: List[UploadFile] = File(...)):

    results = []
    reused_count = 0  # ✅ Track cache hits

    for file in files:
        if not file.content_type.startswith("image/"):
            continue

        content = await file.read()

        # ✅ Step 1: Generate hash for the image
        image_hash = get_image_hash(content)

        # ✅ Step 2: Check cache
        if image_hash in IMAGE_CACHE:
            result = IMAGE_CACHE[image_hash]
            reused_count += 1
        else:
            # ✅ Step 3: Run extraction only if not cached
            image_b64 = encode_image(content)
            result = extract_book_metadata(image_b64)

            # ✅ Step 4: Store in cache
            IMAGE_CACHE[image_hash] = result

        results.append(result)

    if not results:
        return {"status": "error", "message": "No valid images"}

    merged = merge_metadata(results)

    return {
        "status": "success",
        "data": merged,
        "images_processed": len(results),
        "images_reused": reused_count  # ✅ helpful for debugging / UX later
    }



# -------------------------------
# CONFIRM
# -------------------------------
@app.post("/anklib/confirm")
async def confirm(request: Request):
    data = await request.json()
    save_to_sheets(data)
    return {"status": "saved"}


# -------------------------------
# UI
# -------------------------------
@app.get("/", response_class=HTMLResponse)
def ui():
    return """
    <html>
    <head>
        <title>Anklib</title>
        <meta name="viewport" content="width=device-width, initial-scale=1.0">

        <style>
            body {
                font-family: Arial;
                background: #f5f5f5;
                text-align: center;
                padding: 20px;
            }

            .container {
                background: white;
                padding: 25px;
                border-radius: 12px;
                max-width: 500px;
                margin: auto;
            }

            button {
                background: #4CAF50;
                color: white;
                padding: 14px;
                border: none;
                border-radius: 8px;
                width: 100%;
                margin-top: 10px;
                cursor: pointer;
            }

            .upload-btn {
                display: block;
                background: #2196F3;
                color: white;
                padding: 14px;
                border-radius: 8px;
                cursor: pointer;
                margin-top: 10px;
            }

            #previewContainer {
                display: grid;
                grid-template-columns: repeat(3, 1fr);
                gap: 8px;
                margin-top: 10px;
            }

            #previewContainer img {
                width: 100%;
                border-radius: 6px;
            }

            input {
                width: 100%;
                padding: 8px;
                margin-top: 5px;
                border-radius: 6px;
                border: 1px solid #ccc;
            }

            .field-block {
                margin-bottom: 15px;
                text-align: left;
            }

            .field-label {
                font-size: 12px;
                color: #777;
            }
        </style>
    </head>

    <body>
        <div class="container">
            <h2>📚 Anklib</h2>

            <button onclick="startCamera()">📸 Open Camera</button>

            <video id="camera" autoplay playsinline style="display:none; width:100%; margin-top:10px;"></video>
            <canvas id="canvas" style="display:none;"></canvas>

            <button id="captureBtn" onclick="capturePhoto()" style="display:none;">
                Capture Photo
            </button>

            <label for="fileInput" class="upload-btn">
                📁 Upload Images
            </label>

            <input id="fileInput" type="file" accept="image/*" multiple
                   onchange="handleFileSelect()" style="display:none;">

            <div id="previewContainer"></div>

            <button onclick="uploadAll()">Extract Metadata</button>

            <div id="resultBox" style="margin-top:20px;"></div>

            <button id="confirmBtn" onclick="confirmData()" style="display:none;">
                Confirm & Save
            </button>

            <button id="resetBtn" onclick="resetApp()" style="display:none; background:#777;">
                🔄 Scan Next Book
            </button>
        </div>

        <script>

            let stream;
            let capturedImages = [];

            async function startCamera() {
                const video = document.getElementById("camera");
                const captureBtn = document.getElementById("captureBtn");

                stream = await navigator.mediaDevices.getUserMedia({
                    video: { facingMode: "environment" }
                });

                video.srcObject = stream;
                video.style.display = "block";
                captureBtn.style.display = "block";
            }

            function capturePhoto() {
                const video = document.getElementById("camera");
                const canvas = document.getElementById("canvas");

                canvas.width = video.videoWidth;
                canvas.height = video.videoHeight;

                const ctx = canvas.getContext("2d");
                ctx.drawImage(video, 0, 0);

                canvas.toBlob(function(blob) {
                    const file = new File([blob], "capture.jpg", { type: "image/jpeg" });
                    capturedImages.push(file);
                    renderPreview();
                });
            }

            function handleFileSelect() {
                const files = document.getElementById('fileInput').files;

                for (let i = 0; i < files.length; i++) {
                    capturedImages.push(files[i]);
                }

                renderPreview();
            }

            function renderPreview() {
                const container = document.getElementById('previewContainer');
                container.innerHTML = "";

                capturedImages.forEach((file, index) => {

                    const wrapper = document.createElement("div");
                    wrapper.style.position = "relative";

                    const img = document.createElement("img");
                    img.src = URL.createObjectURL(file);

                    const removeBtn = document.createElement("div");
                    removeBtn.innerHTML = "✕";
                    removeBtn.style.position = "absolute";
                    removeBtn.style.top = "4px";
                    removeBtn.style.right = "6px";
                    removeBtn.style.background = "rgba(0,0,0,0.6)";
                    removeBtn.style.color = "white";
                    removeBtn.style.borderRadius = "50%";
                    removeBtn.style.width = "20px";
                    removeBtn.style.height = "20px";
                    removeBtn.style.fontSize = "12px";
                    removeBtn.style.display = "flex";
                    removeBtn.style.alignItems = "center";
                    removeBtn.style.justifyContent = "center";
                    removeBtn.style.cursor = "pointer";

                    removeBtn.onclick = () => removeImage(index);

                    wrapper.appendChild(img);
                    wrapper.appendChild(removeBtn);

                    container.appendChild(wrapper);
                });
            }

            function removeImage(index) {
                capturedImages.splice(index, 1);
                renderPreview();
            }

            async function uploadAll() {

                if (!capturedImages.length) {
                    alert("Add images first");
                    return;
                }

                const formData = new FormData();

                capturedImages.forEach(file => {
                    formData.append("files", file);
                });

                const res = await fetch("/anklib/extract-multiple", {
                    method: "POST",
                    body: formData
                });

                const data = await res.json();
                displayResult(data.data);
            }

            function displayResult(book) {

                function field(label, value) {
                    return `
                        <div class="field-block">
                            <div class="field-label">${label}</div>
                            <input id="${label}" value="${value || ""}">
                        </div>
                    `;
                }

                let html = "";

                html += field("Title", book.title);
                html += field("Author", book.author);
                html += field("Publisher", book.publisher);
                html += field("ISBN", book.isbn);
                html += field("Edition", book.edition);
                html += field("Price", book.price);
                html += field("Accession Number", book.accession_number);
                html += field("Number of Pages", book.number_of_pages);

                document.getElementById("resultBox").innerHTML = html;
                document.getElementById("confirmBtn").style.display = "block";
                document.getElementById("resetBtn").style.display = "block";
            }

            function collectData() {
                return {
                    title: document.getElementById("Title")?.value,
                    author: document.getElementById("Author")?.value,
                    publisher: document.getElementById("Publisher")?.value,
                    isbn: document.getElementById("ISBN")?.value,
                    edition: document.getElementById("Edition")?.value,
                    price: document.getElementById("Price")?.value,
                    accession_number: document.getElementById("Accession Number")?.value,
                    number_of_pages: document.getElementById("Number of Pages")?.value
                };
            }

            async function confirmData() {

                const payload = collectData();

                await fetch("/anklib/confirm", {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json"
                    },
                    body: JSON.stringify(payload)
                });

                alert("✅ Saved successfully!");
            }

            function resetApp() {

                capturedImages = [];

                document.getElementById("previewContainer").innerHTML = "";
                document.getElementById("resultBox").innerHTML = "";

                document.getElementById("confirmBtn").style.display = "none";
                document.getElementById("resetBtn").style.display = "none";

                document.getElementById("fileInput").value = "";
            }

        </script>
    </body>
    </html>
    """


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000)