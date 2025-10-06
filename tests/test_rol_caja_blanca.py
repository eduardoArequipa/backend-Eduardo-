"""
PRUEBAS DE CAJA BLANCA - Módulo Roles
Objetivo: Testear la lógica interna conociendo la implementación

Cobertura objetivo:
- Statement Coverage: 100% (todas las líneas ejecutadas)
- Branch Coverage: 100% (todos los if/else probados)
- Path Coverage: Todas las rutas de ejecución
"""
import pytest
from fastapi import HTTPException
from sqlalchemy.exc import SQLAlchemyError
from unittest.mock import patch, MagicMock

from app.routes.rol import create_rol, update_rol, delete_rol
from app.models.rol import Rol as DBRol
from app.models.persona_rol import PersonaRol as DBPersonaRol
from app.schemas.rol import RolCreate, RolUpdate

class TestCreateRolCajaBlanca:
    """
    CAJA BLANCA: create_rol function

    Rutas de ejecución identificadas:
    1. existing_rol = True → HTTPException(400)
    2. existing_rol = False, creation success → return DBRol
    3. existing_rol = False, DB error → HTTPException(500)
    """

    def test_rama_1_rol_duplicado_case_insensitive(self, db_session, mock_user):
        """
        RAMA 1: Validación de rol duplicado (case-insensitive)

        Flujo interno:
        - Línea 75-77: Query con .ilike()
        - Línea 79: if existing_rol (TRUE)
        - Líneas 80-83: HTTPException(400)
        """
        # ARRANGE: Crear rol existente en BD (nombre único para test)
        import time
        unique_name = f"TestAdmin_{int(time.time())}"
        existing_rol = DBRol(
            nombre_rol=unique_name,
            descripcion="Rol existente",
            estado="activo"
        )
        db_session.add(existing_rol)
        db_session.commit()

        # Crear datos con mismo nombre pero diferente case y espacios
        rol_data = RolCreate(
            rol_id=998,  # Temporal
            nombre_rol=f"  {unique_name.upper()}  ",  # Espacios + mayúsculas
            descripcion="Intento de duplicado"
        )

        # ACT & ASSERT: Debe detectar duplicado y lanzar HTTPException
        with pytest.raises(HTTPException) as exc_info:
            create_rol(rol_data, db_session, mock_user)

        # Verificar detalles específicos de la excepción
        assert exc_info.value.status_code == 400
        assert "Ya existe un rol con el nombre" in str(exc_info.value.detail)
        assert unique_name.upper() in str(exc_info.value.detail)

    def test_rama_2_creacion_exitosa_completa(self, db_session, mock_user):
        """
        RAMA 2: Creación exitosa de rol

        Flujo interno:
        - Línea 75-77: Query (retorna None)
        - Línea 79: if existing_rol (FALSE)
        - Línea 86: DBRol(**rol_data.model_dump())
        - Línea 87: db.add(db_rol)
        - Línea 88: db.commit()
        - Línea 89: db.refresh(db_rol)
        - Línea 90: return db_rol
        """
        # ARRANGE: Datos para rol nuevo (incluyendo rol_id como requiere tu schema)
        rol_data = RolCreate(
            rol_id=999,  # Temporal, se auto-genera en la BD
            nombre_rol="Vendedor",
            descripcion="Rol para ventas"
        )

        # ACT: Ejecutar creación
        result = create_rol(rol_data, db_session, mock_user)

        # ASSERT: Verificar objeto retornado
        assert result is not None
        assert result.nombre_rol == "Vendedor"
        assert result.descripcion == "Rol para ventas"
        assert result.rol_id is not None
        assert hasattr(result, 'estado')

        # VERIFICACIÓN ADICIONAL: Confirmar persistencia en BD
        db_rol = db_session.query(DBRol).filter(
            DBRol.nombre_rol == "Vendedor"
        ).first()
        assert db_rol is not None
        assert db_rol.descripcion == "Rol para ventas"

    def test_rama_3_error_base_datos_rollback(self, db_session, mock_user):
        """
        RAMA 3: Error en base de datos durante creación
        Simplificado: Crear rol con nombre que cause constraint error
        """
        # ARRANGE: Crear rol válido pero después simular error con mock
        rol_data = RolCreate(
            rol_id=997,  # Temporal
            nombre_rol="RolError",
            descripcion="Este rol causará error"
        )

        # Simular error durante commit usando side_effect en la sesión
        original_commit = db_session.commit
        def mock_commit():
            raise SQLAlchemyError("Error simulado de BD")

        db_session.commit = mock_commit

        # ACT & ASSERT: Debe manejar error
        with pytest.raises(HTTPException) as exc_info:
            create_rol(rol_data, db_session, mock_user)

        # Restaurar commit original
        db_session.commit = original_commit

        # Verificar manejo correcto del error
        assert exc_info.value.status_code == 500
        assert "Error al crear el rol" in str(exc_info.value.detail)

    def test_cobertura_logica_ilike_strip(self, db_session, mock_user):
        """
        CAJA BLANCA: Verificar lógica específica de .ilike() y .strip()

        Objetivo: Asegurar que las funciones SQL funcionan como esperado
        """
        # ARRANGE: Crear rol base
        base_rol = DBRol(
            nombre_rol="manager",
            descripcion="Base role",
            estado="activo"
        )
        db_session.add(base_rol)
        db_session.commit()

        # TEST CASES para diferentes variaciones de nombre
        test_cases = [
            "MANAGER",           # Case diferente
            "  manager  ",       # Espacios
            "  MANAGER  ",       # Espacios + case
            "Manager",           # Primera letra mayúscula
        ]

        for i, test_name in enumerate(test_cases):
            rol_data = RolCreate(
                rol_id=990 + i,  # Temporal, diferentes IDs
                nombre_rol=test_name,
                descripcion=f"Duplicate test for {test_name}"
            )

            # ACT & ASSERT: Cada variación debe detectar duplicado
            with pytest.raises(HTTPException) as exc_info:
                create_rol(rol_data, db_session, mock_user)

            assert exc_info.value.status_code == 400


class TestUpdateRolCajaBlanca:
    """
    CAJA BLANCA: update_rol function

    Rutas identificadas:
    1. Rol no existe → HTTPException(404)
    2. Nombre duplicado → HTTPException(400)
    3. Actualización exitosa → return updated_rol
    4. Error de BD → HTTPException(500)
    """

    def test_rama_rol_no_encontrado(self, db_session, mock_user):
        """
        RAMA 1: Rol inexistente

        Verifica líneas del update_rol que manejan rol no encontrado
        """
        # ARRANGE: ID que no existe
        rol_id = 999
        rol_data = RolUpdate(nombre_rol="NoImporta")

        # ACT & ASSERT
        with pytest.raises(HTTPException) as exc_info:
            update_rol(rol_id, rol_data, db_session, mock_user)

        assert exc_info.value.status_code == 404
        assert "Rol no encontrado" in str(exc_info.value.detail)

    def test_rama_actualizacion_exitosa(self, db_session, mock_user, create_test_rol):
        """
        RAMA 3: Actualización exitosa

        Verifica flujo completo de actualización
        """
        # ARRANGE: Crear rol existente
        rol_existente = create_test_rol("RolOriginal", "Descripción original")

        # Datos para actualizar
        rol_data = RolUpdate(
            nombre_rol="RolActualizado",
            descripcion="Nueva descripción"
        )

        # ACT
        result = update_rol(rol_existente.rol_id, rol_data, db_session, mock_user)

        # ASSERT: Verificar actualización
        assert result.nombre_rol == "RolActualizado"
        assert result.descripcion == "Nueva descripción"

        # Verificar persistencia
        db_rol = db_session.query(DBRol).filter(
            DBRol.rol_id == rol_existente.rol_id
        ).first()
        assert db_rol.nombre_rol == "RolActualizado"


class TestDeleteRolCajaBlanca:
    """
    CAJA BLANCA: delete_rol function

    Rutas identificadas:
    1. Rol no existe → HTTPException(404)
    2. Rol asignado a usuarios → HTTPException(400)
    3. Eliminación exitosa → Success response
    """

    def test_rama_rol_con_usuarios_asignados(self, db_session, mock_user, create_test_rol):
        """
        RAMA 2: Rol asignado a usuarios

        Verifica que no se puede eliminar rol en uso
        """
        # ARRANGE: Crear rol y asignarlo a usuario ficticio
        rol = create_test_rol("RolAsignado")

        # Simular asignación (normalmente sería persona_rol)
        persona_rol = DBPersonaRol(
            persona_id=1,
            rol_id=rol.rol_id
        )
        db_session.add(persona_rol)
        db_session.commit()

        # ACT & ASSERT
        with pytest.raises(HTTPException) as exc_info:
            delete_rol(rol.rol_id, db_session, mock_user)

        assert exc_info.value.status_code == 400
        assert "persona" in str(exc_info.value.detail).lower()

    def test_rama_eliminacion_exitosa(self, db_session, mock_user, create_test_rol):
        """
        RAMA 3: Eliminación exitosa

        Verifica eliminación de rol sin usuarios asignados
        """
        # ARRANGE: Rol sin usuarios asignados
        rol = create_test_rol("RolSinUsuarios")
        rol_id = rol.rol_id

        # ACT
        response = delete_rol(rol_id, db_session, mock_user)

        # ASSERT: Verificar respuesta exitosa
        assert response.status_code == 204

        # Verificar que se eliminó de BD
        rol_eliminado = db_session.query(DBRol).filter(
            DBRol.rol_id == rol_id
        ).first()
        assert rol_eliminado is None


# HELPER FUNCTIONS PARA TESTS
def mock_auth_dependency():
    """Helper para mockear dependencias de autenticación"""
    user = MagicMock()
    user.usuario_id = 1
    return user