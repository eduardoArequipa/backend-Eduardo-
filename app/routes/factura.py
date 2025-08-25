import base64
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session

from .. import auth as auth_utils
from ..database import get_db
from ..services.facturacion_service import get_factura_pdf_tesabiz

router = APIRouter(
    prefix="/facturas",
    tags=["facturas"]
)

@router.get("/{factura_id}/pdf")
async def download_factura_pdf(
    factura_id: int,
    db: Session = Depends(get_db),
    current_user: auth_utils.Usuario = Depends(auth_utils.require_menu_access("/ventas")) # Assuming same permission
):
    """
    Descarga la representación gráfica (PDF) de una factura electrónica.
    """
    try:
        pdf_base64 = await get_factura_pdf_tesabiz(factura_id, db)
        
        pdf_bytes = base64.b64decode(pdf_base64)
        
        headers = {
            'Content-Disposition': f'inline; filename="factura-{factura_id}.pdf"'
        }
        return Response(content=pdf_bytes, media_type="application/pdf", headers=headers)

    except HTTPException as e:
        # Re-raise HTTPException to let FastAPI handle it
        raise e
    except Exception as e:
        # Catch any other unexpected errors
        print(f"Error al decodificar o servir el PDF para factura_id {factura_id}: {e}")
        raise HTTPException(status_code=500, detail="No se pudo procesar el archivo PDF.")
