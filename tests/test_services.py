"""
test_services.py - Pruebas de reglas del negocio, entradas, salidas y control de celdas.
"""

import pytest
import os
import tempfile
from database import get_db_connection, init_db
import services


@pytest.fixture
def conn():
    """Crea una base de datos limpia para cada prueba de servicio."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    init_db(path)
    connection = get_db_connection(path)
    yield connection
    connection.close()
    if os.path.exists(path):
        os.remove(path)


def test_registrar_entrada_exitoso(conn):
    """Verifica que un vehículo se registre correctamente y la celda pase a OCUPADA."""
    cursor = conn.cursor()

    # Buscar un vehículo que no esté dentro y una celda disponible
    cursor.execute("""
        SELECT id, placa FROM vehiculos 
        WHERE id NOT IN (SELECT vehiculo_id FROM movimientos WHERE estado = 'ACTIVO')
        LIMIT 1;
    """)
    vehiculo = cursor.fetchone()

    cursor.execute("SELECT id, codigo FROM celdas WHERE estado = 'DISPONIBLE' LIMIT 1;")
    celda = cursor.fetchone()

    mov_id = services.registrar_entrada(
        conn=conn,
        vehiculo_id=vehiculo["id"],
        celda_id=celda["id"],
        usuario_id=1,
        observaciones="Ingreso de prueba unitaria"
    )

    assert mov_id is not None

    # Verificar que el movimiento esté ACTIVO
    cursor.execute("SELECT * FROM movimientos WHERE id = ?;", (mov_id,))
    mov = cursor.fetchone()
    assert mov["estado"] == "ACTIVO"
    assert mov["vehiculo_id"] == vehiculo["id"]

    # Verificar que la celda ahora esté OCUPADA
    cursor.execute("SELECT estado FROM celdas WHERE id = ?;", (celda["id"],))
    celda_upd = cursor.fetchone()
    assert celda_upd["estado"] == "OCUPADA"


def test_impedir_doble_estancia_activa_mismo_vehiculo(conn):
    """Verifica que no se permita registrar un vehículo que ya tiene una estancia activa."""
    cursor = conn.cursor()

    # Tomar un vehículo que ya tiene estancia activa (del demo seed)
    cursor.execute("SELECT vehiculo_id FROM movimientos WHERE estado = 'ACTIVO' LIMIT 1;")
    vehiculo_id = cursor.fetchone()["vehiculo_id"]

    # Buscar una celda disponible
    cursor.execute("SELECT id FROM celdas WHERE estado = 'DISPONIBLE' LIMIT 1;")
    celda_id = cursor.fetchone()["id"]

    with pytest.raises(ValueError) as excinfo:
        services.registrar_entrada(
            conn=conn,
            vehiculo_id=vehiculo_id,
            celda_id=celda_id,
            usuario_id=1
        )

    assert "ya se encuentra dentro del parqueadero" in str(excinfo.value)


def test_impedir_ingreso_en_celda_ocupada(conn):
    """Verifica que no se permita asignar una celda que ya esté ocupada."""
    cursor = conn.cursor()

    # Tomar un vehículo disponible
    cursor.execute("""
        SELECT id FROM vehiculos 
        WHERE id NOT IN (SELECT vehiculo_id FROM movimientos WHERE estado = 'ACTIVO')
        LIMIT 1;
    """)
    vehiculo_id = cursor.fetchone()["id"]

    # Tomar una celda ocupada
    cursor.execute("SELECT id FROM celdas WHERE estado = 'OCUPADA' LIMIT 1;")
    celda_ocupada_id = cursor.fetchone()["id"]

    with pytest.raises(ValueError) as excinfo:
        services.registrar_entrada(
            conn=conn,
            vehiculo_id=vehiculo_id,
            celda_id=celda_ocupada_id,
            usuario_id=1
        )

    assert "no está disponible" in str(excinfo.value)


def test_registrar_salida_exitoso(conn):
    """Verifica que la salida libere la celda y marque el movimiento como FINALIZADO."""
    cursor = conn.cursor()

    # Tomar un movimiento activo
    cursor.execute("SELECT id, celda_id, vehiculo_id FROM movimientos WHERE estado = 'ACTIVO' LIMIT 1;")
    mov_activo = cursor.fetchone()
    mov_id = mov_activo["id"]
    celda_id = mov_activo["celda_id"]

    # Registrar salida
    res = services.registrar_salida(conn=conn, movimiento_id=mov_id, observaciones_salida="Salida ok")

    assert res is not None

    # Verificar estado del movimiento
    cursor.execute("SELECT estado, fecha_salida, observaciones_salida FROM movimientos WHERE id = ?;", (mov_id,))
    mov = cursor.fetchone()
    assert mov["estado"] == "FINALIZADO"
    assert mov["fecha_salida"] is not None
    assert mov["observaciones_salida"] == "Salida ok"

    # Verificar que la celda se liberó a DISPONIBLE
    cursor.execute("SELECT estado FROM celdas WHERE id = ?;", (celda_id,))
    celda = cursor.fetchone()
    assert celda["estado"] == "DISPONIBLE"


def test_impedir_pago_duplicado_mensualidad(conn):
    """Verifica que no se pueda registrar un segundo pago para el mismo vehículo y periodo."""
    cursor = conn.cursor()

    cursor.execute("SELECT vehiculo_id, cliente_id, periodo FROM mensualidades LIMIT 1;")
    m = cursor.fetchone()

    with pytest.raises(ValueError) as excinfo:
        services.registrar_mensualidad(
            conn=conn,
            vehiculo_id=m["vehiculo_id"],
            cliente_id=m["cliente_id"],
            periodo=m["periodo"],
            fecha_inicio="2026-10-01",
            fecha_fin="2026-10-31",
            valor=180000,
            fecha_pago="2026-10-15",
            metodo_pago="Efectivo"
        )

    assert "Ya existe un pago registrado para este vehículo" in str(excinfo.value)


def test_historial_con_filtros(conn):
    """Verifica la consulta de historial y el correcto filtrado por placa y estado."""
    # Filtrar por placa específica
    cursor = conn.cursor()
    cursor.execute("SELECT placa FROM vehiculos LIMIT 1;")
    placa = cursor.fetchone()["placa"]

    resultados = services.get_historial_movimientos(conn=conn, placa=placa)
    for r in resultados:
        assert placa in r["placa"]

    # Filtrar por estado ACTIVO
    activos = services.get_historial_movimientos(conn=conn, estado="ACTIVO")
    for a in activos:
        assert a["estado"] == "ACTIVO"
