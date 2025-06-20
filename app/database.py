from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv
import os

load_dotenv()

SQLALCHEMY_DATABASE_URL = os.getenv("DATABASE_URL")

# Ajusta pool_size y max_overflow según tus necesidades
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    pool_size=10,          # Conexiones activas máximas en el pool
    max_overflow=20,       # Conexiones adicionales si pool_size se agota
    pool_pre_ping=True,    # Verifica conexiones antes de usarlas
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
