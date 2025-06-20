# backEnd/app/routes/persona.py
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session, joinedload # Importar joinedload
from sqlalchemy import or_ # Importar para búsqueda
from sqlalchemy import not_ # Importa la función not_

from .. import auth as auth_utils
from ..database import get_db
from ..models.persona import Persona as DBPersona # Importar el modelo SQLAlchemy
from ..models.usuario import Usuario as DBUsuario # Necesario para el join de rol
from ..models.rol import Rol as DBRol # Necesario para el join de rol
from ..models.enums import EstadoEnum, GeneroEnum
# Importar los esquemas Pydantic necesarios
from ..schemas.persona import Persona, PersonaCreate, PersonaUpdate,PersonaNested
# Aunque usamos PersonaNested en esquemas de Usuario, aquí usamos Persona

router = APIRouter(
    prefix="/personas",
    tags=["personas"]
)

ROLES_CAN_MANAGE_PERSONS = ["Administrador", "Empleado"]

# Modificar el endpoint POST /personas/
@router.post("/", response_model=Persona, status_code=status.HTTP_201_CREATED)
# NOTA: Si quieres retornar el Usuario creado, podrías cambiar response_model
# a something like Union[Persona, UsuarioReadAudit] o definir un esquema de respuesta personalizado.
# Por ahora, mantengamos response_model=Persona como indica la ruta principal.
def create_persona(
    persona: PersonaCreate, # Este esquema ahora incluye usuario_data opcional
    db: Session = Depends(get_db),
    current_user: auth_utils.Usuario = Depends(auth_utils.get_current_active_user_with_role(ROLES_CAN_MANAGE_PERSONS))
):
    """
    Crea una nueva Persona y opcionalmente un Usuario asociado con roles.
    """
    db.begin_nested() # Iniciar transacción anidada

    try:
        # 1. Crear la Persona
        # Separar los datos de persona de los datos de usuario opcionales
        persona_data_dict = persona.model_dump(exclude={'usuario_data'}, exclude_unset=True)

        # Validar unicidad de CI/Identificacion si no lo hace la DB o necesitas un error más específico
        if persona_data_dict.get('ci'):
            db_persona_ci = db.query(DBPersona).filter(DBPersona.ci == persona_data_dict['ci']).first()
            if db_persona_ci:
                 db.rollback()
                 raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Ya existe una persona con este CI")
        if persona_data_dict.get('identificacion'):
             db_persona_identificacion = db.query(DBPersona).filter(DBPersona.identificacion == persona_data_dict['identificacion']).first()
             if db_persona_identificacion:
                 db.rollback()
                 raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Ya existe una persona con esta Identificación")


        new_persona = DBPersona(**persona_data_dict)
        db.add(new_persona)
        db.flush() # Obtener el persona_id antes de crear el usuario

        created_usuario = None # Variable para almacenar el usuario si se crea

        # 2. Crear Usuario y Asignar Roles (Si se proporcionaron datos de usuario)
        if persona.usuario_data:
            usuario_data = persona.usuario_data

            # Validar unicidad del nombre de usuario
            db_usuario_nombre = db.query(DBUsuario).filter(DBUsuario.nombre_usuario == usuario_data.nombre_usuario).first()
            if db_usuario_nombre:
                db.rollback()
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Ya existe un usuario con este nombre de usuario")

            # Hashear la contraseña
            hashed_password = auth_utils.get_password_hash(usuario_data.contraseña)

            new_usuario = DBUsuario(
                persona_id=new_persona.persona_id, # Asociar al ID de la persona recién creada
                nombre_usuario=usuario_data.nombre_usuario,
                contraseña=hashed_password,
                estado=usuario_data.estado,
                foto_ruta=usuario_data.foto_ruta,
                creado_por=current_user.usuario_id # Registrar quién creó el usuario
            )
            db.add(new_usuario)
            db.flush() # Obtener el usuario_id para asignar roles

            created_usuario = new_usuario # Almacenar referencia al usuario creado

            # Asignar Roles iniciales si se proporcionaron
            if usuario_data.rol_ids:
                roles_a_asignar = db.query(DBRol).filter(DBRol.rol_id.in_(usuario_data.rol_ids)).all()

                if len(roles_a_asignar) != len(usuario_data.rol_ids):
                    # Si no se encontraron todos los roles
                    db.rollback()
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Uno o más IDs de rol proporcionados no son válidos.")

                # Asociar los roles al nuevo usuario
                new_usuario.roles.extend(roles_a_asignar)
                # SQLAlchemy manejará la tabla de asociación usuario_roles

        # 3. Confirmar la transacción
        db.commit()

        # 4. Refrescar la persona y el usuario (si se creó) para la respuesta
        db.refresh(new_persona)
        if created_usuario:
            # Asegúrate de que la relación 'usuario' en new_persona esté cargada
            # Para que el esquema Persona pueda incluir el usuario anidado si aplica
            # Esto puede requerir joinedload en la consulta si no usas lazy='joined'
            # O simplemente refrescar la relación:
            db.refresh(new_persona, attribute_names=['usuario'])
            # Si quieres que el esquema de respuesta de Persona incluya el usuario anidado,
            # tu esquema schemas.persona.Persona debería tener un campo usuario: Optional[schemas.usuario.UsuarioNested] = None
            # y el modelo persona.py debería tener la relación `usuario = relationship(...)`.
            # Ya definimos esto, así que refrescando la relación debería bastar para que Pydantic lo mapee.


        return new_persona # Retorna el objeto Persona creado

    except HTTPException as e:
        raise e
    except Exception as e:
        db.rollback()
        print(f"Error durante la creación de Persona (y Usuario opcional): {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Ocurrió un error al crear la Persona (y Usuario opcional).")


@router.get("/", response_model=List[Persona]) # <-- CORREGIDO: Usamos una Lista del esquema Pydantic Persona
def read_personas(
    estado: Optional[EstadoEnum] = Query(None, description="Filtrar por estado"),
    genero: Optional[GeneroEnum] = Query(None, description="Filtrar por género ('M' o 'F')"),
    search: Optional[str] = Query(None, description="Texto de búsqueda por nombre, apellido, CI o identificación"),
    rol_id: Optional[int] = Query(None, description="Filtrar por Personas que tienen un Usuario asociado con este ID de Rol"),
    skip: int = Query(0, ge=0, description="Número de elementos a omitir (paginación)"),
    limit: int = Query(100, gt=0, description="Número máximo de elementos a retornar (paginación)"),
    db: Session = Depends(get_db),
    current_user: auth_utils.Usuario = Depends(auth_utils.get_current_active_user)
):
    """
    Obtiene una lista de Personas, con opciones de filtro, búsqueda, paginación
    y filtro por Rol asociado al Usuario (si la persona tiene uno).
    """
    query = db.query(DBPersona)

    if estado:
        query = query.filter(DBPersona.estado == estado)

    if genero:
         query = query.filter(DBPersona.genero == genero)

    if search:
        query = query.filter(
            or_(
                DBPersona.nombre.ilike(f"%{search}%"),
                DBPersona.apellido_paterno.ilike(f"%{search}%"),
                DBPersona.apellido_materno.ilike(f"%{search}%"),
                DBPersona.ci.ilike(f"%{search}%"),
                DBPersona.email.ilike(f"%{search}%")
                
            )
        )

    if rol_id is not None:
        # Necesitamos unir personas -> usuarios -> usuario_roles -> roles
        # Usamos un inner join si solo queremos personas que *tienen* un usuario con ese rol
        # Usamos un left join si queremos todas las personas, pero solo filtrar aquellas que tienen un usuario con ese rol
        # La interpretación "Personas que tienen un Usuario asociado con este ID de Rol" sugiere un inner join o un where exist
        query = query.join(DBPersona.usuario).join(DBUsuario.roles).filter(DBRol.rol_id == rol_id)

    personas = query.offset(skip).limit(limit).all()

    return personas
# *** NUEVO ENDPOINT: Listar Personas SIN Usuario Asociado ***
@router.get("/without-user/", response_model=List[PersonaNested]) # Usamos PersonaNested para la respuesta
# Proteger este endpoint: Solo roles que pueden crear usuarios necesitan esta lista
# (ej: Administrador, o el mismo rol que puede POST /usuarios/)
def read_personas_without_user(
    db: Session = Depends(get_db),
    current_user: auth_utils.Usuario = Depends(auth_utils.get_current_active_user_with_role(["Administrador"])) # Ajusta el rol requerido
):
    """
    Obtiene una lista de Personas que NO tienen un Usuario asociado.
    Útil para selectores al crear nuevos Usuarios.
    """
    # Realizar un LEFT JOIN desde Persona a Usuario y filtrar donde el usuario es NULL
    # O, más simple y a menudo más eficiente, usar un WHERE NOT EXISTS o filtrar en la relación inversa
    # Usamos .has() para verificar si la relación DBUsuario existe para una DBPersona
    personas = db.query(DBPersona).filter(
        not_(DBPersona.usuario.has()) # Filtra donde NO existe un Usuario asociado a esta Persona
    ).all()

    # Si quieres paginación para esta lista, añade skip y limit como Query parameters

    return personas # FastAPI serializará esto a List[PersonaNested]
@router.get("/{persona_id}", response_model=Persona) # <-- CORREGIDO: Usamos el esquema Pydantic Persona
def read_persona(
    persona_id: int,
    db: Session = Depends(get_db),
    current_user: auth_utils.Usuario = Depends(auth_utils.get_current_active_user)
):
    """Obtiene la información de una Persona específica por su ID."""
    persona = db.query(DBPersona).filter(DBPersona.persona_id == persona_id).first()

    if persona is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Persona no encontrada")
    return persona

@router.put("/{persona_id}", response_model=Persona) # <-- CORREGIDO: Usamos el esquema Pydantic Persona
def update_persona(
    persona_id: int,
    persona: PersonaUpdate,
    db: Session = Depends(get_db),
    current_user: auth_utils.Usuario = Depends(auth_utils.get_current_active_user_with_role(ROLES_CAN_MANAGE_PERSONS))
):
    """Actualiza la información de una Persona existente por su ID."""
    db_persona = db.query(DBPersona).filter(DBPersona.persona_id == persona_id).first()
    if db_persona is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Persona no encontrada")

    if persona.ci is not None and persona.ci != db_persona.ci:
         existing_persona = db.query(DBPersona).filter(DBPersona.ci == persona.ci).first()
         if existing_persona:
              raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Ya existe una persona con este CI")
 
    for field, value in persona.model_dump(exclude_unset=True).items():
        setattr(db_persona, field, value)

    db.commit()
    db.refresh(db_persona)
    return db_persona

@router.delete("/{persona_id}", status_code=status.HTTP_204_NO_CONTENT) # No model for 204
def delete_persona(
    persona_id: int,
    db: Session = Depends(get_db),
    current_user: auth_utils.Usuario = Depends(auth_utils.get_current_active_user_with_role(ROLES_CAN_MANAGE_PERSONS))
):
    """
    Elimina (desactiva) una Persona por su ID.
    """
    db_persona = db.query(DBPersona).filter(DBPersona.persona_id == persona_id).first()
    if db_persona is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Persona no encontrada")

    db_persona.estado = EstadoEnum.inactivo
    db.commit()

    return {}

@router.patch("/{persona_id}/activar", status_code=status.HTTP_204_NO_CONTENT)  
def activate_persona(
    persona_id: int,
    db: Session = Depends(get_db),
    current_user: auth_utils.Usuario = Depends(auth_utils.get_current_active_user_with_role(ROLES_CAN_MANAGE_PERSONS))
):
    """
    Activa una Persona por su ID.
    """
    db_persona = db.query(DBPersona).filter(DBPersona.persona_id == persona_id).first()
    if db_persona is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Persona no encontrada")

    db_persona.estado = EstadoEnum.activo
    db.commit()

    return {}
# Aquí podrías agregar más endpoints relacionados con la entidad Persona