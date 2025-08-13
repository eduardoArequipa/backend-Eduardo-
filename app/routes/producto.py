from typing import List, Optional
import os
import shutil
from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import or_
from .. import auth as auth_utils
from ..database import get_db
from ..models.producto import Producto as DBProducto
from ..models.enums import EstadoEnum
from ..models.categoria import Categoria as DBCategoria
from ..models.usuario import Usuario as DBUsuario
from ..models.unidad_medida import UnidadMedida as DBUnidadMedida
from ..models.marca import Marca as DBMarca
from ..schemas.producto import (
    ProductoBase,
    ProductoCreate,
    ProductoUpdate,
    Producto,
    ProductoNested,
    ProductoPagination # Importar el nuevo esquema de paginación
)

UPLOAD_DIR_PRODUCTS = "static/uploads/products"
os.makedirs(UPLOAD_DIR_PRODUCTS, exist_ok=True)

def delete_image_file(image_path: Optional[str]):
    """Elimina un archivo de imagen del servidor si la ruta pública es válida y apunta al directorio de productos."""
    if image_path and image_path.startswith('/static/uploads/products/'):
        try:
            file_to_delete_relative = image_path.replace("/static/", "static/", 1)
            if file_to_delete_relative.startswith(UPLOAD_DIR_PRODUCTS):
                if os.path.exists(file_to_delete_relative):
                    os.remove(file_to_delete_relative)
        except Exception as e:
            # Opcional: puedes registrar el error si lo deseas
            pass
                    

router = APIRouter(
    prefix="/productos",
    tags=["productos"]
)

ROLES_CAN_MANAGE_PRODUCTS = ["Administrador", "Empleado"]

@router.post("/", response_model=Producto, status_code=status.HTTP_201_CREATED)
def create_producto(
    producto: ProductoCreate,
    db: Session = Depends(get_db),
    current_user: auth_utils.Usuario = Depends(auth_utils.require_menu_access("/productos")) # Verificar acceso al menú de categorías
):
    db_categoria = db.query(DBCategoria).filter(DBCategoria.categoria_id == producto.categoria_id).first()
    if db_categoria is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Categoría no encontrada.")

    db_unidad_medida = db.query(DBUnidadMedida).filter(DBUnidadMedida.unidad_id == producto.unidad_medida_id).first()
    if db_unidad_medida is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unidad de medida no encontrada.")

    db_marca = db.query(DBMarca).filter(DBMarca.marca_id == producto.marca_id).first()
    if db_marca is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Marca no encontrada.")

    db_producto_codigo = db.query(DBProducto).filter(DBProducto.codigo == producto.codigo).first()
    if db_producto_codigo:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Ya existe un producto con este código.")

    if producto.metros_por_rollo is not None and db_unidad_medida.nombre_unidad != "Metro":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="El campo metros_por_rollo solo es válido para unidades de medida 'metro'.")

    # Convertir stock a metros si la unidad es "metro" y hay metros_por_rollo
    if db_unidad_medida.nombre_unidad == "Metro" and producto.metros_por_rollo is not None:
        producto.stock = producto.stock * producto.metros_por_rollo

    # Crear el nuevo producto con los datos del esquema
    new_producto = DBProducto(**producto.model_dump())
    new_producto.creado_por = current_user.usuario_id

    db.add(new_producto)
    db.commit()
    db.refresh(new_producto, attribute_names=['categoria', 'creador', 'modificador', 'unidad_medida', 'marca'])

    return new_producto

@router.get("/", response_model=ProductoPagination) # Cambiado a ProductoPagination
def read_productos(
    estado: Optional[EstadoEnum] = Query(None, description="Filtrar por estado"),
    search: Optional[str] = Query(None, description="Texto de búsqueda por código o nombre"),
    categoria_id: Optional[int] = Query(None, description="Filtrar por Categoría (ID)", alias="categoria"),
    unidad_medida_id: Optional[int] = Query(None, description="Filtrar por Unidad de Medida (ID)", alias="unidad_medida"),
    marca_id: Optional[int] = Query(None, description="Filtrar por Marca (ID)", alias="marca"),
    min_stock: Optional[Decimal] = Query(None, description="Filtrar por productos con stock mínimo"),
    skip: int = Query(0, ge=0, description="Número de elementos a omitir (paginación)"),
    limit: int = Query(100, gt=0, description="Número máximo de elementos a retornar (paginación)"),
    db: Session = Depends(get_db),
    current_user: auth_utils.Usuario = Depends(auth_utils.require_menu_access("/productos")) # Verificar acceso al menú de categorías
):
    query = db.query(DBProducto).options(
        joinedload(DBProducto.categoria),
        joinedload(DBProducto.creador),
        joinedload(DBProducto.modificador),
        joinedload(DBProducto.unidad_medida),
        joinedload(DBProducto.marca)
    )

    if estado:
        query = query.filter(DBProducto.estado == estado)

    if search:
        query = query.filter(
            or_(
                DBProducto.codigo.ilike(f"%{search}%"),
                DBProducto.nombre.ilike(f"%{search}%"),
            )
        )
    
    if categoria_id is not None:
        query = query.filter(DBProducto.categoria_id == categoria_id)

    if unidad_medida_id is not None:
        query = query.filter(DBProducto.unidad_medida_id == unidad_medida_id)

    if marca_id is not None:
        query = query.filter(DBProducto.marca_id == marca_id)

    if min_stock is not None:
        query = query.filter(DBProducto.stock >= min_stock)

    total = query.count() # Contar el total de productos antes de aplicar skip/limit
    productos = query.offset(skip).limit(limit).all()

    return {"items": productos, "total": total} # Devolver el objeto de paginación


@router.get("/low-stock", response_model=List[Producto])
def get_low_stock_products(
    db: Session = Depends(get_db),
    current_user: auth_utils.Usuario = Depends(auth_utils.get_current_active_user) # Cualquier usuario logeado puede ver esto
):
    """
    Obtiene una lista de productos cuyo stock actual es igual o menor que su stock mínimo.
    Accesible por cualquier usuario autenticado.
    """
    low_stock_products = db.query(DBProducto).options(
        joinedload(DBProducto.categoria),
        joinedload(DBProducto.unidad_medida),
        joinedload(DBProducto.marca),
        joinedload(DBProducto.creador),
        joinedload(DBProducto.modificador)
    ).filter(
        DBProducto.stock <= DBProducto.stock_minimo,
        DBProducto.estado == EstadoEnum.activo 
    ).all()

    return low_stock_products
@router.get("/{producto_id}", response_model=Producto)
def read_producto(
    producto_id: int,
    db: Session = Depends(get_db),
    current_user: auth_utils.Usuario = Depends(auth_utils.require_menu_access("/productos")) # Verificar acceso al menú de categorías
):
    producto = db.query(DBProducto).options(
        joinedload(DBProducto.categoria),
        joinedload(DBProducto.creador),
        joinedload(DBProducto.modificador),
        joinedload(DBProducto.unidad_medida),
        joinedload(DBProducto.marca)
    ).filter(DBProducto.producto_id == producto_id).first()

    if producto is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Producto no encontrado")

    return producto

@router.put("/{producto_id}", response_model=Producto)
def update_producto(
    producto_id: int,
    producto_update: ProductoUpdate,
    db: Session = Depends(get_db),
    current_user: auth_utils.Usuario = Depends(auth_utils.require_menu_access("/productos")) # Verificar acceso al menú de categorías
):
    db_producto = db.query(DBProducto).options(
        joinedload(DBProducto.categoria),
        joinedload(DBProducto.creador),
        joinedload(DBProducto.modificador),
        joinedload(DBProducto.unidad_medida),
        joinedload(DBProducto.marca)
    ).filter(DBProducto.producto_id == producto_id).first()

    if db_producto is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Producto no encontrado.")

    update_data = producto_update.model_dump(exclude_unset=True)

    if 'imagen_ruta' in update_data:
        new_image_ruta = update_data['imagen_ruta']
        if new_image_ruta is None and db_producto.imagen_ruta:
            delete_image_file(db_producto.imagen_ruta)
            db_producto.imagen_ruta = None
        elif new_image_ruta is not None and new_image_ruta != db_producto.imagen_ruta:
            db_producto.imagen_ruta = new_image_ruta
        del update_data['imagen_ruta']

    if 'codigo' in update_data and update_data['codigo'] != db_producto.codigo:
        existing_producto_with_new_code = db.query(DBProducto).filter(DBProducto.codigo == update_data['codigo']).first()
        if existing_producto_with_new_code and existing_producto_with_new_code.producto_id != producto_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Ya existe otro producto con este código.")

    if 'categoria_id' in update_data and update_data['categoria_id'] is not None and update_data['categoria_id'] != db_producto.categoria_id:
        db_categoria = db.query(DBCategoria).filter(DBCategoria.categoria_id == update_data['categoria_id']).first()
        if db_categoria is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="La nueva Categoría especificada no fue encontrada.")

    if 'unidad_medida_id' in update_data and update_data['unidad_medida_id'] is not None and update_data['unidad_medida_id'] != db_producto.unidad_medida_id:
        db_unidad_medida = db.query(DBUnidadMedida).filter(DBUnidadMedida.unidad_id == update_data['unidad_medida_id']).first()
        if db_unidad_medida is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="La nueva Unidad de Medida especificada no fue encontrada.")

    if 'marca_id' in update_data and update_data['marca_id'] is not None and update_data['marca_id'] != db_producto.marca_id:
        db_marca = db.query(DBMarca).filter(DBMarca.marca_id == update_data['marca_id']).first()
        if db_marca is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="La nueva Marca especificada no fue encontrada.")

    if 'metros_por_rollo' in update_data and update_data['metros_por_rollo'] is not None:
        db_unidad_medida = db.query(DBUnidadMedida).filter(DBUnidadMedida.unidad_id == db_producto.unidad_medida_id).first()
        if db_unidad_medida.nombre_unidad != "Metro":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="El campo metros_por_rollo solo es válido para unidades de medida 'metro'.")
    for field, value in update_data.items():
        setattr(db_producto, field, value)

    db_producto.modificado_por = current_user.usuario_id

    db.commit()
    db.refresh(db_producto, attribute_names=['categoria', 'creador', 'modificador', 'unidad_medida', 'marca'])

    return db_producto

@router.patch("/{producto_id}/inactivar", status_code=status.HTTP_204_NO_CONTENT)
def delete_producto(
    producto_id: int,
    db: Session = Depends(get_db),
    current_user: auth_utils.Usuario = Depends(auth_utils.require_menu_access("/productos")) # Verificar acceso al menú de categorías
):
    db_producto = db.query(DBProducto).filter(DBProducto.producto_id == producto_id).first()
    if db_producto is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Producto no encontrado.")

    if db_producto.estado == EstadoEnum.inactivo:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="El producto ya está inactivo.")

    db_producto.estado = EstadoEnum.inactivo
    db_producto.modificado_por = current_user.usuario_id

    if db_producto.imagen_ruta:
        delete_image_file(db_producto.imagen_ruta)
        db_producto.imagen_ruta = None

    db.commit()

    return {}

@router.patch("/{producto_id}/activar", response_model=Producto)
def activate_producto(
    producto_id: int,
    db: Session = Depends(get_db),
    current_user: auth_utils.Usuario = Depends(auth_utils.require_menu_access("/productos")) # Verificar acceso al menú de categorías
):
    db_producto = db.query(DBProducto).options(
        joinedload(DBProducto.categoria),
        joinedload(DBProducto.creador),
        joinedload(DBProducto.modificador),
        joinedload(DBProducto.unidad_medida),
        joinedload(DBProducto.marca)
    ).filter(DBProducto.producto_id == producto_id).first()

    if db_producto is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Producto no encontrado.")

    if db_producto.estado == EstadoEnum.activo:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="El producto ya está activo.")

    db_producto.estado = EstadoEnum.activo
    db_producto.modificado_por = current_user.usuario_id

    db.commit()
    db.refresh(db_producto)

    return db_producto

@router.get("/by-code/{codigo}", response_model=Producto)
def read_producto_by_code(
    codigo: str,
    db: Session = Depends(get_db),
  #  current_user: auth_utils.Usuario = Depends(auth_utils.get_current_active_user_with_role(ROLES_CAN_MANAGE_PRODUCTS))
):
    """
    Obtiene un Producto específico buscando por su código de barras.
    """
    producto = db.query(DBProducto).options(
        joinedload(DBProducto.categoria),
        joinedload(DBProducto.creador),
        joinedload(DBProducto.modificador),
        joinedload(DBProducto.unidad_medida),
        joinedload(DBProducto.marca)
    ).filter(DBProducto.codigo == codigo).first()

    if producto is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Producto con código '{codigo}' no encontrado.")

    return producto