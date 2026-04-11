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


@app.get("/anklib/get-sheet")
def get_sheet(email: str):
    from services.sheets import load_user_map

    user_map = load_user_map()

    if email in user_map:
        sheet_id = user_map[email]
        return {
            "status": "found",
            "url": f"https://docs.google.com/spreadsheets/d/{sheet_id}"
        }

    return {"status": "not_found"}

# -------------------------------
# CONFIRM
# -------------------------------
@app.post("/anklib/confirm")
async def confirm(request: Request):
    data = await request.json()
    user_email = data.get("user_email")
    save_to_sheets(data, user_email)
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
                font-size: 14px;
            }

            .secondary {
                background: #555;
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
                padding: 12px;
                margin-top: 10px;
                border-radius: 6px;
                border: 1px solid #ccc;
                font-size: 14px;
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

            #statusBox {
                margin-top: 15px;
                font-size: 14px;
                color: #555;
            }

            #resultBox {
                margin-top: 20px;
                text-align: left;
                font-size: 12px;
                background: #fafafa;
                padding: 10px;
                border-radius: 6px;
                white-space: pre-wrap;
            }
        </style>
    </head>

    <body>
        <div class="container">
            <h2>📚 Anklib</h2>

            <!-- EMAIL -->
            <input id="emailInput" type="email" placeholder="Enter your email" />

            <button onclick="openSheet()">📄 Open My Sheet</button>

            <!-- CAMERA -->
            <button onclick="startCamera()">📸 Open Camera</button>

            <video id="camera" autoplay playsinline style="display:none; width:100%; margin-top:10px;"></video>
            <canvas id="canvas" style="display:none;"></canvas>

            <button id="captureBtn" onclick="capturePhoto()" style="display:none;">
                Capture Photo
            </button>

            <!-- UPLOAD -->
            <label for="fileInput" class="upload-btn">📁 Upload Images</label>
            <input id="fileInput" type="file" accept="image/*" multiple onchange="handleFiles()" style="display:none;">

            <div id="previewContainer"></div>

            <button onclick="extractData()">Extract Metadata</button>

            <div id="statusBox"></div>

            <!-- PROGRESS -->
            <div id="progressContainer" style="display:none; margin-top:10px;">
                <div style="width:100%; background:#ddd; border-radius:6px;">
                    <div id="progressBar" style="width:0%; height:10px; background:#4CAF50;"></div>
                </div>
            </div>

            <div id="resultBox"></div>

            <button id="confirmBtn" onclick="saveData()" style="display:none;">
                Confirm & Save
            </button>

            <button id="resetBtn" onclick="resetApp()" class="secondary" style="display:none;">
                🔄 Scan Next Book
            </button>
        </div>

        <script>
            let stream = null;
            let images = [];
            let progressTimer;

            function stopCamera() {
                if (stream) {
                    stream.getTracks().forEach(track => track.stop());
                    stream = null;
                }
                document.getElementById("camera").style.display = "none";
                document.getElementById("captureBtn").style.display = "none";
            }

            async function startCamera() {
                stopCamera();

                stream = await navigator.mediaDevices.getUserMedia({
                    video: { facingMode: "environment" }
                });

                const video = document.getElementById("camera");
                video.srcObject = stream;
                video.style.display = "block";
                document.getElementById("captureBtn").style.display = "block";
            }

            function capturePhoto() {
                const video = document.getElementById("camera");
                const canvas = document.getElementById("canvas");

                canvas.width = video.videoWidth;
                canvas.height = video.videoHeight;

                const ctx = canvas.getContext("2d");
                ctx.drawImage(video, 0, 0);

                canvas.toBlob(blob => {
                    const file = new File([blob], "photo.jpg", { type: "image/jpeg" });
                    images.push(file);
                    renderPreview();
                });
            }

            function handleFiles() {
                const files = document.getElementById("fileInput").files;
                for (let i = 0; i < files.length; i++) {
                    images.push(files[i]);
                }
                renderPreview();
            }

            function renderPreview() {
                const container = document.getElementById("previewContainer");
                container.innerHTML = "";

                images.forEach(file => {
                    const img = document.createElement("img");
                    img.src = URL.createObjectURL(file);
                    container.appendChild(img);
                });
            }

            function startProgress() {
                const bar = document.getElementById("progressBar");
                document.getElementById("progressContainer").style.display = "block";

                let progress = 0;

                progressTimer = setInterval(() => {
                    if (progress < 90) {
                        progress += Math.random() * 10;
                        bar.style.width = progress + "%";
                    }
                }, 300);
            }

            function stopProgress() {
                clearInterval(progressTimer);
                document.getElementById("progressBar").style.width = "100%";

                setTimeout(() => {
                    document.getElementById("progressContainer").style.display = "none";
                }, 500);
            }

            async function extractData() {
                if (!images.length) {
                    alert("Add images first");
                    return;
                }

                stopCamera();
                startProgress();

                document.getElementById("statusBox").innerText = "Extracting...";

                const formData = new FormData();
                images.forEach(f => formData.append("files", f));

                const res = await fetch("/anklib/extract-multiple", {
                    method: "POST",
                    body: formData
                });

                const data = await res.json();

                stopProgress();

                document.getElementById("statusBox").innerText = "Done";

                document.getElementById("resultBox").innerText =
                    JSON.stringify(data.data, null, 2);

                document.getElementById("confirmBtn").style.display = "block";
                document.getElementById("resetBtn").style.display = "block";
            }

            async function saveData() {
                const email = document.getElementById("emailInput").value;

                if (!email) {
                    alert("Enter your email first");
                    return;
                }

                const data = JSON.parse(document.getElementById("resultBox").innerText);
                data["user_email"] = email;

                await fetch("/anklib/confirm", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify(data)
                });

                alert("Saved to your sheet!");
            }

            async function openSheet() {
                const email = document.getElementById("emailInput").value;

                if (!email) {
                    alert("Enter your email first");
                    return;
                }

                const res = await fetch(`/anklib/get-sheet?email=${email}`);
                const data = await res.json();

                if (data.status === "found") {
                    window.open(data.url, "_blank");
                } else {
                    alert("No sheet yet. Save once to create it.");
                }
            }

            function resetApp() {
                stopCamera();
                images = [];
                document.getElementById("previewContainer").innerHTML = "";
                document.getElementById("resultBox").innerText = "";
                document.getElementById("statusBox").innerText = "";
                document.getElementById("confirmBtn").style.display = "none";
                document.getElementById("resetBtn").style.display = "none";
            }
        </script>
    </body>
    </html>
    """

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000)