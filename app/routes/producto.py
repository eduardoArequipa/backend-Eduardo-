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
from ..models.conversion import Conversion as DBConversion
# 1. Importar modelos de detalles para la comprobación
from ..models.detalle_venta import DetalleVenta
from ..models.detalle_compra import DetalleCompra
from ..schemas.producto import (
    Producto,
    ProductoCreate,
    ProductoUpdate,
    ProductoPagination,
    ProductoNested,
    Conversion,
    ConversionCreate
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
            pass
                    

router = APIRouter(
    prefix="/productos",
    tags=["productos"]
)

@router.post("/", response_model=Producto, status_code=status.HTTP_201_CREATED)
def create_producto(
    producto: ProductoCreate,
    db: Session = Depends(get_db),
    current_user: auth_utils.Usuario = Depends(auth_utils.require_menu_access("/productos"))
):
    db_categoria = db.query(DBCategoria).filter(DBCategoria.categoria_id == producto.categoria_id).first()
    if not db_categoria:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Categoría no encontrada.")

    db_unidad_inventario = db.query(DBUnidadMedida).filter(DBUnidadMedida.unidad_id == producto.unidad_inventario_id).first()
    if not db_unidad_inventario:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unidad de inventario no encontrada.")

    db_marca = db.query(DBMarca).filter(DBMarca.marca_id == producto.marca_id).first()
    if not db_marca:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Marca no encontrada.")

    db_producto_codigo = db.query(DBProducto).filter(DBProducto.codigo == producto.codigo).first()
    if db_producto_codigo:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Ya existe un producto con este código.")

    new_producto = DBProducto(**producto.model_dump())
    new_producto.creado_por = current_user.usuario_id

    db.add(new_producto)
    db.commit()
    db.refresh(new_producto, attribute_names=['categoria', 'creador', 'modificador', 'unidad_inventario', 'marca', 'conversiones'])

    return new_producto

@router.get("/", response_model=ProductoPagination)
def read_productos(
    estado: Optional[EstadoEnum] = Query(None, description="Filtrar por estado"),
    search: Optional[str] = Query(None, description="Texto de búsqueda por código o nombre"),
    categoria_id: Optional[int] = Query(None, description="Filtrar por Categoría (ID)", alias="categoria"),
    unidad_inventario_id: Optional[int] = Query(None, description="Filtrar por Unidad de Inventario (ID)", alias="unidad_inventario"),
    marca_id: Optional[int] = Query(None, description="Filtrar por Marca (ID)", alias="marca"),
    min_stock: Optional[Decimal] = Query(None, description="Filtrar por productos con stock mínimo"),
    skip: int = Query(0, ge=0, description="Número de elementos a omitir (paginación)"),
    limit: int = Query(100, gt=0, description="Número máximo de elementos a retornar (paginación)"),
    db: Session = Depends(get_db),
    current_user: auth_utils.Usuario = Depends(auth_utils.require_menu_access("/productos"))
):
    query = db.query(DBProducto).options(
        joinedload(DBProducto.categoria),
        joinedload(DBProducto.creador),
        joinedload(DBProducto.modificador),
        joinedload(DBProducto.unidad_inventario),
        joinedload(DBProducto.marca),
        joinedload(DBProducto.conversiones)
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

    if unidad_inventario_id is not None:
        query = query.filter(DBProducto.unidad_inventario_id == unidad_inventario_id)

    if marca_id is not None:
        query = query.filter(DBProducto.marca_id == marca_id)

    if min_stock is not None:
        query = query.filter(DBProducto.stock >= min_stock)

    total = query.count()
    productos = query.offset(skip).limit(limit).all()

    return {"items": productos, "total": total}


@router.get("/low-stock", response_model=List[Producto])
def get_low_stock_products(
    db: Session = Depends(get_db),
    current_user: auth_utils.Usuario = Depends(auth_utils.get_current_active_user)
):
    low_stock_products = db.query(DBProducto).options(
        joinedload(DBProducto.categoria),
        joinedload(DBProducto.unidad_inventario),
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
    current_user: auth_utils.Usuario = Depends(auth_utils.require_menu_access("/productos"))
):
    producto = db.query(DBProducto).options(
        joinedload(DBProducto.categoria),
        joinedload(DBProducto.creador),
        joinedload(DBProducto.modificador),
        joinedload(DBProducto.unidad_inventario),
        joinedload(DBProducto.marca),
        joinedload(DBProducto.conversiones)
    ).filter(DBProducto.producto_id == producto_id).first()

    if producto is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Producto no encontrado")

    return producto

@router.put("/{producto_id}", response_model=Producto)
def update_producto(
    producto_id: int,
    producto_update: ProductoUpdate,
    db: Session = Depends(get_db),
    current_user: auth_utils.Usuario = Depends(auth_utils.require_menu_access("/productos"))
):
    db_producto = db.query(DBProducto).options(
        joinedload(DBProducto.categoria),
        joinedload(DBProducto.creador),
        joinedload(DBProducto.modificador),
        joinedload(DBProducto.unidad_inventario),
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

    if 'unidad_inventario_id' in update_data and update_data['unidad_inventario_id'] is not None and update_data['unidad_inventario_id'] != db_producto.unidad_inventario_id:
        db_unidad_medida = db.query(DBUnidadMedida).filter(DBUnidadMedida.unidad_id == update_data['unidad_inventario_id']).first()
        if db_unidad_medida is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="La nueva Unidad de Medida especificada no fue encontrada.")

    if 'marca_id' in update_data and update_data['marca_id'] is not None and update_data['marca_id'] != db_producto.marca_id:
        db_marca = db.query(DBMarca).filter(DBMarca.marca_id == update_data['marca_id']).first()
        if db_marca is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="La nueva Marca especificada no fue encontrada.")

    for field, value in update_data.items():
        setattr(db_producto, field, value)

    db_producto.modificado_por = current_user.usuario_id

    db.commit()
    db.refresh(db_producto, attribute_names=['categoria', 'creador', 'modificador', 'unidad_inventario', 'marca', 'conversiones'])

    return db_producto

@router.patch("/{producto_id}/inactivar", status_code=status.HTTP_204_NO_CONTENT)
def delete_producto(
    producto_id: int,
    db: Session = Depends(get_db),
    current_user: auth_utils.Usuario = Depends(auth_utils.require_menu_access("/productos"))
):
    db_producto = db.query(DBProducto).filter(DBProducto.producto_id == producto_id).first()
    if db_producto is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Producto no encontrado.")

    if db_producto.estado == EstadoEnum.inactivo:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="El producto ya está inactivo.")

    # 2. Comprobación más granular de transacciones existentes
    # Verificar ventas activas (no anuladas)
    from ..models.venta import Venta as DBVenta
    from ..models.compra import Compra as DBCompra
    from ..models.enums import EstadoVentaEnum, EstadoCompraEnum
    
    active_sales = db.query(DetalleVenta).join(DBVenta).filter(
        DetalleVenta.producto_id == producto_id,
        DBVenta.estado == EstadoVentaEnum.activa
    ).count()
    
    active_purchases = db.query(DetalleCompra).join(DBCompra).filter(
        DetalleCompra.producto_id == producto_id,
        DBCompra.estado.in_([EstadoCompraEnum.pendiente, EstadoCompraEnum.completada])
    ).count()

    if active_sales > 0 or active_purchases > 0:
        transaction_details = []
        if active_sales > 0:
            transaction_details.append(f"{active_sales} venta(s) activa(s)")
        if active_purchases > 0:
            transaction_details.append(f"{active_purchases} compra(s) pendiente(s) o completada(s)")
        
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Este producto no se puede desactivar porque está asociado a {' y '.join(transaction_details)}."
        )

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
    current_user: auth_utils.Usuario = Depends(auth_utils.require_menu_access("/productos"))
):
    db_producto = db.query(DBProducto).options(
        joinedload(DBProducto.categoria),
        joinedload(DBProducto.creador),
        joinedload(DBProducto.modificador),
        joinedload(DBProducto.unidad_inventario),
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
):
    producto = db.query(DBProducto).options(
        joinedload(DBProducto.categoria),
        joinedload(DBProducto.creador),
        joinedload(DBProducto.modificador),
        joinedload(DBProducto.unidad_inventario),
        joinedload(DBProducto.marca),
        joinedload(DBProducto.conversiones)
    ).filter(DBProducto.codigo == codigo).first()

    if producto is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Producto con código '{codigo}' no encontrado.")

    return producto

@router.get("/search/suggestions", response_model=List[ProductoNested])
def search_product_suggestions(
    q: str = Query(..., min_length=1, description="Término de búsqueda para código o nombre de producto"),
    db: Session = Depends(get_db),
    current_user: auth_utils.Usuario = Depends(auth_utils.get_current_active_user)
):
    productos = db.query(DBProducto).filter(
        or_(
            DBProducto.codigo.ilike(f"%{q}%"),
            DBProducto.nombre.ilike(f"%{q}%")
        ),
        DBProducto.estado == EstadoEnum.activo
    ).limit(10).all()

    return productos


@router.get("/conversiones/", response_model=List[Conversion])
def read_all_conversiones(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: auth_utils.Usuario = Depends(auth_utils.get_current_active_user)
):
    """
    Obtiene una lista de todas las conversiones de todos los productos.
    """
    conversiones = db.query(DBConversion).offset(skip).limit(limit).all()
    return conversiones


@router.post("/conversiones/", response_model=Conversion, status_code=status.HTTP_201_CREATED)
def create_conversion(
    conversion_data: ConversionCreate,
    producto_id: int,
    db: Session = Depends(get_db),
    current_user: auth_utils.Usuario = Depends(auth_utils.require_menu_access("/productos"))
):
    db_producto = db.query(DBProducto).filter(DBProducto.producto_id == producto_id).first()
    if not db_producto:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Producto no encontrado.")

    # Check for existing conversion with the same name for the same product
    existing_conversion = db.query(DBConversion).filter(
        DBConversion.producto_id == producto_id,
        DBConversion.nombre_presentacion == conversion_data.nombre_presentacion
    ).first()
    if existing_conversion:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Ya existe una presentación con el nombre '{conversion_data.nombre_presentacion}' para este producto.")

    new_conversion = DBConversion(
        **conversion_data.model_dump(),
        producto_id=producto_id
    )
    db.add(new_conversion)
    db.commit()
    db.refresh(new_conversion)
    return new_conversion

@router.put("/conversiones/{conversion_id}", response_model=Conversion)
def update_conversion(
    conversion_id: int,
    conversion_data: ConversionCreate,
    db: Session = Depends(get_db),
    current_user: auth_utils.Usuario = Depends(auth_utils.require_menu_access("/productos"))
):
    db_conversion = db.query(DBConversion).filter(DBConversion.id == conversion_id).first()
    if not db_conversion:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversión no encontrada.")

    if conversion_data.nombre_presentacion != db_conversion.nombre_presentacion:
        existing_conversion = db.query(DBConversion).filter(
            DBConversion.producto_id == db_conversion.producto_id,
            DBConversion.nombre_presentacion == conversion_data.nombre_presentacion,
            DBConversion.id != conversion_id
        ).first()
        if existing_conversion:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Ya existe otra presentación con el nombre '{conversion_data.nombre_presentacion}' para este producto.")

    # Update all fields from conversion_data
    update_data = conversion_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_conversion, field, value)

    db.commit()
    db.refresh(db_conversion)
    return db_conversion

@router.delete("/conversiones/{conversion_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_conversion(
    conversion_id: int,
    db: Session = Depends(get_db),
    current_user: auth_utils.Usuario = Depends(auth_utils.require_menu_access("/productos"))
):
    db_conversion = db.query(DBConversion).filter(DBConversion.id == conversion_id).first()
    if not db_conversion:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversión no encontrada.")
    
    db.delete(db_conversion)
    db.commit()
    return {}
