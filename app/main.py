from fastapi import FastAPI,WebSocket, WebSocketDisconnect, Depends, HTTPException, status
from app.models.base import Base
from app.database import engine
from fastapi.middleware.cors import CORSMiddleware
from app.routes import auth, usuario, rol, categoria,persona,producto , proveedor, empresa,compra ,venta,metodo_pago, cliente,marca,unidad_medida,dashboard
from fastapi.staticfiles import StaticFiles # Para servir archivos estáticos
from .routes import uploads, auth # Importa tus rutas

from dotenv import load_dotenv
import os # Importa os para usar os.environ.get

# IMPORTACIONES PARA WEBSOCKETS Y LÓGICA DE NEGOCIO ***
from typing import List, Dict
import json # Para convertir datos a JSON para WebSockets
from sqlalchemy.orm import Session # Ya deberías tenerla
from app.database import get_db # Ya deberías tenerla
from app.models.producto import Producto as DBProducto # Ya deberías tenerla
from app.auth import get_current_active_user_with_role # Asumiendo que esta es tu función de autenticación
from app.schemas.producto import Producto as ProductoSchema # Asumiendo que este es tu esquema Pydantic para Producto
from . import auth as auth_utils # Importa el módulo auth con alias
#ConnectionManager
class AdministradorDeConexiones:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        print(f"WebSocket conectado: {websocket.client}")

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)
        print(f"WebSocket desconectado: {websocket.client}")

    async def send_personal_message(self, message: str, websocket: WebSocket):
        await websocket.send_text(message)

    async def broadcast(self, message: str):
        for connection in self.active_connections:
            await connection.send_text(message)
            # print(f"Broadcast enviado a: {connection.client}") # Opcional: imprimir cada envío

manager = AdministradorDeConexiones() # Crea una instancia del manager




# Carga las variables del archivo .env en el entorno del sistema
load_dotenv()

#  Imprimir valores de variables de entorno después de cargar .env ***
print("--- Debugging Environment Variables ---")
print(f"TWILIO_ACCOUNT_SID: {os.environ.get('TWILIO_ACCOUNT_SID')}")
print(f"TWILIO_AUTH_TOKEN: {os.environ.get('TWILIO_AUTH_TOKEN')}")
print(f"TWILIO_WHATSAPP_FROM: {os.environ.get('TWILIO_WHATSAPP_FROM')}")
print("-------------------------------------")


app = FastAPI()

app.title = "Sistema de Ventas y Compras"

app.mount("/static", StaticFiles(directory="static"), name="static")

# *** ENDPOINT WEBSOCKET ***
@app.websocket("/ws/queue") 
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
 
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)
        print(f"WebSocket desconectado: {websocket.client}")
    except Exception as e:
        print(f"Error en el WebSocket: {e}")


# *** NUEVO ENDPOINT REST PARA NOTIFICAR ESCANEO DESDE EL MÓVIL ***
# Esta ruta la llamará tu aplicación móvil después de un escaneo exitoso.
@app.post("/sales/add-to-queue/{product_code}", status_code=status.HTTP_200_OK)
async def add_product_to_web_queue(
    product_code: str,
    db: Session = Depends(get_db),
    # Ajusta los roles si solo ciertos usuarios del móvil pueden notificar
    current_user: auth_utils.Usuario = Depends(get_current_active_user_with_role(["Administrador", "Empleado", "Cajero"]))
):
    # 1. Buscar el producto por código en la base de datos
    db_producto = db.query(DBProducto).filter(DBProducto.codigo == product_code).first()
    if db_producto is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Producto con código '{product_code}' no encontrado.")

    # 2. Preparar los datos del producto para enviar por WebSocket
    # Es importante que el precio sea convertible a float para JSON
    product_data_for_ws = {
        "event": "product_scanned", # Tipo de evento para que el frontend lo reconozca
        "product": {
            "producto_id": db_producto.producto_id,
            "codigo": db_producto.codigo,
            "nombre": db_producto.nombre,
            "precio": float(db_producto.precio), # <--- Asegúrate de convertir a float si es Decimal
            "stock": db_producto.stock,
            "quantity": 1 # Asume que cada escaneo añade 1 unidad por defecto
            # Añade cualquier otro campo que tu frontend necesite (ej. stock, imagen_ruta)
        }
    }
    # 3. ¡ENVIAR LA NOTIFICACIÓN POR WEBSOCKET A TODOS LOS CLIENTES WEB CONECTADOS!
    try:
        await manager.broadcast(json.dumps(product_data_for_ws)) # Convierte el diccionario a string JSON
    except Exception as e:
        print(f"Error al hacer broadcast del mensaje WebSocket: {e}")
      

    return {"message": f"Producto {db_producto.nombre} añadido a la cola web."}


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Cambia a los orígenes permitidos en producción
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# Crear tablas en la base de datos
Base.metadata.create_all(bind=engine)

# Incluir rutas
app.include_router(auth.router, tags=["login"])
app.include_router(usuario.router , tags=["usuarios"])
app.include_router(rol.router , tags=["roles"])
app.include_router(categoria.router, tags=["categoria"])  
app.include_router(persona.router, tags=["personas"])
app.include_router(uploads.router)  
app.include_router(producto.router) 
app.include_router(proveedor.router)  
app.include_router(empresa.router)  
app.include_router(compra.router)  
app.include_router(venta.router)  

app.include_router(metodo_pago.router)  
app.include_router(venta.router_productos_public)  
app.include_router(cliente.router)
app.include_router(marca.router)
app.include_router(unidad_medida.router)
app.include_router(dashboard.router) # ¡Añade esta línea!

 