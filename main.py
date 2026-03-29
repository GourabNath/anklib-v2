from fastapi import FastAPI, File, UploadFile, Request
from fastapi.responses import HTMLResponse
from typing import List

from services.extractor import extract_book_metadata
from utils.image import encode_image
from services.sheets import save_to_sheets

# Initialize FastAPI app
app = FastAPI()


@app.get("/anklib")
def home():
    return {"message": "Welcome to Anklib API"}


# -------------------------------
# 🔹 SINGLE IMAGE (existing)
# -------------------------------
@app.post("/anklib/extract")
async def extract(file: UploadFile = File(...)):

    if not file.content_type.startswith("image/"):
        return {"error": "Only image files are supported"}

    try:
        content = await file.read()
        image_b64 = encode_image(content)
        result = extract_book_metadata(image_b64)

        return {
            "status": "success",
            "data": result
        }

    except Exception as e:
        return {
            "status": "error",
            "message": str(e)
        }


# -------------------------------
# 🔥 NEW: MULTI-IMAGE EXTRACTION
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

    try:
        results = []

        for file in files:
            if not file.content_type.startswith("image/"):
                continue

            content = await file.read()
            image_b64 = encode_image(content)

            result = extract_book_metadata(image_b64)
            results.append(result)

        if not results:
            return {"status": "error", "message": "No valid images uploaded"}

        merged = merge_metadata(results)

        return {
            "status": "success",
            "data": merged,
            "images_processed": len(results)
        }

    except Exception as e:
        return {
            "status": "error",
            "message": str(e)
        }


# -------------------------------
# ✅ CONFIRM (unchanged)
# -------------------------------
@app.post("/anklib/confirm")
async def confirm(request: Request):
    """
    Receives user-edited metadata and saves it to Google Sheets.
    """
    data = await request.json()
    save_to_sheets(data)

    return {"status": "saved"}


# -------------------------------
# 🎨 UI (UPDATED for multi-upload)
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

                <!-- 📸 CAMERA -->
                <button onclick="startCamera()">📸 Open Camera</button>

                <video id="camera" autoplay playsinline style="display:none; width:100%; margin-top:10px;"></video>
                <canvas id="canvas" style="display:none;"></canvas>

                <button id="captureBtn" onclick="capturePhoto()" style="display:none;">
                    Capture Photo
                </button>

                <!-- 📁 MULTI UPLOAD -->
                <label for="fileInput" class="upload-btn">
                    📁 Upload Images (Multiple)
                </label>

                <input id="fileInput" type="file" accept="image/*" multiple
                       onchange="handleFileSelect()" style="display:none;">

                <div id="previewContainer"></div>

                <button id="extractBtn" onclick="uploadFile()">Extract Metadata</button>

                <div id="resultBox" style="margin-top:20px;"></div>

                <button id="confirmBtn" onclick="confirmData()" style="display:none;">
                    Confirm & Save
                </button>
            </div>

            <script>

                let stream;

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

                    canvas.toBlob(async function(blob) {
                        const file = new File([blob], "capture.jpg", { type: "image/jpeg" });

                        const formData = new FormData();
                        formData.append("file", file);

                        const res = await fetch("/anklib/extract", {
                            method: "POST",
                            body: formData
                        });

                        const data = await res.json();
                        displayResult(data.data);

                        stopCamera();
                    });
                }

                function stopCamera() {
                    if (stream) {
                        stream.getTracks().forEach(track => track.stop());
                    }
                    document.getElementById("camera").style.display = "none";
                    document.getElementById("captureBtn").style.display = "none";
                }

                function handleFileSelect() {
                    const files = document.getElementById('fileInput').files;
                    const container = document.getElementById('previewContainer');
                    container.innerHTML = "";

                    for (let i = 0; i < files.length; i++) {
                        const img = document.createElement("img");
                        img.src = URL.createObjectURL(files[i]);
                        img.style.maxWidth = "100px";
                        img.style.margin = "5px";
                        container.appendChild(img);
                    }
                }

                async function uploadFile() {

                    const files = document.getElementById('fileInput').files;

                    if (!files.length) {
                        alert("Select at least one image");
                        return;
                    }

                    const formData = new FormData();

                    for (let i = 0; i < files.length; i++) {
                        formData.append("files", files[i]);
                    }

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

                    const res = await fetch("/anklib/confirm", {
                        method: "POST",
                        headers: {
                            "Content-Type": "application/json"
                        },
                        body: JSON.stringify(payload)
                    });

                    await res.json();

                    alert("✅ Saved successfully!");
                }

            </script>
        </body>
    </html>
    """


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000)