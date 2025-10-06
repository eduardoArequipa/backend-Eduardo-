"""
PRUEBAS DE CAJA BLANCA - Módulo Ventas
Objetivo: Testear la lógica interna de creación y gestión de ventas

Cobertura objetivo:
- Statement Coverage: 100% (todas las líneas ejecutadas)
- Branch Coverage: 100% (todos los if/else probados)
- Path Coverage: Todas las rutas de ejecución
"""
import pytest
from decimal import Decimal
from fastapi import HTTPException, Request
from sqlalchemy.exc import SQLAlchemyError
from unittest.mock import MagicMock, AsyncMock, patch
import asyncio

from app.routes.venta import create_venta, calcular_stock_en_unidad_minima
from app.models.venta import Venta as DBVenta
from app.models.detalle_venta import DetalleVenta as DBDetalleVenta
from app.models.producto import Producto as DBProducto
from app.models.persona import Persona as DBPersona
from app.models.conversion import Conversion as DBConversion
from app.schemas.venta import VentaCreate, DetalleVentaCreate
from app.models.enums import EstadoVentaEnum, EstadoEnum


class TestCreateVentaCajaBlanca:
    """
    CAJA BLANCA: create_venta function

    Rutas de ejecución identificadas:
    1. Cliente inválido → HTTPException(404)
    2. Sin detalles de venta → HTTPException(400)
    3. Stock insuficiente → HTTPException(400)
    4. Venta exitosa sin factura → Return venta
    5. Factura solicitada sin cliente → HTTPException(400)
    6. Error general de BD → HTTPException(500)
    """

    @pytest.fixture
    def mock_request(self):
        """Mock del objeto Request de FastAPI"""
        request = MagicMock(spec=Request)
        request.client = MagicMock()
        request.client.host = "127.0.0.1"
        return request

    @pytest.fixture
    def sample_venta_data(self):
        """Datos de ejemplo para crear ventas válidas"""
        return VentaCreate(
            persona_id=1,
            metodo_pago_id=1,
            estado=EstadoVentaEnum.activa,
            solicitar_factura=False,
            detalles=[
                DetalleVentaCreate(
                    producto_id=1,
                    cantidad=5,
                    precio_unitario=10.50,
                    presentacion_venta="Unidad"
                )
            ]
        )

    def test_rama_1_cliente_invalido(self, db_session, mock_user, mock_request, sample_venta_data):
        """
        RAMA 1: Cliente inválido o inactivo

        Flujo interno:
        - Línea 127-130: Query persona con filtros de estado
        - Línea 129: if not persona (TRUE)
        - Línea 130: HTTPException(404)
        """
        # ARRANGE: Venta con cliente que no existe
        sample_venta_data.persona_id = 999  # ID inexistente

        # ACT & ASSERT: Debe fallar por cliente no encontrado
        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(create_venta(sample_venta_data, mock_request, db_session, mock_user))

        assert exc_info.value.status_code == 404
        assert "no encontrado o inactivo" in str(exc_info.value.detail)

    def test_rama_2_sin_detalles_venta(self, db_session, mock_user, mock_request):
        """
        RAMA 2: Venta sin productos (detalles vacíos)

        Flujo interno:
        - Línea 132: if not venta_data.detalles (TRUE)
        - Línea 133: HTTPException(400)
        """
        # ARRANGE: Venta sin detalles
        venta_data = VentaCreate(
            persona_id=1,
            metodo_pago_id=1,
            estado=EstadoVentaEnum.activa,
            solicitar_factura=False,
            detalles=[]  # Lista vacía
        )

        # ACT & ASSERT: Debe fallar por falta de productos
        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(create_venta(venta_data, mock_request, db_session, mock_user))

        assert exc_info.value.status_code == 400
        assert "debe tener al menos un producto" in str(exc_info.value.detail)

    def test_rama_3_stock_insuficiente(self, db_session, mock_user, mock_request, create_test_persona, create_test_producto):
        """
        RAMA 3: Stock insuficiente para la venta

        Flujo interno:
        - Línea 149-157: Loop de validación de stock
        - Línea 153: if producto.stock < stock_a_descontar (TRUE)
        - Línea 154: HTTPException(400)
        """
        # ARRANGE: Crear persona y producto con poco stock
        persona = create_test_persona("Cliente Test")
        producto = create_test_producto("Producto Test", stock=2)  # Solo 2 unidades

        venta_data = VentaCreate(
            persona_id=persona.persona_id,
            metodo_pago_id=1,
            estado=EstadoVentaEnum.activa,
            solicitar_factura=False,
            detalles=[
                DetalleVentaCreate(
                    producto_id=producto.producto_id,
                    cantidad=5,  # Quiere 5 pero solo hay 2
                    precio_unitario=10.00,
                    presentacion_venta="Unidad"
                )
            ]
        )

        # ACT & ASSERT: Debe fallar por stock insuficiente
        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(create_venta(venta_data, mock_request, db_session, mock_user))

        assert exc_info.value.status_code == 400
        assert "Stock insuficiente" in str(exc_info.value.detail)

    def test_rama_4_venta_exitosa_sin_factura(self, db_session, mock_user, mock_request, create_test_persona, create_test_producto):
        """
        RAMA 4: Venta exitosa sin factura electrónica

        Flujo interno:
        - Línea 127-131: Persona encontrada (skip)
        - Línea 132-133: Detalles válidos (skip)
        - Línea 135-147: Crear venta y detalles
        - Línea 149-157: Validar y actualizar stock
        - Línea 159-160: Commit y refresh
        - Línea 173: if venta_data.solicitar_factura (FALSE)
        - Línea 185: return get_venta_or_404
        """
        # ARRANGE: Crear datos válidos
        persona = create_test_persona("Cliente Válido")
        producto = create_test_producto("Producto Válido", stock=10)

        venta_data = VentaCreate(
            persona_id=persona.persona_id,
            metodo_pago_id=1,
            estado=EstadoVentaEnum.activa,
            solicitar_factura=False,  # Sin factura
            detalles=[
                DetalleVentaCreate(
                    producto_id=producto.producto_id,
                    cantidad=3,
                    precio_unitario=15.99,
                    presentacion_venta="Unidad"
                )
            ]
        )

        # ACT: Crear venta
        result = asyncio.run(create_venta(venta_data, mock_request, db_session, mock_user))

        # ASSERT: Verificar creación exitosa
        assert result is not None
        assert result.total == Decimal('47.97')  # 3 * 15.99
        assert result.estado == EstadoVentaEnum.activa
        assert len(result.detalles) == 1

        # Verificar que se actualizó el stock
        producto_actualizado = db_session.query(DBProducto).filter(
            DBProducto.producto_id == producto.producto_id
        ).first()
        assert producto_actualizado.stock == 7  # 10 - 3

    def test_rama_5_factura_sin_cliente(self, db_session, mock_user, mock_request, create_test_producto):
        """
        RAMA 5: Solicita factura pero sin cliente válido

        Flujo interno:
        - Línea 173: if venta_data.solicitar_factura (TRUE)
        - Línea 174: if not venta_data.persona_id (TRUE)
        - Línea 176: HTTPException(400)
        """
        # ARRANGE: Venta sin cliente pero pidiendo factura
        producto = create_test_producto("Producto Test", stock=10)

        venta_data = VentaCreate(
            persona_id=None,  # Sin cliente
            metodo_pago_id=1,
            estado=EstadoVentaEnum.activa,
            solicitar_factura=True,  # Pero pidiendo factura
            detalles=[
                DetalleVentaCreate(
                    producto_id=producto.producto_id,
                    cantidad=2,
                    precio_unitario=20.00,
                    presentacion_venta="Unidad"
                )
            ]
        )

        # ACT & ASSERT: Debe fallar por factura sin cliente
        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(create_venta(venta_data, mock_request, db_session, mock_user))

        assert exc_info.value.status_code == 400
        assert "Se debe seleccionar un cliente para poder emitir una factura" in str(exc_info.value.detail)

    @patch('app.routes.venta.crear_factura_tesabiz')
    def test_rama_6_venta_con_factura_exitosa(self, mock_factura, db_session, mock_user, mock_request, create_test_persona, create_test_producto):
        """
        RAMA 6: Venta exitosa con factura electrónica

        Flujo interno:
        - Línea 173: if venta_data.solicitar_factura (TRUE)
        - Línea 174: if not venta_data.persona_id (FALSE)
        - Línea 177-183: try/except facturación
        - Línea 179: await crear_factura_tesabiz (SUCCESS)
        """
        # ARRANGE: Mock del servicio de facturación
        mock_factura.return_value = AsyncMock()

        persona = create_test_persona("Cliente con Factura")
        producto = create_test_producto("Producto Facturado", stock=10)

        venta_data = VentaCreate(
            persona_id=persona.persona_id,
            metodo_pago_id=1,
            estado=EstadoVentaEnum.activa,
            solicitar_factura=True,  # Con factura
            detalles=[
                DetalleVentaCreate(
                    producto_id=producto.producto_id,
                    cantidad=1,
                    precio_unitario=100.00,
                    presentacion_venta="Unidad"
                )
            ]
        )

        # ACT: Crear venta con factura
        result = asyncio.run(create_venta(venta_data, mock_request, db_session, mock_user))

        # ASSERT: Verificar creación exitosa y llamada a facturación
        assert result is not None
        assert result.total == Decimal('100.00')
        mock_factura.assert_called_once()


class TestCalcularStockCajaBlanca:
    """
    CAJA BLANCA: calcular_stock_en_unidad_minima function

    Rutas de ejecución identificadas:
    A. Venta en "Unidad" → Return cantidad directa
    B. Conversión no encontrada → HTTPException(400)
    C. Factor conversión <= 0 → HTTPException(400)
    D. Conversión exitosa → Return cantidad * factor
    """

    @pytest.fixture
    def producto_con_conversiones(self, create_test_producto, db_session):
        """Producto con conversiones de presentación"""
        from app.models.conversion import Conversion as DBConversion

        producto = create_test_producto("Producto con Presentaciones", stock=100)

        # Conversión válida para venta
        conversion_caja = DBConversion(
            producto_id=producto.producto_id,
            nombre_presentacion="Caja",
            unidades_por_presentacion=12,
            es_para_venta=True
        )
        db_session.add(conversion_caja)

        # Conversión NO válida para venta (solo compra)
        conversion_pallet = DBConversion(
            producto_id=producto.producto_id,
            nombre_presentacion="Pallet",
            unidades_por_presentacion=144,
            es_para_venta=False
        )
        db_session.add(conversion_pallet)

        # Conversión con factor inválido
        conversion_invalida = DBConversion(
            producto_id=producto.producto_id,
            nombre_presentacion="InvalidBox",
            unidades_por_presentacion=0,  # Factor inválido
            es_para_venta=True
        )
        db_session.add(conversion_invalida)

        db_session.commit()
        db_session.refresh(producto)
        return producto

    def test_rama_a_venta_en_unidad_minima(self, producto_con_conversiones):
        """
        RAMA A: Venta en unidad mínima (sin conversión)

        Flujo interno:
        - Línea 66: if not presentacion_venta or presentacion_venta == 'Unidad' (TRUE)
        - Línea 67: return cantidad_vendida
        """
        # ARRANGE
        cantidad_vendida = Decimal('5')
        presentacion = "Unidad"

        # ACT
        result = calcular_stock_en_unidad_minima(producto_con_conversiones, cantidad_vendida, presentacion)

        # ASSERT: Debe retornar la cantidad sin conversión
        assert result == Decimal('5')

    def test_rama_a_venta_sin_presentacion(self, producto_con_conversiones):
        """
        RAMA A: Venta sin especificar presentación (None)

        Flujo interno:
        - Línea 66: if not presentacion_venta (TRUE)
        - Línea 67: return cantidad_vendida
        """
        # ARRANGE
        cantidad_vendida = Decimal('3')
        presentacion = None

        # ACT
        result = calcular_stock_en_unidad_minima(producto_con_conversiones, cantidad_vendida, presentacion)

        # ASSERT: Debe retornar la cantidad sin conversión
        assert result == Decimal('3')

    def test_rama_b_conversion_no_encontrada(self, producto_con_conversiones):
        """
        RAMA B: Presentación no existe o no habilitada para venta

        Flujo interno:
        - Línea 66: if not presentacion_venta (FALSE)
        - Línea 73-77: Loop de conversiones, no encuentra match
        - Línea 79: if not conversion (TRUE)
        - Línea 81-84: HTTPException(400)
        """
        # ARRANGE: Presentación que no existe
        cantidad_vendida = Decimal('2')
        presentacion = "PresentacionInexistente"

        # ACT & ASSERT
        with pytest.raises(HTTPException) as exc_info:
            calcular_stock_en_unidad_minima(producto_con_conversiones, cantidad_vendida, presentacion)

        assert exc_info.value.status_code == 400
        assert "no es válida o no está habilitada para ventas" in str(exc_info.value.detail)

    def test_rama_b_conversion_no_habilitada_venta(self, producto_con_conversiones):
        """
        RAMA B: Presentación existe pero NO habilitada para venta

        Flujo interno:
        - Línea 73-77: Loop encuentra "Pallet" pero es_para_venta=False
        - Línea 79: if not conversion (TRUE)
        - Línea 81-84: HTTPException(400)
        """
        # ARRANGE: Presentación que existe pero no está habilitada para venta
        cantidad_vendida = Decimal('1')
        presentacion = "Pallet"  # es_para_venta=False

        # ACT & ASSERT
        with pytest.raises(HTTPException) as exc_info:
            calcular_stock_en_unidad_minima(producto_con_conversiones, cantidad_vendida, presentacion)

        assert exc_info.value.status_code == 400
        assert "no es válida o no está habilitada para ventas" in str(exc_info.value.detail)

    def test_rama_c_factor_conversion_invalido(self, producto_con_conversiones):
        """
        RAMA C: Factor de conversión es 0 o negativo

        Flujo interno:
        - Línea 73-77: Loop encuentra conversión válida
        - Línea 79: if not conversion (FALSE)
        - Línea 87: if conversion.unidades_por_presentacion <= 0 (TRUE)
        - Línea 88-91: HTTPException(400)
        """
        # ARRANGE: Presentación con factor de conversión inválido
        cantidad_vendida = Decimal('2')
        presentacion = "InvalidBox"  # unidades_por_presentacion=0

        # ACT & ASSERT
        with pytest.raises(HTTPException) as exc_info:
            calcular_stock_en_unidad_minima(producto_con_conversiones, cantidad_vendida, presentacion)

        assert exc_info.value.status_code == 400
        assert "es cero o negativo" in str(exc_info.value.detail)

    def test_rama_d_conversion_exitosa(self, producto_con_conversiones):
        """
        RAMA D: Conversión exitosa con factor válido

        Flujo interno:
        - Línea 73-77: Loop encuentra "Caja" válida para venta
        - Línea 79: if not conversion (FALSE)
        - Línea 87: if unidades_por_presentacion <= 0 (FALSE)
        - Línea 94: stock_a_descontar = cantidad * factor
        - Línea 96: return stock_a_descontar
        """
        # ARRANGE: Presentación válida con factor 12
        cantidad_vendida = Decimal('3')
        presentacion = "Caja"  # 12 unidades por caja

        # ACT
        result = calcular_stock_en_unidad_minima(producto_con_conversiones, cantidad_vendida, presentacion)

        # ASSERT: 3 cajas * 12 unidades/caja = 36 unidades
        assert result == Decimal('36')

    def test_rama_d_conversion_case_insensitive(self, producto_con_conversiones):
        """
        RAMA D: Conversión funciona independiente de mayúsculas/minúsculas

        Flujo interno:
        - Línea 75: c.nombre_presentacion.lower() == presentacion_nombre.lower()
        """
        # ARRANGE: Presentación en diferentes casos
        cantidad_vendida = Decimal('2')

        # ACT & ASSERT: Diferentes casos deben funcionar igual
        result1 = calcular_stock_en_unidad_minima(producto_con_conversiones, cantidad_vendida, "caja")
        result2 = calcular_stock_en_unidad_minima(producto_con_conversiones, cantidad_vendida, "CAJA")
        result3 = calcular_stock_en_unidad_minima(producto_con_conversiones, cantidad_vendida, "Caja")

        expected = Decimal('24')  # 2 * 12
        assert result1 == expected
        assert result2 == expected
        assert result3 == expected


# HELPER FUNCTIONS PARA FIXTURES ADICIONALES
@pytest.fixture
def create_test_persona(db_session):
    """Factory para crear personas de prueba"""
    import time
    def _create_persona(nombre="Test Person"):
        unique_ci = f"{int(time.time())}{hash(nombre) % 1000}"[:10]
        persona = DBPersona(
            nombre=nombre,
            apellido_paterno="TestApellido",
            ci=unique_ci,  # CI único para evitar duplicados
            estado=EstadoEnum.activo
        )
        db_session.add(persona)
        db_session.commit()
        db_session.refresh(persona)
        return persona
    return _create_persona


@pytest.fixture
def create_test_producto(db_session):
    """Factory para crear productos de prueba"""
    import time
    def _create_producto(nombre="Test Product", stock=10):
        unique_code = f"TEST{int(time.time())}{hash(nombre) % 1000}"

        # Crear o usar categoria y marca existentes
        from app.models.categoria import Categoria as DBCategoria
        from app.models.marca import Marca as DBMarca
        from app.models.unidad_medida import UnidadMedida as DBUnidadMedida

        # Intentar obtener registros existentes o crear nuevos
        categoria = db_session.query(DBCategoria).first()
        if not categoria:
            categoria = DBCategoria(nombre="Categoria Test", estado=EstadoEnum.activo)
            db_session.add(categoria)
            db_session.flush()

        marca = db_session.query(DBMarca).first()
        if not marca:
            marca = DBMarca(nombre="Marca Test", estado=EstadoEnum.activo)
            db_session.add(marca)
            db_session.flush()

        unidad = db_session.query(DBUnidadMedida).first()
        if not unidad:
            unidad = DBUnidadMedida(nombre="Unidad Test", simbolo="Un")
            db_session.add(unidad)
            db_session.flush()

        producto = DBProducto(
            nombre=nombre,
            codigo=unique_code,
            stock=stock,
            stock_minimo=1,
            precio_compra=Decimal('5.00'),
            precio_venta=Decimal('10.00'),
            unidad_inventario_id=unidad.unidad_id,
            marca_id=marca.marca_id,
            categoria_id=categoria.categoria_id,  # Campo requerido
            estado=EstadoEnum.activo,
            conversiones=[]  # Inicializar lista vacía
        )
        db_session.add(producto)
        db_session.commit()
        db_session.refresh(producto)
        return producto
    return _create_producto