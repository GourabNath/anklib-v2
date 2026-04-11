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
    payload = await request.json()

    data = payload.get("data", {})
    user_email = payload.get("user_email")

    if not user_email:
        return {"status": "error", "message": "user_email is required"}

    user_email = user_email.strip().lower()  # NORMALIZE EMAIL

    save_to_sheets(data, user_email)

    import sys
    print("CONFIRM API HIT")
    sys.stdout.flush()

    return {
    "status": "saved",
    "debug": "API HIT"
}


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

            #statusBox {
                margin-top: 15px;
                font-size: 14px;
                color: #555;
            }

        </style>
    </head>

    <body>
        <div class="container">
            <h2>📚 Anklib</h2>

            <input id="userEmail" placeholder="Enter your email"
               style="margin-top:10px; padding:10px; width:100%; border-radius:8px; border:1px solid #ccc;" />

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

            <!-- ✅ NEW STATUS BOX -->
            <div id="statusBox"></div>


            <div id="progressContainer" style="margin-top:10px; display:none;">
                <div style="background:#ddd; border-radius:10px; overflow:hidden;">
                    <div id="progressBar" style="
                        height:10px;
                        width:0%;
                        background:#4CAF50;
                        transition: width 1s linear;
                    "></div>
                </div>
            </div>

            <div id="resultBox" style="margin-top:20px;"></div>

            <button id="confirmBtn" style="display:none;">
                Confirm & Save
            </button>

            <button id="resetBtn" onclick="resetApp()" style="display:none; background:#777;">
                🔄 Scan Next Book
            </button>
        </div>

        <script>
	
    let progressInterval = null;
    let progressValue = 0;
    let stream = null;
    let capturedImages = [];

    async function startCamera() {
        const video = document.getElementById("camera");
        const captureBtn = document.getElementById("captureBtn");

        // ✅ Stop existing stream before starting new one
        stopCamera();

        stream = await navigator.mediaDevices.getUserMedia({
            video: { facingMode: "environment" }
        });

        video.srcObject = stream;
        video.style.display = "block";
        captureBtn.style.display = "block";
    }

    // ✅ NEW: Stop camera function
    function stopCamera() {
        const video = document.getElementById("camera");
        const captureBtn = document.getElementById("captureBtn");

        if (stream) {
            stream.getTracks().forEach(track => track.stop());
            stream = null;
        }

        // Hide UI
        video.srcObject = null;
        video.style.display = "none";
        captureBtn.style.display = "none";
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


// ✅ [NEW] Progress bar
function startProgress() {
    const bar = document.getElementById("progressBar");
    const container = document.getElementById("progressContainer");

    progressValue = 0;
    bar.style.width = "0%";
    container.style.display = "block";

    progressInterval = setInterval(() => {
        // Slow, asymptotic progress
        if (progressValue < 90) {
            progressValue += Math.random() * 10; // random small increments
            if (progressValue > 90) progressValue = 90;
            bar.style.width = progressValue + "%";
        }
    }, 500);
}


function stopProgress() {
    clearInterval(progressInterval);

    const bar = document.getElementById("progressBar");

    // Jump to 100% only when done
    bar.style.width = "100%";

    setTimeout(() => {
        document.getElementById("progressContainer").style.display = "none";
    }, 400);
}
    
    async function uploadAll() {

    if (!capturedImages.length) {
        alert("Add images first");
        return;
    }

    // ✅ Stop camera when extracting
    stopCamera();

    startProgress(); // 👉 start here

    try {
        const formData = new FormData();

        capturedImages.forEach(file => {
            formData.append("files", file);
        });

        const res = await fetch("/anklib/extract-multiple", {
            method: "POST",
            body: formData
        });

        const data = await res.json();

        const reused = data.images_reused || 0;
        const total = data.images_processed || 0;
        const newProcessed = total - reused;

        let message = "";

        if (reused > 0) {
            message = `⚡ Reused ${reused} image(s), processed ${newProcessed} new image(s)`;
        } else {
            message = `Processed ${total} image(s)`;
        }

        document.getElementById("statusBox").innerText = message;

        displayResult(data.data);

    } catch (err) {
        console.error(err);
        document.getElementById("statusBox").innerText = "❌ Something went wrong";
    } finally {
        stopProgress(); // 👉 ALWAYS stops (success or error)
    }
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

    console.log("CONFIRM BUTTON CLICKED");

    const payload = {
        data: collectData(),
        user_email: document.getElementById("userEmail").value
    };

    if (!payload.user_email) {
        alert("Please enter your email");
        return;
    }

    localStorage.setItem("anklib_user_email", payload.user_email);

    const res = await fetch("/anklib/confirm", {
        method: "POST",
        headers: {
            "Content-Type": "application/json"
        },
        body: JSON.stringify(payload)
    });

    const data = await res.json();
    alert(data.debug || "Saved successfully!");
}


    function resetApp() {

        // ✅ Stop camera when resetting
        stopCamera();

        capturedImages = [];

        document.getElementById("previewContainer").innerHTML = "";
        document.getElementById("resultBox").innerHTML = "";
        document.getElementById("statusBox").innerText = "";

        document.getElementById("confirmBtn").style.display = "none";
        document.getElementById("resetBtn").style.display = "none";

        document.getElementById("fileInput").value = "";
    }


    // Load saved email on page load
window.onload = function () {
    const savedEmail = localStorage.getItem("anklib_user_email");
    if (savedEmail) {
        document.getElementById("userEmail").value = savedEmail;
    }
};

document.getElementById("confirmBtn").onclick = confirmData;

</script>
    </body>
    </html>
    """


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000)