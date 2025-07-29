from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv
import os
import json
from sqlalchemy.orm import Session

from app.models.base import Base
from app.database import engine, get_db
from app.routes import (
    auth, usuario, rol, categoria, persona, producto, proveedor, 
    empresa, compra, venta, metodo_pago, marca, 
    unidad_medida, dashboard, uploads, movimiento, reportes
)
from app.models.producto import Producto as DBProducto
from app.auth import get_current_active_user_with_role

# --- Administrador de Conexiones WebSocket ---
class AdministradorDeConexiones:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        print(f"WebSocket conectado: {websocket.client}")

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        print(f"WebSocket desconectado: {websocket.client}")

    async def broadcast(self, message: str):
        for connection in self.active_connections:
            await connection.send_text(message)

manager = AdministradorDeConexiones()

# --- Carga de Variables de Entorno ---
load_dotenv()

# --- Creación de la Aplicación FastAPI ---
app = FastAPI(
    title="Sistema de Ventas y Compras Don Eduardo",
    description="API para la gestión de inventario, ventas, compras y más.",
    version="1.0.0"
)

# --- Middlewares ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # TODO: Cambiar a los orígenes permitidos en producción
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Montaje de Archivos Estáticos ---
app.mount("/static", StaticFiles(directory="static"), name="static")

# --- Creación de Tablas en la Base de Datos (para desarrollo) ---
Base.metadata.create_all(bind=engine)

# --- Endpoints de WebSocket y Notificaciones ---
@app.websocket("/ws/queue")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text() # Espera mensajes, pero no hace nada con ellos
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        manager.disconnect(websocket)
        print(f"Error en el WebSocket: {e}")

@app.post("/sales/add-to-queue/{product_code}", status_code=status.HTTP_200_OK)
async def add_product_to_web_queue_sales(
    product_code: str,
    db: Session = Depends(get_db),
 #   current_user: dict = Depends(get_current_active_user_with_role(["Administrador", "Empleado"])) # Roles permitidos
):
    db_producto = db.query(DBProducto).filter(DBProducto.codigo == product_code).first()
    if not db_producto:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Producto con código '{product_code}' no encontrado.")

    product_data_for_ws = {
        "event": "product_scanned",
        "type": "sales_scan", # Nuevo campo para identificar el tipo de escaneo

        "product": {
            "producto_id": db_producto.producto_id,
            "codigo": db_producto.codigo,
            "nombre": db_producto.nombre,
            "precio_venta": float(db_producto.precio_venta), # Precio de venta para el escáner de ventas
            "stock": db_producto.stock,
            "quantity": 1
            
        }
    }
    await manager.broadcast(json.dumps(product_data_for_ws))
    return {"message": f"Producto {db_producto.nombre} notificado a la cola web de ventas."}

@app.post("/purchases/add-to-queue/{product_code}", status_code=status.HTTP_200_OK)
async def add_product_to_web_queue_purchases(
    product_code: str,
    db: Session = Depends(get_db),
 #   current_user: dict = Depends(get_current_active_user_with_role(["Administrador", "Empleado"])) # Roles permitidos
):
    db_producto = db.query(DBProducto).filter(DBProducto.codigo == product_code).first()
    if not db_producto:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Producto con código '{product_code}' no encontrado.")

    product_data_for_ws = {
        "event": "product_scanned",
        "type": "purchase_scan", # Nuevo campo para identificar el tipo de escaneo

        "product": {
            "producto_id": db_producto.producto_id,
            "codigo": db_producto.codigo,
            "nombre": db_producto.nombre,
            "precio_compra": float(db_producto.precio_compra), # Precio de compra para el escáner de compras
            "stock": db_producto.stock,
            "quantity": 1
        }
    }
    await manager.broadcast(json.dumps(product_data_for_ws))
    return {"message": f"Producto {db_producto.nombre} notificado a la cola web de compras."}

# --- Inclusión de Routers de la API ---
app.include_router(auth.router)
app.include_router(usuario.router)
app.include_router(rol.router)
app.include_router(categoria.router)
app.include_router(persona.router)
app.include_router(producto.router)
app.include_router(proveedor.router)
app.include_router(empresa.router)
app.include_router(compra.router)
app.include_router(metodo_pago.router)
app.include_router(marca.router)
app.include_router(unidad_medida.router)
app.include_router(dashboard.router)
app.include_router(uploads.router)
app.include_router(movimiento.router)
app.include_router(reportes.router)

# Routers del módulo de ventas
app.include_router(venta.router) # Para /ventas
app.include_router(venta.router_productos_public) # Para /productos/buscar_por_codigo