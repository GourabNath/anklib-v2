from fastapi import FastAPI, File, UploadFile, Request
from fastapi.responses import HTMLResponse
from typing import List
import hashlib  # ✅ NEW: for image hashing

from services.extractor import extract_book_metadata
from utils.image import encode_image
from services.sheets import save_to_sheets

app = FastAPI()

# --------------------------------------------------
# ✅ In-memory cache
# --------------------------------------------------
IMAGE_CACHE = {}


def get_image_hash(content: bytes) -> str:
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
    final = {}

    for res in results:
        for key, value in res.items():
            if key not in final or not final[key]:
                final[key] = value

    return final


@app.post("/anklib/extract-multiple")
async def extract_multiple(files: List[UploadFile] = File(...)):

    results = []
    reused_count = 0

    for file in files:
        if not file.content_type.startswith("image/"):
            continue

        content = await file.read()
        image_hash = get_image_hash(content)

        if image_hash in IMAGE_CACHE:
            result = IMAGE_CACHE[image_hash]
            reused_count += 1
        else:
            image_b64 = encode_image(content)
            result = extract_book_metadata(image_b64)
            IMAGE_CACHE[image_hash] = result

        results.append(result)

    if not results:
        return {"status": "error", "message": "No valid images"}

    merged = merge_metadata(results)

    return {
        "status": "success",
        "data": merged,
        "images_processed": len(results),
        "images_reused": reused_count
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
            body { font-family: Arial; background: #f5f5f5; text-align: center; padding: 20px; }
            .container { background: white; padding: 25px; border-radius: 12px; max-width: 500px; margin: auto; }
            button { background: #4CAF50; color: white; padding: 14px; border: none; border-radius: 8px; width: 100%; margin-top: 10px; cursor: pointer; }
            .upload-btn { display: block; background: #2196F3; color: white; padding: 14px; border-radius: 8px; cursor: pointer; margin-top: 10px; }
            #previewContainer { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; margin-top: 10px; }
            #previewContainer img { width: 100%; border-radius: 6px; }
            input { width: 100%; padding: 8px; margin-top: 5px; border-radius: 6px; border: 1px solid #ccc; }
            .field-block { margin-bottom: 15px; text-align: left; }
            .field-label { font-size: 12px; color: #777; }
            #statusBox { margin-top: 15px; font-size: 14px; color: #555; }
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

            <label for="fileInput" class="upload-btn">📁 Upload Images</label>
            <input id="fileInput" type="file" accept="image/*" multiple onchange="handleFileSelect()" style="display:none;">

            <div id="previewContainer"></div>

            <button onclick="uploadAll()">Extract Metadata</button>

            <div id="statusBox"></div>

            <!-- ✅ Progress Bar -->
            <div id="progressContainer" style="display:none; margin-top:10px;">
                <div style="width:100%; background:#ddd; border-radius:6px;">
                    <div id="progressBar" style="width:0%; height:10px; background:#4CAF50; border-radius:6px;"></div>
                </div>
            </div>

            <div id="resultBox" style="margin-top:20px;"></div>

            <button id="confirmBtn" onclick="confirmData()" style="display:none;">Confirm & Save</button>
            <button id="resetBtn" onclick="resetApp()" style="display:none; background:#777;">🔄 Scan Next Book</button>
        </div>

        <script>
            let stream = null;
            let capturedImages = [];
            let progressInterval;

            function stopCamera() {
                const video = document.getElementById("camera");
                const captureBtn = document.getElementById("captureBtn");

                if (stream) {
                    stream.getTracks().forEach(track => track.stop());
                    stream = null;
                }

                video.srcObject = null;
                video.style.display = "none";
                captureBtn.style.display = "none";
            }

            async function startCamera() {
                stopCamera();

                const video = document.getElementById("camera");
                const captureBtn = document.getElementById("captureBtn");

                stream = await navigator.mediaDevices.getUserMedia({
                    video: { facingMode: "environment" }
                });

                video.srcObject = stream;
                video.style.display = "block";
                captureBtn.style.display = "block";
            }

            function startFakeProgress() {
                const container = document.getElementById("progressContainer");
                const bar = document.getElementById("progressBar");

                container.style.display = "block";
                bar.style.width = "0%";

                let progress = 0;

                progressInterval = setInterval(() => {
                    if (progress < 90) {
                        progress += Math.random() * 10;
                        bar.style.width = progress + "%";
                    }
                }, 300);
            }

            function completeProgress() {
                const bar = document.getElementById("progressBar");

                clearInterval(progressInterval);
                bar.style.width = "100%";

                setTimeout(() => {
                    document.getElementById("progressContainer").style.display = "none";
                }, 500);
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
                    const img = document.createElement("img");
                    img.src = URL.createObjectURL(file);
                    container.appendChild(img);
                });
            }

            async function uploadAll() {
                if (!capturedImages.length) {
                    alert("Add images first");
                    return;
                }

                stopCamera();

                document.getElementById("statusBox").innerText = "⏳ Extracting metadata...";
                startFakeProgress();

                const formData = new FormData();
                capturedImages.forEach(file => formData.append("files", file));

                const res = await fetch("/anklib/extract-multiple", {
                    method: "POST",
                    body: formData
                });

                const data = await res.json();

                completeProgress();

                document.getElementById("statusBox").innerText = "✅ Extraction complete";

                displayResult(data.data);
            }

            function displayResult(book) {
                document.getElementById("resultBox").innerHTML = JSON.stringify(book, null, 2);
                document.getElementById("confirmBtn").style.display = "block";
                document.getElementById("resetBtn").style.display = "block";
            }

            function resetApp() {
                stopCamera();
                capturedImages = [];
                document.getElementById("previewContainer").innerHTML = "";
                document.getElementById("resultBox").innerHTML = "";
                document.getElementById("statusBox").innerText = "";
                document.getElementById("confirmBtn").style.display = "none";
                document.getElementById("resetBtn").style.display = "none";
            }

            async function confirmData() {
                alert("Saved!");
            }
        </script>
    </body>
    </html>
    """

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000)