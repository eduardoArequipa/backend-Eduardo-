import httpx
import json
from fastapi import HTTPException
from sqlalchemy.orm import Session, joinedload
from app.models import Venta, Empresa, Usuario, FacturaElectronica
from app.models.detalle_venta import DetalleVenta as DBDetalleVenta
import os
from datetime import datetime
import time
import base64

TESABIZ_API_URL = os.getenv("TESABIZ_API_URL")
TESABIZ_PDF_URL = os.getenv("TESABIZ_PDF_URL")

def get_datos_empresa(db: Session):
    empresa = db.query(Empresa).first()
    if not empresa:
        raise HTTPException(status_code=500, detail="No hay datos de la empresa configurados.")
    return empresa

def format_fecha(fecha: datetime):
    return fecha.strftime('%Y%m%d%H%M%S') + "000"

def construir_json_factura(venta_db: Venta, empresa_db: Empresa, usuario_db: Usuario, numero_factura: int):
    detalle_factura = [
        {
            "cantidad": float(item.cantidad),
            "precioUnitario": float(item.precio_unitario),
            "actividadEconomica": "471110",
            "codigoProductoSin": "621329",
            "codigoProducto": str(item.producto.producto_id),
            "descripcion": item.producto.nombre,
            "montoDescuento": 0,
            "subTotal": float(item.cantidad * item.precio_unitario),
            "unidadMedida": 57,
            "numeroSerie": None,
            "numeroImei": 0
        } for item in venta_db.detalles
    ]
    cabecera_factura = {
        "codigoMoneda": 1,
        "cafc": None,
        "montoTotal": float(venta_db.total),
        "montoTotalMoneda": float(venta_db.total),
        "descuentoAdicional": 0,
        "montoTotalSujetoIva": float(venta_db.total),
        "tipoCambio": 1,
        "codigoMetodoPago": venta_db.metodo_pago_id,
        "numeroFactura": numero_factura,
        "direccion": empresa_db.direccion,
        "fechaEmision": None,
        "codigoTipoDocumentoIdentidad": "1",
        "cuf": None,
        "numeroDocumento": venta_db.persona.ci,
        "complemento": None,
        "codigoSucursal": "0",
        "codigoPuntoVenta": "0",
        "nombreRazonSocial": str(venta_db.persona.nombre) + str(" " + (venta_db.persona.apellido_paterno or "") + " " + (venta_db.persona.apellido_materno or "")),
        "codigoCliente": str(venta_db.persona.persona_id),
        "codigoExcepcion": 0,
        "codigoDocumentoSector": 35,
        "nitEmisor": 1028341029,
        "razonSocialEmisor": "Multicenter S.R.L.",
        "municipio":  "COCHABAMBA - BOLIVIA",
        "usuario": "admin",
        "montoGiftCard": 0
    }
    factura_completa = {
        "facturaCompraVentaBon": {
            "detalle": detalle_factura,
            "cabecera": cabecera_factura
        },
        "idDocFiscalERP": "121650000"+str(numero_factura)+"3212",
        "codigoTipoFactura": 1,
        "emailCliente": venta_db.persona.email,
        "contingencia": False,
        "esLote": False,
        "idLoteERP": "",
        "ultFacturaLote": False,
        "codigoSistemaOrigen": "SO_MULTICENTER_SRL",
        "fueraLinea": False,
        "eventoId": ""
    }
    return factura_completa

async def crear_factura_tesabiz(venta_id: int, db: Session):
    print(f"[FACTURACION] Iniciando proceso para Venta ID: {venta_id}")
    venta_db = db.query(Venta).options(joinedload(Venta.persona), joinedload(Venta.detalles).joinedload(DBDetalleVenta.producto)).filter(Venta.venta_id == venta_id).first()
    if not venta_db:
        raise HTTPException(status_code=404, detail=f"Venta con ID {venta_id} no encontrada.")
    if not venta_db.persona:
        raise HTTPException(status_code=400, detail="La venta no tiene un cliente asociado.")
    
    empresa_db = get_datos_empresa(db)
    usuario_db = db.query(Usuario).filter(Usuario.usuario_id == venta_db.creado_por).first()
    if not usuario_db:
        raise HTTPException(status_code=404, detail="Usuario creador de la venta no encontrado.")

    print("[FACTURACION] 1. Reservando ID de factura en la base de datos...")
    factura_db = FacturaElectronica(venta_id=venta_db.venta_id, estado="PENDIENTE")
    db.add(factura_db)
    db.commit()
    db.refresh(factura_db)
    print(f"[FACTURACION] ID reservado: {factura_db.factura_id}")

    factura_a_enviar = construir_json_factura(venta_db, empresa_db, usuario_db, factura_db.factura_id)
    print(f"[FACTURACION] 2. JSON para Tesabiz construido. Enviando factura #{factura_db.factura_id}...")
    print(f"[FACTURACION] PAYLOAD A ENVIAR: {json.dumps(factura_a_enviar, indent=2)}")

    headers = { "Content-Type": "application/json" }
    try:
        async with httpx.AsyncClient(verify=False) as client:
            response = await client.post(TESABIZ_API_URL, json=factura_a_enviar, headers=headers, timeout=40.0)
            response.raise_for_status()
            respuesta_tesabiz = response.json()
            print(f"[FACTURACION] 3. Respuesta recibida de Tesabiz: {json.dumps(respuesta_tesabiz, indent=2)}")

        proceso_respuesta = respuesta_tesabiz.get("proceso")
        
        if proceso_respuesta:
            # Caso de Éxito (Respuesta con objeto 'proceso')
            codigo_recepcion = proceso_respuesta.get("codigoRecepcion")
            cuf = respuesta_tesabiz.get("facturaCompraVentaBon", {}).get("cabecera", {}).get("cuf")
            print(f"[FACTURACION] -> Código de Recepción: {codigo_recepcion}, CUF: {cuf}")

            factura_db.cuf = cuf
            factura_db.tesabiz_id = proceso_respuesta.get("idDocFiscalFEEL")
            factura_db.detalles_respuesta = json.dumps(respuesta_tesabiz)

            if str(codigo_recepcion) == "908" and cuf:
                factura_db.estado = "VALIDADA"
                print("[FACTURACION] -> Estado determinado: VALIDADA")
            else:
                factura_db.estado = "RECHAZADA"
                print(f"[FACTURACION] -> Estado determinado: RECHAZADA (Código no es 908 o falta CUF)")
            db.commit()
        else:
            # Caso de Error (Respuesta sin objeto 'proceso')
            respuesta_error = respuesta_tesabiz.get("respuesta", {})
            error_msg = respuesta_error.get("txtRespuesta", "Error desconocido de Tesabiz.")
            print(f"[FACTURACION] -> Error de Tesabiz: {error_msg}")
            factura_db.estado = "RECHAZADA"
            factura_db.cuf = None
            factura_db.tesabiz_id = None
            factura_db.detalles_respuesta = json.dumps(respuesta_tesabiz)
            db.commit()
        
        print(f"[FACTURACION] 4. Factura ID {factura_db.factura_id} actualizada en la BD. Proceso completado.")

    except Exception as e:
        print(f"[FACTURACION] !!! ERROR !!! Ha ocurrido un error durante el proceso: {e}")
        factura_db.estado = "ERROR"
        factura_db.detalles_respuesta = f"Error en la comunicación o procesamiento con Tesabiz: {str(e)}"
        db.commit()
        print(f"[FACTURACION] Guardado registro de factura ID {factura_db.factura_id} con estado de ERROR.")


async def get_factura_pdf_tesabiz(factura_id: int, db: Session):
    """
    Obtiene la representación PDF de una factura desde Tesabiz.
    """
    factura_db = db.query(FacturaElectronica).options(
        joinedload(FacturaElectronica.venta).joinedload(Venta.persona)
    ).filter(FacturaElectronica.factura_id == factura_id).first()

    if not factura_db:
        raise HTTPException(status_code=404, detail="Factura electrónica no encontrada.")
    
    if not factura_db.cuf:
        raise HTTPException(status_code=400, detail="La factura no tiene un CUF, no se puede obtener el PDF.")

    if not factura_db.venta or not factura_db.venta.persona:
        raise HTTPException(status_code=400, detail="No se pudo encontrar el cliente asociado a la factura.")

    if not factura_db.venta.persona.ci:
        raise HTTPException(status_code=400, detail="El cliente asociado a la factura no tiene un número de CI/NIT registrado.")

    empresa_db = get_datos_empresa(db)

    pdf_request_body = {
        "nitEmisor": "1028341029",
        "nitCliente": factura_db.venta.persona.ci,
        "cuf": factura_db.cuf
    }
    
    if not TESABIZ_PDF_URL:
        raise HTTPException(status_code=500, detail="La URL para obtener el PDF de facturas (TESABIZ_PDF_URL) no está configurada.")

    headers = {"Content-Type": "application/json"}

    print(f"Solicitando PDF a Tesabiz para Factura ID {factura_id} con CUF {factura_db.cuf}")

    async with httpx.AsyncClient(verify=False) as client:
        try:
            response = await client.post(TESABIZ_PDF_URL, json=pdf_request_body, headers=headers, timeout=40.0)
            response.raise_for_status()
            
            respuesta_tesabiz = response.json()
            print(f"Respuesta de Tesabiz para PDF: {json.dumps(respuesta_tesabiz, indent=2)}")

            doc_fiscal = respuesta_tesabiz.get("docFiscal")
            if not doc_fiscal or not isinstance(doc_fiscal, dict):
                error_msg = respuesta_tesabiz.get("respuesta", {}).get("txtRespuesta", "Tesabiz no devolvió un objeto 'docFiscal' válido.")
                raise HTTPException(status_code=404, detail=error_msg)

            pdf_base64 = doc_fiscal.get("archivo")

            if not pdf_base64:
                raise HTTPException(status_code=404, detail="La respuesta de Tesabiz no contiene el campo 'archivo' con el PDF dentro de 'docFiscal'.")

            return pdf_base64

        except httpx.HTTPStatusError as e:
            error_detail = f"Error HTTP al obtener PDF de Tesabiz: {e.response.status_code} - {e.response.text}"
            print(error_detail)
            raise HTTPException(status_code=500, detail=error_detail)
        except Exception as e:
            error_detail = f"Error inesperado al obtener PDF de Tesabiz: {str(e)}"
            print(error_detail)
            raise HTTPException(status_code=500, detail=error_detail)
