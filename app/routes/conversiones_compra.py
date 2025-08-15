from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from .. import auth as auth_utils
from ..database import get_db
from ..models.conversiones_compra import ConversionesCompra as DBConversionesCompra
from ..models.producto import Producto as DBProducto
from ..schemas.conversiones_compra import (
    ConversionesCompra,
    ConversionesCompraCreate,
    ConversionesCompraUpdate
)

router = APIRouter(
    prefix="/conversiones-compra",
    tags=["conversiones-compra"]
)

@router.post("/", response_model=ConversionesCompra, status_code=status.HTTP_201_CREATED)
def create_conversion_compra(
    conversion: ConversionesCompraCreate,
    db: Session = Depends(get_db),
    current_user: auth_utils.Usuario = Depends(auth_utils.require_menu_access("/conversiones-compra"))
):
    db_producto = db.query(DBProducto).filter(DBProducto.producto_id == conversion.producto_id).first()
    if not db_producto:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Producto no encontrado.")

    existing_conversion = db.query(DBConversionesCompra).filter(
        DBConversionesCompra.producto_id == conversion.producto_id,
        DBConversionesCompra.nombre_presentacion == conversion.nombre_presentacion
    ).first()
    if existing_conversion:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Ya existe una presentación con el nombre '{conversion.nombre_presentacion}' para este producto.")

    db_conversion = DBConversionesCompra(**conversion.model_dump())
    db.add(db_conversion)
    db.commit()
    db.refresh(db_conversion)
    return db_conversion

@router.get("/", response_model=List[ConversionesCompra])
def read_conversiones_compra(
    db: Session = Depends(get_db),
    current_user: auth_utils.Usuario = Depends(auth_utils.require_menu_access("/conversiones-compra"))
):
    conversiones = db.query(DBConversionesCompra).all()
    return conversiones

@router.get("/{conversion_id}", response_model=ConversionesCompra)
def read_conversion_compra(
    conversion_id: int,
    db: Session = Depends(get_db),
    current_user: auth_utils.Usuario = Depends(auth_utils.require_menu_access("/conversiones-compra"))
):
    db_conversion = db.query(DBConversionesCompra).filter(DBConversionesCompra.conversion_id == conversion_id).first()
    if db_conversion is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversión de compra no encontrada.")
    return db_conversion

@router.put("/{conversion_id}", response_model=ConversionesCompra)
def update_conversion_compra(
    conversion_id: int,
    conversion: ConversionesCompraUpdate,
    db: Session = Depends(get_db),
    current_user: auth_utils.Usuario = Depends(auth_utils.require_menu_access("/conversiones-compra"))
):
    db_conversion = db.query(DBConversionesCompra).filter(DBConversionesCompra.conversion_id == conversion_id).first()
    if db_conversion is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversión de compra no encontrada.")

    update_data = conversion.model_dump(exclude_unset=True)

    if "nombre_presentacion" in update_data and update_data["nombre_presentacion"] != db_conversion.nombre_presentacion:
        existing_conversion = db.query(DBConversionesCompra).filter(
            DBConversionesCompra.producto_id == db_conversion.producto_id,
            DBConversionesCompra.nombre_presentacion == update_data["nombre_presentacion"],
            DBConversionesCompra.conversion_id != conversion_id
        ).first()
        if existing_conversion:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f'Ya existe otra presentación con el nombre "{update_data["nombre_presentacion"]}" para este producto.')

    for key, value in update_data.items():
        setattr(db_conversion, key, value)

    db.commit()
    db.refresh(db_conversion)
    return db_conversion

@router.delete("/{conversion_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_conversion_compra(
    conversion_id: int,
    db: Session = Depends(get_db),
    current_user: auth_utils.Usuario = Depends(auth_utils.require_menu_access("/conversiones-compra"))
):
    db_conversion = db.query(DBConversionesCompra).filter(DBConversionesCompra.conversion_id == conversion_id).first()
    if db_conversion is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversión de compra no encontrada.")
    
    db.delete(db_conversion)
    db.commit()
    return {}
