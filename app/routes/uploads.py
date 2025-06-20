import os
import uuid
from fastapi import APIRouter, File, UploadFile, HTTPException, status
from PIL import Image
from io import BytesIO

UPLOAD_DIR = "static/uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

router = APIRouter(
    prefix="/uploads",
    tags=["Uploads"]
)

@router.post("/image/")
async def upload_image(file: UploadFile = File(...)):
    if not file.content_type.startswith("image/"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Solo se aceptan imágenes.")

    try:
        # Leer archivo en memoria
        contents = await file.read()

        # Abrir imagen con Pillow desde memoria
        image = Image.open(BytesIO(contents))

        # Convertir a RGB (webp no soporta alfa en algunos casos)
        if image.mode in ("RGBA", "P"):
            image = image.convert("RGB")

        # Crear nombre único con extensión .webp
        unique_filename = f"{uuid.uuid4()}.webp"
        file_path = os.path.join(UPLOAD_DIR, unique_filename)

        # Guardar la imagen como .webp con calidad ajustable (ejemplo: 80)
        image.save(file_path, "WEBP", quality=80)

        await file.close()

        public_path = f"/static/uploads/{unique_filename}"
        return {"file_path": public_path}

    except Exception as e:
        print(f"Error al procesar imagen: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error al procesar la imagen.")
