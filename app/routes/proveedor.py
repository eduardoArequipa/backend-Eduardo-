# backEnd/app/routes/proveedor.py
from typing import List, Optional, Union

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import or_
from .. import auth as auth_utils 
from ..database import get_db
from ..models.proveedor import Proveedor as DBProveedor 
from ..models.persona import Persona as DBPersona
from ..models.empresa import Empresa as DBEmpresa
from ..models.rol import Rol as DBRol
from ..models.enums import EstadoEnum
from ..schemas.proveedor import (
    ProveedorBase,
    ProveedorCreate,
    ProveedorUpdate, 
    Proveedor, 
    ProveedorPagination, # Importar ProveedorPagination
)

router = APIRouter(
    prefix="/proveedores",
    tags=["proveedores"]
)

ROLES_CAN_MANAGE_PROVEEDORES = ["Administrador", "Empleado"]

@router.post("/", response_model=Proveedor, status_code=status.HTTP_201_CREATED)
def create_proveedor(
    proveedor_data: ProveedorCreate, 
    db: Session = Depends(get_db),
    current_user: auth_utils.Usuario = Depends(auth_utils.require_menu_access("/proveedores")) # Verificar acceso al menú de categorías
):
    """
    Crea un nuevo Proveedor, opcionalmente creando una nueva Persona o Empresa asociada.
    Debe proporcionar exactamente una de las siguientes opciones: persona_id, empresa_id, persona_data, o empresa_data.
    Solo accesible por usuarios con permisos de gestión de proveedores.
    """
    try:
        proveedor_id_to_associate: Optional[int] = None 
        is_persona = False 

        if proveedor_data.persona_data:
            is_persona = True
            persona_create_data = proveedor_data.persona_data.model_dump()
            rol_ids = persona_create_data.pop('rol_ids', [])
            persona_create_data.pop('usuario_data', None) # Eliminar usuario_data

            if persona_create_data.get('ci'):
                db_persona_ci = db.query(DBPersona).filter(DBPersona.ci == persona_create_data['ci']).first()
                if db_persona_ci:
                     raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Ya existe una persona con este CI: {persona_create_data['ci']}")
            
            new_persona = DBPersona(**persona_create_data)

            if rol_ids:
                roles = db.query(DBRol).filter(DBRol.rol_id.in_(rol_ids)).all()
                if len(roles) != len(rol_ids):
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Uno o más roles no fueron encontrados.")
                new_persona.roles = roles

            db.add(new_persona)
            db.flush() # Obtener el ID de la nueva persona

            proveedor_id_to_associate = new_persona.persona_id

        elif proveedor_data.empresa_data:
            # Opción 2: Crear una nueva Empresa y asociarla
            is_persona = False
            # Validar unicidad de Identificacion si no lo hace la DB o necesitas un error más específico
            if proveedor_data.empresa_data.identificacion:
                 db_empresa_identificacion = db.query(DBEmpresa).filter(DBEmpresa.identificacion == proveedor_data.empresa_data.identificacion).first()
                 if db_empresa_identificacion:
                      raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Ya existe una empresa con esta Identificación: {proveedor_data.empresa_data.identificacion}")

            # Crear la nueva Empresa
            new_empresa = DBEmpresa(**proveedor_data.empresa_data.model_dump(exclude_unset=True))
            db.add(new_empresa)
            db.flush() # Obtener el ID de la nueva empresa

            proveedor_id_to_associate = new_empresa.empresa_id

        elif proveedor_data.persona_id is not None:
            # Opción 3: Asociar una Persona existente por ID
            is_persona = True
            db_persona = db.query(DBPersona).filter(DBPersona.persona_id == proveedor_data.persona_id).first()
            if db_persona is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Persona con ID {proveedor_data.persona_id} no encontrada.")

            # Opcional: Verificar si esta Persona ya está asociada a otro proveedor
            if db_persona.proveedor: # Asume que la relación inversa 'proveedor' existe en el modelo Persona
                 raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"La Persona con ID {proveedor_data.persona_id} ya está asociada a un proveedor.")

            proveedor_id_to_associate = proveedor_data.persona_id

        elif proveedor_data.empresa_id is not None:
            # Opción 4: Asociar una Empresa existente por ID
            is_persona = False
            db_empresa = db.query(DBEmpresa).filter(DBEmpresa.empresa_id == proveedor_data.empresa_id).first()
            if db_empresa is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Empresa con ID {proveedor_data.empresa_id} no encontrada.")

            # Opcional: Verificar si esta Empresa ya está asociada a otro proveedor
            if db_empresa.proveedor: # Asume que la relación inversa 'proveedor' existe en el modelo Empresa
                 raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"La Empresa con ID {proveedor_data.empresa_id} ya está asociada a un proveedor.")

            proveedor_id_to_associate = proveedor_data.empresa_id

        else:
            # Esto no debería ocurrir si el validador Pydantic funciona, pero es un fallback seguro
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Debe proporcionar una opción de asociación/creación.")


        # *** 2. Crear el Proveedor ***
        new_proveedor = DBProveedor(
            estado=proveedor_data.estado, # Estado del proveedor (viene del esquema ProveedorCreate)
            persona_id=proveedor_id_to_associate if is_persona else None,
            empresa_id=proveedor_id_to_associate if not is_persona else None,
            # Si tu modelo Proveedor tuviera campos de auditoría (creado_por, modificado_por), los asignarías aquí:
            # creado_por=current_user.usuario_id
        )

        db.add(new_proveedor)
        db.commit() # Confirma la creación del Proveedor y la entidad asociada (si se creó)
        db.refresh(new_proveedor) # Refresca para obtener el proveedor_id

        # *** 3. Cargar las relaciones para la respuesta ***
        # Necesitamos cargar la relación correcta (persona o empresa) para que el response_model Proveedor la serialice
        query = db.query(DBProveedor).filter(DBProveedor.proveedor_id == new_proveedor.proveedor_id)
        if is_persona:
             # Carga Persona y su posible Usuario si existe la relación en Persona model
             query = query.options(joinedload(DBProveedor.persona).joinedload(DBPersona.usuario))
        else:
             # Carga Empresa
             query = query.options(joinedload(DBProveedor.empresa))

        db_proveedor_for_response = query.first()

        return db_proveedor_for_response # Retorna el objeto DBProveedor que FastAPI serializa a Proveedor

    except HTTPException as e:
        # Si ocurrió una HTTPException (ej. 400, 404), la lanzamos directamente
        db.rollback() # Asegura el rollback en caso de error validado
        raise e
    except Exception as e:
        # Para cualquier otro error inesperado, hacemos rollback y retornamos 500
        db.rollback()
        print(f"Error durante la creación de Proveedor (y entidad asociada): {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Ocurrió un error al crear el Proveedor.")


# --- Endpoint para Listar Proveedores ---
# Lo restringiremos a usuarios con ROLES_CAN_MANAGE_PROVEEDORES por defecto.
@router.get("/", response_model=ProveedorPagination) # Cambiado el response_model a ProveedorPagination
def read_proveedores(
    estado: Optional[EstadoEnum] = Query(None, description="Filtrar por estado"),
    tipo: Optional[str] = Query(None, description="Filtrar por tipo ('persona' o 'empresa')"), # NUEVO FILTRO por tipo
    search: Optional[str] = Query(None, description="Texto de búsqueda por nombre/razón social, CI/identificación"), # Búsqueda combinada
    skip: int = Query(0, ge=0, description="Número de elementos a omitir (paginación)"),
    limit: int = Query(100, gt=0, description="Número máximo de elementos a retornar (paginación)"),
    db: Session = Depends(get_db),
    current_user: auth_utils.Usuario = Depends(auth_utils.require_menu_access("/proveedores")) # Verificar acceso al menú de categorías
):
    """
    Obtiene una lista de Proveedores con opciones de filtro, búsqueda y paginación.
    Incluye la Persona o Empresa asociada.
    Accesible solo por usuarios con permisos de gestión de proveedores (por defecto).
    """
    # Iniciar la consulta cargando AMBAS relaciones (Persona y Empresa)
    # Esto es necesario porque el response_model Proveedor anida AMBAS,
    # aunque solo una tendrá datos por fila.
    query = db.query(DBProveedor).options(
        joinedload(DBProveedor.persona).joinedload(DBPersona.usuario), # Carga Persona y su posible Usuario si existe la relación
        joinedload(DBProveedor.empresa) # Carga Empresa
    )

    # Aplicar filtros
    if estado:
        query = query.filter(DBProveedor.estado == estado)

    # Aplicar filtro por tipo
    if tipo:
        if tipo.lower() == 'persona':
            query = query.filter(DBProveedor.persona_id.isnot(None)) # Filtra donde persona_id NO es NULL
        elif tipo.lower() == 'empresa':
            query = query.filter(DBProveedor.empresa_id.isnot(None)) # Filtra donde empresa_id NO es NULL
        else:
             raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Valor de filtro 'tipo' inválido. Use 'persona' o 'empresa'.")


    # Aplicar búsqueda combinada por nombre/razón social, CI/identificación
    if search:
        # Para que la búsqueda funcione en campos de relaciones, necesitamos hacer un LEFT OUTER JOIN explícito
        # con las tablas Persona y Empresa. Esto asegura que los proveedores sin una entidad asociada
        # (aunque nuestra lógica de creación lo impide, es buena práctica) no se excluyan y que los filtros funcionen.
        query = query.outerjoin(DBPersona, DBProveedor.persona_id == DBPersona.persona_id)
        query = query.outerjoin(DBEmpresa, DBProveedor.empresa_id == DBEmpresa.empresa_id)

        query = query.filter(
            or_(
                # Búsqueda en campos de Persona
                DBPersona.nombre.ilike(f"%{search}%"),
                DBPersona.apellido_paterno.ilike(f"%{search}%"),
                DBPersona.apellido_materno.ilike(f"%{search}%"),
                DBPersona.ci.ilike(f"%{search}%"),
                DBPersona.email.ilike(f"%{search}%"),
                # Búsqueda en campos de Empresa
                DBEmpresa.razon_social.ilike(f"%{search}%"),
                DBEmpresa.nombre_contacto.ilike(f"%{search}%"),
                DBEmpresa.identificacion.ilike(f"%{search}%"),
                DBEmpresa.email.ilike(f"%{search}%")
            )
        )

    # Obtener el total de elementos antes de aplicar la paginación
    total_items = query.count()

    # Aplicar paginación
    proveedores = query.offset(skip).limit(limit).all()

    return {"items": proveedores, "total": total_items} # Retorna un diccionario con items y total

# --- Endpoint para Obtener un Proveedor por ID ---
# Lo restringiremos a usuarios con ROLES_CAN_MANAGE_PROVEEDORES por defecto.
@router.get("/{proveedor_id}", response_model=Proveedor) # Retorna el esquema Proveedor
def read_proveedor(
    proveedor_id: int,
    db: Session = Depends(get_db),
    current_user: auth_utils.Usuario = Depends(auth_utils.require_menu_access("/proveedores")) # Verificar acceso al menú de categorías
):
    """
    Obtiene la información de un Proveedor específico por su ID.
    Incluye la Persona o Empresa asociada.
    Accesible solo por usuarios con permisos de gestión de proveedores (por defecto).
    """
    # Obtener el proveedor por ID cargando AMBAS relaciones
    proveedor = db.query(DBProveedor).options(
        joinedload(DBProveedor.persona).joinedload(DBPersona.usuario), # Carga Persona y su posible Usuario
        joinedload(DBProveedor.empresa) # Carga Empresa
    ).filter(DBProveedor.proveedor_id == proveedor_id).first()

    if proveedor is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Proveedor no encontrado")

    return proveedor # Retorna el objeto DBProveedor que FastAPI serializa a Proveedor


# --- Endpoint para Actualizar un Proveedor por ID (Permite actualizar Persona/Empresa asociada) ---
@router.put("/{proveedor_id}", response_model=Proveedor)
def update_proveedor(
    proveedor_id: int,
    proveedor_update: ProveedorUpdate, # Usa el esquema modificado con datos de actualización anidados
    db: Session = Depends(get_db),
    current_user: auth_utils.Usuario = Depends(auth_utils.require_menu_access("/proveedores")) # Verificar acceso al menú de categorías
):
    """
    Actualiza la información de un Proveedor existente por su ID, incluyendo datos de la Persona o Empresa asociada.
    Solo accesible por usuarios con permisos de gestión de proveedores.
    """
    # 1. Obtener el proveedor por ID (cargando relaciones para respuesta)
    db_proveedor = db.query(DBProveedor).options(
        joinedload(DBProveedor.persona).joinedload(DBPersona.usuario), # Carga Persona y su posible Usuario
        joinedload(DBProveedor.empresa) # Carga Empresa
    ).filter(DBProveedor.proveedor_id == proveedor_id).first()

    if db_proveedor is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Proveedor no encontrado.")

    # 2. Aplicar las actualizaciones del estado del Proveedor si está presente en el payload
    update_data_proveedor = proveedor_update.model_dump(exclude_unset=True, exclude={'persona_data', 'empresa_data'})
    if 'estado' in update_data_proveedor:
        db_proveedor.estado = update_data_proveedor['estado']

    # Si tu modelo Proveedor tuviera campo modificado_por, lo asignarías aquí:
    # db_proveedor.modificado_por = current_user.usuario_id


    # *** 3. Actualizar la Persona o Empresa asociada si los datos están en el payload ***

    if proveedor_update.persona_data:
        # Se enviaron datos para actualizar la Persona. Verificar que el proveedor ES una Persona.
        if not db_proveedor.persona:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Este proveedor no es una Persona.")

        # Actualizar la Persona asociada
        update_data_persona = proveedor_update.persona_data.model_dump(exclude_unset=True)
        for field, value in update_data_persona.items():
            setattr(db_proveedor.persona, field, value)

        # Opcional: Validaciones de unicidad de CI/Identificacion al actualizar Persona
        if 'ci' in update_data_persona and update_data_persona['ci'] != db_proveedor.persona.ci:
             existing_persona_ci = db.query(DBPersona).filter(DBPersona.ci == update_data_persona['ci']).first()
             # Asegurarse de que si existe, no sea la misma persona que estamos actualizando
             if existing_persona_ci and existing_persona_ci.persona_id != db_proveedor.persona.persona_id:
                  raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Ya existe otra persona con este CI: {update_data_persona['ci']}")

        if 'identificacion' in update_data_persona and update_data_persona['identificacion'] != db_proveedor.persona.identificacion:
             existing_persona_identificacion = db.query(DBPersona).filter(DBPersona.identificacion == update_data_persona['identificacion']).first()
             if existing_persona_identificacion and existing_persona_identificacion.persona_id != db_proveedor.persona.persona_id:
                  raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Ya existe otra persona con esta Identificación: {update_data_persona['identificacion']}")


    elif proveedor_update.empresa_data:
        # Se enviaron datos para actualizar la Empresa. Verificar que el proveedor ES una Empresa.
        if not db_proveedor.empresa:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Este proveedor no es una Empresa.")

        # Actualizar la Empresa asociada
        update_data_empresa = proveedor_update.empresa_data.model_dump(exclude_unset=True)
        for field, value in update_data_empresa.items():
            setattr(db_proveedor.empresa, field, value)

        # Opcional: Validaciones de unicidad de Identificacion al actualizar Empresa
        if 'identificacion' in update_data_empresa and update_data_empresa['identificacion'] != db_proveedor.empresa.identificacion:
             existing_empresa_identificacion = db.query(DBEmpresa).filter(DBEmpresa.identificacion == update_data_empresa['identificacion']).first()
             if existing_empresa_identificacion and existing_empresa_identificacion.empresa_id != db_proveedor.empresa.empresa_id:
                  raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Ya existe otra empresa con esta Identificación: {update_data_empresa['identificacion']}")


    # Nota: Si se envían datos tanto en persona_data como en empresa_data en el mismo payload PUT,
    # esto no está validado explícitamente en el esquema ProveedorUpdate. La lógica actual procesaría
    # el primero que encuentre (persona_data) y el segundo sería ignorado (o podría causar un error
    # si el proveedor no es de ese tipo). Podrías añadir un validador en ProveedorUpdate
    # o una verificación al inicio de esta función para asegurar que solo uno de ellos se envía.
    # Por simplicidad, confiamos en que el frontend enviará solo el relevante.


    db.commit() # Confirma los cambios en Proveedor y la entidad asociada
    db.refresh(db_proveedor) # Refresca para obtener los cambios confirmados

    # Recargar el objeto con relaciones si es necesario (refresh debería bastar)
    # db_proveedor_for_response = db.query(DBProveedor).options(...).filter(...).first()

    return db_proveedor # Retorna el objeto DBProveedor actualizado que FastAPI serializa a Proveedor


# --- Endpoint para Eliminar/Desactivar un Proveedor por ID (Soft Delete) ---
@router.delete("/{proveedor_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_proveedor(
    proveedor_id: int,
    db: Session = Depends(get_db),
    current_user: auth_utils.Usuario = Depends(auth_utils.require_menu_access("/proveedores")) # Verificar acceso al menú de categorías
):
    """
    Desactiva (cambia el estado a inactivo) un Proveedor por su ID.
    Solo accesible por usuarios con permisos de gestión de proveedores.
    """
    db_proveedor = db.query(DBProveedor).filter(DBProveedor.proveedor_id == proveedor_id).first()
    if db_proveedor is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Proveedor no encontrado.")

    if db_proveedor.estado == EstadoEnum.inactivo:
         raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="El proveedor ya está inactivo.")

    # Implementar Soft Delete: cambiar el estado
    db_proveedor.estado = EstadoEnum.inactivo

    # 🔄 SINCRONIZACIÓN AUTOMÁTICA: Desactivar persona relacionada si es de tipo persona
    if db_proveedor.persona_id:
        # Cargar la persona relacionada
        db_persona = db.query(DBPersona).filter(
            DBPersona.persona_id == db_proveedor.persona_id
        ).first()
        
        if db_persona and db_persona.estado == EstadoEnum.activo:
            db_persona.estado = EstadoEnum.inactivo
            print(f"🔄 Sincronización: Desactivando persona ID {db_persona.persona_id} asociada a proveedor ID {proveedor_id}")
            
            # Si la persona tiene un usuario asociado, también lo desactivamos
            if db_persona.usuario and db_persona.usuario.estado == EstadoEnum.activo:
                db_persona.usuario.estado = EstadoEnum.inactivo
                print(f"🔄 Sincronización: Desactivando usuario ID {db_persona.usuario.usuario_id} asociado a persona ID {db_persona.persona_id}")

    # Si tu modelo Proveedor tuviera campo modificado_por, lo asignarías aquí:
    # db_proveedor.modificado_por = current_user.usuario_id

    db.commit()

    return {}


# --- ENDPOINT: Activar un Proveedor por ID (PATCH /proveedores/{proveedor_id}) ---
@router.patch("/{proveedor_id}", response_model=Proveedor)
def activate_proveedor(
    proveedor_id: int,
    db: Session = Depends(get_db),
    current_user: auth_utils.Usuario = Depends(auth_utils.require_menu_access("/proveedores")) # Verificar acceso al menú de categorías
):
    """
    Activa (cambia el estado a activo) un Proveedor por su ID.
    Solo accesible por usuarios con permisos de gestión de proveedores.
    """
    db_proveedor = db.query(DBProveedor).options(
        joinedload(DBProveedor.persona).joinedload(DBPersona.usuario), # Carga Persona y su posible Usuario
        joinedload(DBProveedor.empresa) # Carga Empresa
    ).filter(DBProveedor.proveedor_id == proveedor_id).first()

    if db_proveedor is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Proveedor no encontrado.")

    if db_proveedor.estado == EstadoEnum.activo:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="El proveedor ya está activo.")

    db_proveedor.estado = EstadoEnum.activo

    # 🔄 SINCRONIZACIÓN AUTOMÁTICA: Activar persona relacionada si es de tipo persona
    if db_proveedor.persona_id:
        # Cargar la persona relacionada
        db_persona = db.query(DBPersona).filter(
            DBPersona.persona_id == db_proveedor.persona_id
        ).first()
        
        if db_persona and db_persona.estado == EstadoEnum.inactivo:
            db_persona.estado = EstadoEnum.activo
            print(f"🔄 Sincronización: Activando persona ID {db_persona.persona_id} asociada a proveedor ID {proveedor_id}")
            
            # Activar usuario asociado si existe y está inactivo
            if db_persona.usuario and db_persona.usuario.estado == EstadoEnum.inactivo:
                db_persona.usuario.estado = EstadoEnum.activo
                print(f"🔄 Sincronización: Activando usuario ID {db_persona.usuario.usuario_id} asociado a persona ID {db_persona.persona_id}")

    # Si tu modelo Proveedor tuviera campo modificado_por, lo asignarías aquí:
    # db_proveedor.modificado_por = current_user.usuario_id

    db.commit()
    db.refresh(db_proveedor)

    return db_proveedor

