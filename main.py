from fastapi import FastAPI, File, UploadFile, Request
from fastapi.responses import HTMLResponse
from services.extractor import extract_book_metadata
from utils.image import encode_image
from services.sheets import save_to_sheets

# Initialize FastAPI app
app = FastAPI()


@app.get("/anklib")
def home():
    return {"message": "Welcome to Anklib API"}


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


# ✅ SINGLE confirm endpoint (removed duplicate)
@app.post("/anklib/confirm")
async def confirm(request: Request):
    """
    Receives user-edited metadata and saves it to Google Sheets.
    """
    data = await request.json()

    save_to_sheets(data)

    return {"status": "saved"}


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

                <label for="fileInput" class="upload-btn">
                    📸 Upload Image
                </label>

                <input id="fileInput" type="file" accept="image/*"
                       onchange="handleFileSelect()" style="display:none;">

                <img id="preview" style="display:none; max-width:100%; margin-top:10px;" />

                <button id="extractBtn" onclick="uploadFile()">Extract Metadata</button>

                <div id="resultBox" style="margin-top:20px;"></div>

                <button id="confirmBtn" onclick="confirmData()" style="display:none;">
                    Confirm & Save
                </button>
            </div>

            <script>

                function handleFileSelect() {
                    const file = document.getElementById('fileInput').files[0];
                    const preview = document.getElementById('preview');

                    if (file) {
                        preview.src = URL.createObjectURL(file);
                        preview.style.display = "block";
                    }
                }

                async function uploadFile() {

                    const file = document.getElementById('fileInput').files[0];

                    if (!file) {
                        alert("Select a file");
                        return;
                    }

                    const formData = new FormData();
                    formData.append("file", file);

                    const res = await fetch("/anklib/extract", {
                        method: "POST",
                        body: formData
                    });

                    const data = await res.json();
                    const book = data.data;

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

                    // 🆕 NEW FIELDS
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

                        // 🆕 NEW FIELDS
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