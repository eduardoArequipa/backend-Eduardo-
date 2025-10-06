"""
Configuración global para todas las pruebas pytest
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from unittest.mock import MagicMock

from app.database import get_db
from app.main import app
from app.models.base import Base
from app.models.rol import Rol as DBRol
from app.models.usuario import Usuario as DBUsuario
from app.models.persona import Persona as DBPersona

# Base de datos PostgreSQL separada para tests
SQLALCHEMY_DATABASE_URL = "postgresql://postgres:1234@localhost:5432/comercial_eduardo"
engine = create_engine(SQLALCHEMY_DATABASE_URL)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

@pytest.fixture
def db_session():
    """
    Crea una sesión con transacción que se revierte al final.
    SEGURO: No modifica datos reales, solo usa rollback.
    """
    connection = engine.connect()
    transaction = connection.begin()
    session = TestingSessionLocal(bind=connection)

    try:
        yield session
    finally:
        session.close()
        transaction.rollback()  # Revierte cambios sin afectar BD real
        connection.close()

@pytest.fixture
def client(db_session):
    """
    Cliente HTTP de pruebas con la base de datos mockeada.
    """
    def get_test_db():
        yield db_session

    app.dependency_overrides[get_db] = get_test_db

    with TestClient(app) as client:
        yield client

    # Limpiar overrides después del test
    app.dependency_overrides.clear()

@pytest.fixture
def mock_user():
    """
    Usuario mockeado para pruebas que requieren autenticación.
    """
    user = MagicMock()
    user.usuario_id = 1
    user.email = "admin@test.com"
    user.persona_id = 1
    return user

@pytest.fixture
def sample_rol_data():
    """
    Datos de ejemplo para crear roles en tests.
    """
    return {
        "nombre_rol": "TestRole",
        "descripcion": "Rol de prueba para testing",
        "estado": "activo"
    }

@pytest.fixture
def create_test_rol(db_session):
    """
    Factory function para crear roles de prueba en la BD.
    """
    def _create_rol(nombre="TestRole", descripcion="Test Description", rol_id=None):
        rol = DBRol(
            nombre_rol=nombre,
            descripcion=descripcion,
            estado="activo"
        )
        if rol_id:
            rol.rol_id = rol_id
        db_session.add(rol)
        db_session.commit()
        db_session.refresh(rol)
        return rol

    return _create_rol