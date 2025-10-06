import base64
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from sqlalchemy.orm import Session
from pydantic import BaseModel

from .. import auth as auth_utils
from ..database import get_db
from ..services.facturacion_service import get_factura_pdf_tesabiz, anular_factura_tesabiz

router = APIRouter(
    prefix="/facturas",
    tags=["facturas"]
)

class AnularFacturaRequest(BaseModel):
    codigo_motivo: int = 1  # Código de motivo por defecto (1 = por error de importe)

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


@router.patch("/{factura_id}/anular")
async def anular_factura(
    factura_id: int,
    request: AnularFacturaRequest,
    db: Session = Depends(get_db),
    current_user: auth_utils.Usuario = Depends(auth_utils.require_menu_access("/ventas"))
):
    """
    Anula una factura electrónica en Tesabiz.
    Solo se pueden anular facturas con estado VALIDADA.
    """
    try:
        resultado = await anular_factura_tesabiz(factura_id, request.codigo_motivo, db)
        return resultado

    except HTTPException as e:
        # Re-raise HTTPException to let FastAPI handle it
        raise e
    except Exception as e:
        # Catch any other unexpected errors
        print(f"Error inesperado al anular factura_id {factura_id}: {e}")
        raise HTTPException(status_code=500, detail="Error interno al anular la factura.")
