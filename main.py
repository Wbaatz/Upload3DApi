from fastapi import FastAPI, File, UploadFile
import os
import shutil
import zipfile
import json
import subprocess
from pathlib import Path
from fastapi.middleware.cors import CORSMiddleware
import re
app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, "ecommerce_next", "public")
os.makedirs(UPLOAD_DIR, exist_ok=True)
MODEL_DIR = "ecommerce_next/src/ThreeDModels"
PRODUCT_PAGE_PATH = "ecommerce_next/src/app/(client)/(productGrid)/product/[ProductSlug]/page.tsx"

def get_next_folder_name():
    existing_folders = [f for f in os.listdir(UPLOAD_DIR) if f.startswith("object")]
    highest_index = max([int(f.replace("object", "")) for f in existing_folders if f.replace("object", "").isdigit()], default=0)
    return f"object{highest_index + 1}"

@app.post("/upload/")
async def upload_zip(file: UploadFile = File(...)):
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
    new_gltf_file = os.path.join(object_path, "Obj.gltf")
    new_bin_file = os.path.join(object_path, "Obj.bin")

    if os.path.exists(gltf_file):
        os.rename(gltf_file, new_gltf_file)
    if os.path.exists(bin_file):
        os.rename(bin_file, new_bin_file)

    # Update Obj.gltf file
    with open(new_gltf_file, "r") as f:
        gltf_data = json.load(f)
    
    if "buffers" in gltf_data:
        gltf_data["buffers"][0]["uri"] = "Obj.bin"
    
    with open(new_gltf_file, "w") as f:
        json.dump(gltf_data, f, indent=2)
    
    # Generate Obj.jsx temporarily using gltfjsx
    NPX_PATH = shutil.which("npx")
    temp_jsx_path = os.path.join(object_path, "Obj.jsx")
    if NPX_PATH:
        try:
            subprocess.run([NPX_PATH, "gltfjsx", "Obj.gltf"], cwd=object_path, check=True)
        except subprocess.CalledProcessError as e:
            return {"error": f"GLTF JSX conversion failed: {e}"}
    else:
        return {"error": "npx not found on the system! Make sure Node.js is installed."}

    # Extract outer <group> content and save to group_content.txt
    group_content = ""
    if os.path.exists(temp_jsx_path):
        with open(temp_jsx_path, "r") as f:
            chair_content = f.read()

        group_start = "<group"
        group_end = "</group>"
        start_idx = chair_content.find(group_start)
        
        if start_idx != -1:
            group_open_end = chair_content.find(">", start_idx) + 1
            nest_level = 0
            current_idx = group_open_end
            
            while current_idx < len(chair_content):
                if chair_content[current_idx:].startswith("<group"):
                    nest_level += 1
                    current_idx = chair_content.find(">", current_idx) + 1
                elif chair_content[current_idx:].startswith("</group>"):
                    if nest_level == 0:
                        end_idx = current_idx + len(group_end)
                        break
                    nest_level -= 1
                    current_idx += len(group_end)
                else:
                    current_idx += 1

            if start_idx != -1 and end_idx != -1:
                group_content = chair_content[start_idx:end_idx]
                group_content = re.sub(r'(<group\s+[^>]*?)(\s*scale=\{[^}]*\})(\s*[^>]*>)', r'\1\3', group_content)
                group_content = group_content.replace("<group {...props} dispose={null}", "<group {...props} dispose={null} scale={0.3} ")

                # Save the full group content to a text file
                group_output_path = os.path.join(object_path, "group_content.txt")
                with open(group_output_path, "w") as f:
                    f.write(group_content)

        # Clean up: remove the temporary Obj.jsx
        os.remove(temp_jsx_path)

    # Update the existing Obj.jsx in MODEL_DIR using group_content.txt
    obj_jsx_path = os.path.join(MODEL_DIR, "Obj.jsx")
    if os.path.exists(obj_jsx_path) and group_content:
        with open(obj_jsx_path, "r") as f:
            obj_content = f.read()

        # Find the return statement and replace its content
        return_start = obj_content.find("return (")
        return_end = obj_content.find(")", return_start)
        if return_start != -1 and return_end != -1:
            # Replace the content inside return (...) with the group_content
            new_return_content = f"return (\n    {group_content}\n  )"
            obj_content = obj_content[:return_start] + new_return_content + obj_content[return_end + 1:]
        
        # Update the useGLTF and useGLTF.preload paths
        existing_folders = [f for f in os.listdir(UPLOAD_DIR) if f.startswith("object")]
        highest_index = max([int(f.replace("object", "")) for f in existing_folders if f.replace("object", "").isdigit()], default=0)
    
        obj_content = obj_content.replace(f"useGLTF.preload('/object{highest_index-1}/Obj.gltf')", f"useGLTF.preload('/{folder_name}/Obj.gltf')")
        obj_content = obj_content.replace(f"useGLTF('/object{highest_index-1}/Obj.gltf')", f"useGLTF('/{folder_name}/Obj.gltf')")
        print(f"this is the number:{highest_index}")


        # Write the updated content back to Obj.jsx
        with open(obj_jsx_path, "w") as f:
            f.write(obj_content)
    else:
        return {"error": "Obj.jsx not found or group_content is empty"}

    return {"message": "Upload and processing completed successfully", "folder": folder_name}