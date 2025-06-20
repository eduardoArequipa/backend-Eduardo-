# backEnd/app/routes/empresa.py
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import or_ # Importar para búsqueda combinada

# Importa tus utilidades de auth y la dependencia get_db
from .. import auth as auth_utils # Importa el módulo auth con alias

from ..database import get_db

# Importa el modelo SQLAlchemy Empresa
from ..models.empresa import Empresa as DBEmpresa # Usa el alias DBEmpresa

# Importa el Enum para el estado
from ..models.enums import EstadoEnum

# Importar tus esquemas Pydantic para Empresa
from ..schemas.empresa import (
    Empresa, # Esquema de lectura completa
    EmpresaCreate, # Esquema para creación
    EmpresaUpdate, # Esquema para actualización
    EmpresaNested # Esquema de lectura anidada (si lo usas en otros esquemas)
)

# Si tu modelo Empresa tiene campos de auditoría que referencian a Usuario, impórtalo
# from ..models.usuario import Usuario as DBUsuario


router = APIRouter(
    prefix="/empresas", # Prefijo para todas las rutas en este router
    tags=["empresas"] # Etiqueta para agrupar en la documentación (Swagger UI)
)

# Define qué roles pueden gestionar empresas (ej. Administrador, Empleado)
# Asegúrate de que estos nombres de rol coinciden exactamente con los de tu base de datos
ROLES_CAN_MANAGE_EMPRESAS = ["Administrador", "Empleado"]


# --- Endpoint para Crear una Nueva Empresa ---
@router.post("/", response_model=Empresa, status_code=status.HTTP_201_CREATED)
def create_empresa(
    empresa: EmpresaCreate, # Espera tu esquema EmpresaCreate
    db: Session = Depends(get_db),
    # Restringe el acceso: solo usuarios con ROLES_CAN_MANAGE_EMPRESAS pueden crear
    current_user: auth_utils.Usuario = Depends(auth_utils.get_current_active_user_with_role(ROLES_CAN_MANAGE_EMPRESAS))
):
    """
    Crea una nueva Empresa.
    Solo accesible por usuarios con permisos de gestión de empresas.
    """
    # 1. Verificar si ya existe una empresa con la misma identificación (si se proporcionó)
    # La identificación puede ser NULL en la DB, pero UNIQUE si no es NULL.
    # Si el cliente envía una identificación, verificamos que no exista ya.
    if empresa.identificacion:
        db_empresa_identificacion = db.query(DBEmpresa).filter(DBEmpresa.identificacion == empresa.identificacion).first()
        if db_empresa_identificacion:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Ya existe una empresa con esta Identificación: {empresa.identificacion}")

    # 2. Crear el objeto Empresa SQLAlchemy
    # Usamos **empresa.model_dump() para desempaquetar los campos del esquema Create
    # Los campos con default (estado) se asignarán automáticamente si no están en el esquema Create
    new_empresa = DBEmpresa(**empresa.model_dump())

    # Si tu modelo Empresa tuviera campo creado_por, lo asignarías aquí:
    # new_empresa.creado_por = current_user.usuario_id

    db.add(new_empresa) # Añadir a la sesión
    db.commit() # Confirmar la transacción
    db.refresh(new_empresa) # Refrescar para obtener el empresa_id generado por la DB

    return new_empresa # Retorna el objeto DBEmpresa que FastAPI serializa a Empresa


# --- Endpoint para Listar Empresas ---
# Este endpoint es necesario para el formulario de Proveedor.
# Lo restringiremos a usuarios con ROLES_CAN_MANAGE_EMPRESAS por defecto.
@router.get("/", response_model=List[Empresa]) # Retorna una lista del esquema Empresa
def read_empresas(
    estado: Optional[EstadoEnum] = Query(None, description="Filtrar por estado"),
    search: Optional[str] = Query(None, description="Texto de búsqueda por razón social o identificación"), # Búsqueda combinada
    skip: int = Query(0, ge=0, description="Número de elementos a omitir (paginación)"),
    limit: int = Query(100, gt=0, description="Número máximo de elementos a retornar (paginación)"),
    # Parámetro opcional para filtrar empresas sin proveedor asociado (útil para selectores)
    without_proveedor: Optional[bool] = Query(None, description="Filtrar empresas que no tienen un proveedor asociado"),
    db: Session = Depends(get_db),
    # Restringe el acceso: solo usuarios con ROLES_CAN_MANAGE_EMPRESAS pueden listar (ajusta si es necesario)
    current_user: auth_utils.Usuario = Depends(auth_utils.get_current_active_user_with_role(ROLES_CAN_MANAGE_EMPRESAS))
):
    """
    Obtiene una lista de Empresas con opciones de filtro, búsqueda y paginación.
    Opcionalmente, filtra empresas que no tienen un proveedor asociado.
    Accesible solo por usuarios con permisos de gestión de empresas (por defecto).
    """
    query = db.query(DBEmpresa)

    # Aplicar filtros
    if estado:
        query = query.filter(DBEmpresa.estado == estado)

    if search:
        # Buscar tanto en razon_social como en identificacion
        query = query.filter(
            or_(
                DBEmpresa.razon_social.ilike(f"%{search}%"),
                DBEmpresa.identificacion.ilike(f"%{search}%"),
            )
        )

    # *** Aplicar filtro para empresas sin proveedor asociado ***
    if without_proveedor is True:
        # Asume que tienes la relación inversa 'proveedor' definida en el modelo Empresa
        query = query.filter(DBEmpresa.proveedor.is_(None)) # Filtra donde la relación proveedor es NULL
    elif without_proveedor is False:
         # Opcional: filtrar empresas *con* proveedor asociado
         query = query.filter(DBEmpresa.proveedor.isnot(None))


    # Aplicar paginación
    empresas = query.offset(skip).limit(limit).all()

    return empresas # Retorna la lista de objetos DBEmpresa que FastAPI serializa a List[Empresa]


# --- Endpoint para Obtener una Empresa por ID ---
# Lo restringiremos a usuarios con ROLES_CAN_MANAGE_EMPRESAS por defecto.
@router.get("/{empresa_id}", response_model=Empresa) # Retorna el esquema Empresa
def read_empresa(
    empresa_id: int,
    db: Session = Depends(get_db),
    current_user: auth_utils.Usuario = Depends(auth_utils.get_current_active_user_with_role(ROLES_CAN_MANAGE_EMPRESAS))
):
    """
    Obtiene la información de una Empresa específica por su ID.
    Accesible solo por usuarios con permisos de gestión de empresas (por defecto).
    """
    empresa = db.query(DBEmpresa).filter(DBEmpresa.empresa_id == empresa_id).first()

    if empresa is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Empresa no encontrada")

    return empresa # Retorna el objeto DBEmpresa que FastAPI serializa a Empresa


# --- Endpoint para Actualizar una Empresa por ID ---
# Requiere que el usuario logeado tenga uno de los roles en ROLES_CAN_MANAGE_EMPRESAS
@router.put("/{empresa_id}", response_model=Empresa) # Retorna el esquema Empresa
def update_empresa(
    empresa_id: int,
    empresa_update: EmpresaUpdate, # Espera tu esquema EmpresaUpdate (campos opcionales)
    db: Session = Depends(get_db),
    current_user: auth_utils.Usuario = Depends(auth_utils.get_current_active_user_with_role(ROLES_CAN_MANAGE_EMPRESAS))
):
    """
    Actualiza la información de una Empresa existente por su ID.
    Permite actualizar varios campos.
    Solo accesible por usuarios con permisos de gestión de empresas.
    """
    # 1. Obtener la empresa por ID
    db_empresa = db.query(DBEmpresa).filter(DBEmpresa.empresa_id == empresa_id).first()

    if db_empresa is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Empresa no encontrada.")

    # 2. Verificar si la nueva identificación (si se cambió y no es NULL) ya existe en otra empresa
    # Es importante solo verificar si empresa_update.identificacion tiene un valor (no None) Y es diferente al actual
    if empresa_update.identificacion is not None and empresa_update.identificacion != db_empresa.identificacion:
         existing_empresa_with_new_identificacion = db.query(DBEmpresa).filter(DBEmpresa.identificacion == empresa_update.identificacion).first()
         if existing_empresa_with_new_identificacion and existing_empresa_with_new_identificacion.empresa_id != empresa_id:
              raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Ya existe otra empresa con esta Identificación: {empresa_update.identificacion}")

    # 3. Actualizar los campos del objeto SQLAlchemy con los datos del esquema EmpresaUpdate
    # model_dump(exclude_unset=True) asegura que solo se actualizan los campos que se enviaron
    update_data = empresa_update.model_dump(exclude_unset=True)

    for field, value in update_data.items():
        setattr(db_empresa, field, value)

    # Si tu modelo Empresa tuviera campo modificado_por, lo asignarías aquí:
    # db_empresa.modificado_por = current_user.usuario_id

    db.commit() # Confirmar la transacción
    db.refresh(db_empresa) # Refrescar para obtener los cambios confirmados

    return db_empresa # Retorna el objeto DBEmpresa actualizado que FastAPI serializa a Empresa


# --- Endpoint para Eliminar/Desactivar una Empresa por ID (Soft Delete) ---
# Requiere que el usuario logeado tenga uno de los roles en ROLES_CAN_MANAGE_EMPRESAS
@router.delete("/{empresa_id}", status_code=status.HTTP_204_NO_CONTENT) # 204 No Content en éxito sin cuerpo
def delete_empresa(
    empresa_id: int,
    db: Session = Depends(get_db),
    current_user: auth_utils.Usuario = Depends(auth_utils.get_current_active_user_with_role(ROLES_CAN_MANAGE_EMPRESAS))
):
    """
    Desactiva (cambia el estado a inactivo) una Empresa por su ID.
    Solo accesible por usuarios con permisos de gestión de empresas.
    """
    # Obtener la empresa por ID
    db_empresa = db.query(DBEmpresa).filter(DBEmpresa.empresa_id == empresa_id).first()
    if db_empresa is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Empresa no encontrada.")

    # Verificar si la empresa ya está inactiva (opcional)
    if db_empresa.estado == EstadoEnum.inactivo:
         raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="La empresa ya está inactiva.")

    # Implementar Soft Delete: cambiar el estado
    db_empresa.estado = EstadoEnum.inactivo

    # Si tu modelo Empresa tuviera campo modificado_por, lo asignarías aquí:
    # db_empresa.modificado_por = current_user.usuario_id

    db.commit() # Confirmar el cambio

    return {} # Retorna un cuerpo vacío para 204 No Content

# --- ENDPOINT: Activar una Empresa por ID (PATCH /empresas/{empresa_id}) ---
# Requiere que el usuario logeado tenga uno de los roles en ROLES_CAN_MANAGE_EMPRESAS
@router.patch("/{empresa_id}", response_model=Empresa) # Retorna el esquema Empresa
def activate_empresa(
    empresa_id: int,
    db: Session = Depends(get_db),
    current_user: auth_utils.Usuario = Depends(auth_utils.get_current_active_user_with_role(ROLES_CAN_MANAGE_EMPRESAS))
):
    """
    Activa (cambia el estado a activo) una Empresa por su ID.
    Solo accesible por usuarios con permisos de gestión de empresas.
    """
    # Obtener la empresa por ID
    db_empresa = db.query(DBEmpresa).filter(DBEmpresa.empresa_id == empresa_id).first()

    if db_empresa is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Empresa no encontrada.")

    if db_empresa.estado == EstadoEnum.activo:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="La empresa ya está activa.")

    db_empresa.estado = EstadoEnum.activo

    # Si tu modelo Empresa tuviera campo modificado_por, lo asignarías aquí:
    # db_empresa.modificado_por = current_user.usuario_id

    db.commit()
    db.refresh(db_empresa)

    return db_empresa
