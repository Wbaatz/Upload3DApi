from fastapi import FastAPI, File, UploadFile
import os
import shutil
import zipfile
import json
import subprocess
from pathlib import Path
from fastapi.middleware.cors import CORSMiddleware


app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],  # Explicitly allow React frontend
    allow_credentials=True,
    allow_methods=["*"],  # Allow all HTTP methods
    allow_headers=["*"],  # Allow all headers
)



BASE_DIR = os.path.dirname(os.path.abspath(__file__))  # Get the directory of main.py
UPLOAD_DIR = os.path.join(BASE_DIR, "Ecommerce_app", "public")  # Point to the public folder
os.makedirs(UPLOAD_DIR, exist_ok=True)
MODEL_DIR = "src/ThreeDModels"
PRODUCT_PAGE_PATH = "src/app/client/productGrid/product/ProductSlug/page.tsx"

def get_next_folder_name():
    """Find the next available 'objectX' folder name."""
    existing_folders = [f for f in os.listdir(UPLOAD_DIR) if f.startswith("object")]
    highest_index = max([int(f.replace("object", "")) for f in existing_folders if f.replace("object", "").isdigit()], default=0)
    return f"object{highest_index + 1}"

@app.post("/upload/")
async def upload_zip(file: UploadFile = File(...)):
    """Handle the uploaded ZIP file and process it."""
    folder_name = get_next_folder_name()
    object_path = os.path.join(UPLOAD_DIR, folder_name)
    os.makedirs(object_path, exist_ok=True)

    zip_path = os.path.join(object_path, file.filename)
    
    # Save the ZIP file
    with open(zip_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    # Extract ZIP file
    with zipfile.ZipFile(zip_path, "r") as zip_ref:
        zip_ref.extractall(object_path)

    # Rename files inside extracted folder
    gltf_file = os.path.join(object_path, "scene.gltf")
    bin_file = os.path.join(object_path, "scene.bin")
    new_gltf_file = os.path.join(object_path, "chair.gltf")
    new_bin_file = os.path.join(object_path, "chair.bin")

    if os.path.exists(gltf_file):
        os.rename(gltf_file, new_gltf_file)
    if os.path.exists(bin_file):
        os.rename(bin_file, new_bin_file)

    # Update chair.gltf file
    with open(new_gltf_file, "r") as f:
        gltf_data = json.load(f)
    
    if "buffers" in gltf_data:
        gltf_data["buffers"][0]["uri"] = "chair.bin"
    
    with open(new_gltf_file, "w") as f:
        json.dump(gltf_data, f, indent=2)

    # Run gltfjsx command
    try:
        subprocess.run(["npx", "gltfjsx", "chair.gltf"], cwd=object_path, check=True)
    except subprocess.CalledProcessError as e:
        return {"error": f"GLTF JSX conversion failed: {e}"}

    # Move generated Chair.jsx to model directory
    generated_jsx_path = os.path.join(object_path, "Chair.jsx")
    target_jsx_path = os.path.join(MODEL_DIR, "Chair.jsx")

    if os.path.exists(generated_jsx_path):
        shutil.move(generated_jsx_path, target_jsx_path)

    # Modify page.tsx to import and use Chair
    with open(PRODUCT_PAGE_PATH, "r") as f:
        page_content = f.read()

    new_import = "import {Model as Chair} from '@/model/Chair';\n"
    chair_component = "<Suspense fallback={null}>\n    <Chair scale={0.014} />\n</Suspense>\n"

    if new_import not in page_content:
        page_content = new_import + page_content

    if "Suspense" in page_content:
        page_content = page_content.replace("<Suspense fallback={null}>", f"<Suspense fallback={{null}}>\n{chair_component}")

    with open(PRODUCT_PAGE_PATH, "w") as f:
        f.write(page_content)

    # Modify Chair.jsx to update paths
    if os.path.exists(target_jsx_path):
        with open(target_jsx_path, "r") as f:
            chair_content = f.read()

        chair_content = chair_content.replace("useGLTF('/chair.gltf')", f"useGLTF('/{folder_name}/chair.gltf')")
        chair_content = chair_content.replace("useGLTF.preload('/chair.gltf')", f"useGLTF.preload('/{folder_name}/chair.gltf')")

        with open(target_jsx_path, "w") as f:
            f.write(chair_content)

    return {"message": "Upload and processing completed successfully", "folder": folder_name}
