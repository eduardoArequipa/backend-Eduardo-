# backEnd/app/routes/cliente.py

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import or_

# Importa tus utilidades de auth y la dependencia get_db
from .. import auth as auth_utils
from ..database import get_db

# Importa los modelos SQLAlchemy
from ..models.cliente import Cliente as DBCliente
from ..models.persona import Persona as DBPersona
from ..models.usuario import Usuario as DBUsuario # Para creador/modificador si los clientes tienen
from ..models.enums import EstadoEnum # Para el estado del cliente

# Importa tus esquemas Pydantic
from ..schemas.cliente import (
    Cliente,
    ClienteCreate,
    ClienteNested, # Para la respuesta de listado/anidación
    PersonaNested, # Para la persona anidada
)
from ..schemas.usuario import UsuarioAudit # Si Cliente tiene campos de auditoría

router = APIRouter(
    prefix="/clientes",
    tags=["clientes"]
)

# Roles que pueden gestionar clientes (ajusta según tus roles)
ROLES_CAN_MANAGE_CLIENTS = ["Administrador", "Empleado"]

# --- Endpoint para Listar Clientes ---
@router.get("/", response_model=List[ClienteNested]) # Usamos ClienteNested para la respuesta de listado
def read_clientes(
    estado: Optional[EstadoEnum] = Query(None, description="Filtrar por estado del cliente"),
    search: Optional[str] = Query(None, description="Buscar por nombre, apellido o CI de la persona"),
    skip: int = Query(0, ge=0, description="Número de elementos a omitir (paginación)"),
    limit: int = Query(100, gt=0, description="Número máximo de elementos a retornar (paginación)"),
    db: Session = Depends(get_db),
    # current_user: auth_utils.Usuario = Depends(auth_utils.get_current_active_user_with_role(ROLES_CAN_MANAGE_CLIENTS))
    # Descomenta la línea de arriba si quieres que este endpoint requiera autenticación
):
    """
    Obtiene una lista de clientes con opciones de filtro, búsqueda y paginación.
    Incluye la información anidada de la persona asociada.
    """
    query = db.query(DBCliente).options(
        joinedload(DBCliente.persona) # Carga la relación con Persona
        # Si Cliente tuviera creador/modificador:
        # .joinedload(DBCliente.creador)
        # .joinedload(DBCliente.modificador)
    )

    if estado:
        query = query.filter(DBCliente.estado == estado)

    if search:
        # Búsqueda por nombre, apellido o CI de la persona
        query = query.filter(
            DBCliente.persona.has(
                or_(
                    DBPersona.nombre.ilike(f"%{search}%"),
                    DBPersona.apellido_paterno.ilike(f"%{search}%"),
                    DBPersona.apellido_materno.ilike(f"%{search}%"),
                    DBPersona.ci.ilike(f"%{search}%")
                )
            )
        )

    clientes = query.offset(skip).limit(limit).all()
    return clientes

# --- Endpoint para Obtener un Cliente por ID ---
@router.get("/{cliente_id}", response_model=Cliente) # Usamos Cliente completo para la respuesta detallada
def get_cliente(
    cliente_id: int,
    db: Session = Depends(get_db),
    # current_user: auth_utils.Usuario = Depends(auth_utils.get_current_active_user_with_role(ROLES_CAN_MANAGE_CLIENTS))
):
    """
    Obtiene un cliente específico por su ID, incluyendo la información de la persona.
    """
    db_cliente = db.query(DBCliente).options(
        joinedload(DBCliente.persona)
    ).filter(DBCliente.cliente_id == cliente_id).first()

    if db_cliente is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cliente no encontrado.")

    return db_cliente

# --- Endpoint para Crear un Nuevo Cliente ---
@router.post("/", response_model=Cliente, status_code=status.HTTP_201_CREATED)
def create_cliente(
    cliente_data: ClienteCreate,
    db: Session = Depends(get_db),
    current_user: auth_utils.Usuario = Depends(auth_utils.get_current_active_user_with_role(ROLES_CAN_MANAGE_CLIENTS))
):
    """
    Crea un nuevo cliente. Requiere que la persona_id ya exista.
    """
    # Verifica si la persona_id existe y no está ya asociada a otro cliente
    db_persona = db.query(DBPersona).filter(
        DBPersona.persona_id == cliente_data.persona_id,
        DBPersona.estado == EstadoEnum.activo # O el estado que consideres válido para asociar
    ).first()
    if not db_persona:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Persona no encontrada o inactiva.")

    # Opcional: Verifica si ya existe un cliente con esta persona_id
    existing_cliente = db.query(DBCliente).filter(DBCliente.persona_id == cliente_data.persona_id).first()
    if existing_cliente:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Esta persona ya está asociada a un cliente.")

    try:
        new_cliente = DBCliente(
            persona_id=cliente_data.persona_id,
            estado=EstadoEnum.activo, # Estado por defecto al crear
            # creado_por=current_user.usuario_id # Si tu modelo Cliente tiene este campo
        )
        db.add(new_cliente)
        db.commit()
        db.refresh(new_cliente)
        return new_cliente
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error al crear cliente: {e}")

# --- Endpoint para Actualizar el Estado de un Cliente (o otros campos) ---
@router.patch("/{cliente_id}", response_model=Cliente)
def update_cliente(
    cliente_id: int,
    estado: EstadoEnum = Query(..., description="Nuevo estado del cliente"), # Solo permite actualizar el estado por ahora
    db: Session = Depends(get_db),
    # current_user: auth_utils.Usuario = Depends(auth_utils.get_current_active_user_with_role(ROLES_CAN_MANAGE_CLIENTS))
):
    """
    Actualiza el estado de un cliente existente.
    """
    db_cliente = db.query(DBCliente).filter(DBCliente.cliente_id == cliente_id).first()
    if db_cliente is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cliente no encontrado.")

    db_cliente.estado = estado
    # db_cliente.modificado_por = current_user.usuario_id # Si tu modelo Cliente tiene este campo

    try:
        db.add(db_cliente)
        db.commit()
        db.refresh(db_cliente)
        return db_cliente
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error al actualizar cliente: {e}")

# --- Endpoint para Eliminar un Cliente (Opcional, considera solo cambiar estado a inactivo) ---
# @router.delete("/{cliente_id}", status_code=status.HTTP_204_NO_CONTENT)
# def delete_cliente(
#     cliente_id: int,
#     db: Session = Depends(get_db),
#     # current_user: auth_utils.Usuario = Depends(auth_utils.get_current_active_user_with_role(ROLES_CAN_MANAGE_CLIENTS))
# ):
#     """
#     Elimina un cliente por su ID. (Considera cambiar el estado a 'inactivo' en lugar de eliminar físicamente).
#     """
#     db_cliente = db.query(DBCliente).filter(DBCliente.cliente_id == cliente_id).first()
#     if db_cliente is None:
#         raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cliente no encontrado.")

#     try:
#         db.delete(db_cliente)
#         db.commit()
#         return {"message": "Cliente eliminado exitosamente."}
#     except Exception as e:
#         db.rollback()
#         raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error al eliminar cliente: {e}")