"""
test_celdas.py - Pruebas automatizadas de la Gestión de Celdas y Reglas Operativas (Iteración 2).
"""

import pytest
import os
import tempfile
from app import app
from database import init_db, get_db_connection
import services


@pytest.fixture
def client():
    """Configura un cliente de prueba aislado con base de datos temporal."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)

    os.environ["AUTOSCOLOMBIA_DB_PATH"] = path
    init_db(path)

    app.config["TESTING"] = True
    app.config["WTF_CSRF_ENABLED"] = False

    with app.test_client() as test_client:
        yield test_client

    if os.path.exists(path):
        os.remove(path)


def login_admin(client):
    """Helper para autenticar sesión como administrador."""
    return client.post("/login", data={
        "username": "admin",
        "password": "admin123"
    }, follow_redirects=True)


def test_registrar_celda_correctamente(client):
    """Verifica el registro de una nueva celda en el parqueadero."""
    login_admin(client)

    codigo_nuevo = "Z-99"
    res = client.post("/celdas/nueva", data={
        "codigo": codigo_nuevo,
        "tipo_permitido": "Automóvil",
        "ubicacion": "Bahía de Reserva"
    }, follow_redirects=True)

    assert res.status_code == 200
    assert b"creada con" in res.data
    assert b"Z-99" in res.data

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM celdas WHERE codigo = ?;", (codigo_nuevo,))
    celda = cursor.fetchone()
    conn.close()

    assert celda is not None
    assert celda["codigo"] == "Z-99"
    assert celda["tipo_permitido"] == "Automóvil"
    assert celda["estado"] == "DISPONIBLE"
    assert celda["activo"] == 1


def test_impedir_codigo_celda_duplicado(client):
    """Verifica que no sea posible registrar dos celdas con el mismo código identificador."""
    login_admin(client)

    # Intentar registrar celda con código existente 'A-01'
    res = client.post("/celdas/nueva", data={
        "codigo": "A-01",
        "tipo_permitido": "Automóvil",
        "ubicacion": "Piso 1"
    }, follow_redirects=True)

    assert res.status_code == 200
    assert b"Ya existe una celda registrada" in res.data


def test_editar_celda(client):
    """Verifica la edición de información de una celda existente."""
    login_admin(client)

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM celdas WHERE codigo = 'A-08';")
    celda_id = cursor.fetchone()["id"]
    conn.close()

    res = client.post(f"/celdas/{celda_id}/editar", data={
        "codigo": "A-08-MOD",
        "tipo_permitido": "Camioneta / SUV",
        "ubicacion": "Piso 1 - Reubicada"
    }, follow_redirects=True)

    assert res.status_code == 200
    assert b"actualizada satisfactoriamente" in res.data

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM celdas WHERE id = ?;", (celda_id,))
    celda = cursor.fetchone()
    conn.close()

    assert celda["codigo"] == "A-08-MOD"
    assert celda["tipo_permitido"] == "Camioneta / SUV"
    assert celda["ubicacion"] == "Piso 1 - Reubicada"


def test_cambiar_estado_celda(client):
    """Verifica el cambio de estado de una celda entre DISPONIBLE y MANTENIMIENTO."""
    login_admin(client)

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, codigo FROM celdas WHERE codigo = 'A-03';")
    celda = cursor.fetchone()
    celda_id = celda["id"]
    conn.close()

    # 1. Poner en mantenimiento
    res_mant = client.post(f"/celdas/{celda_id}/estado", data={
        "nuevo_estado": "MANTENIMIENTO"
    }, follow_redirects=True)

    assert res_mant.status_code == 200
    assert b"MANTENIMIENTO" in res_mant.data

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT estado FROM celdas WHERE id = ?;", (celda_id,))
    assert cursor.fetchone()["estado"] == "MANTENIMIENTO"
    conn.close()

    # 2. Habilitar de nuevo a disponible
    res_disp = client.post(f"/celdas/{celda_id}/estado", data={
        "nuevo_estado": "DISPONIBLE"
    }, follow_redirects=True)

    assert res_disp.status_code == 200
    assert b"DISPONIBLE" in res_disp.data

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT estado FROM celdas WHERE id = ?;", (celda_id,))
    assert cursor.fetchone()["estado"] == "DISPONIBLE"
    conn.close()


def test_desactivar_celda_disponible(client):
    """Verifica la baja lógica (desactivación) de una celda disponible."""
    login_admin(client)

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, codigo FROM celdas WHERE estado = 'DISPONIBLE' LIMIT 1;")
    celda = cursor.fetchone()
    celda_id = celda["id"]
    conn.close()

    # Desactivar celda
    res = client.post(f"/celdas/{celda_id}/toggle", follow_redirects=True)
    assert res.status_code == 200
    assert b"desactivada correctamente" in res.data

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT activo FROM celdas WHERE id = ?;", (celda_id,))
    assert cursor.fetchone()["activo"] == 0
    conn.close()


def test_impedir_desactivar_celda_ocupada(client):
    """Verifica la regla de negocio que prohíbe desactivar una celda mientras esté ocupada."""
    login_admin(client)

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, codigo FROM celdas WHERE estado = 'OCUPADA' LIMIT 1;")
    celda_ocupada = cursor.fetchone()
    celda_id = celda_ocupada["id"]
    conn.close()

    res = client.post(f"/celdas/{celda_id}/toggle", follow_redirects=True)
    assert res.status_code == 200
    assert b"No se puede desactivar" in res.data or b"est\xc3\xa1 actualmente ocupada" in res.data

    # La celda debe continuar activa
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT activo FROM celdas WHERE id = ?;", (celda_id,))
    assert cursor.fetchone()["activo"] == 1
    conn.close()


def test_impedir_mantenimiento_celda_ocupada(client):
    """Verifica la regla de negocio que prohíbe pasar a mantenimiento una celda ocupada."""
    login_admin(client)

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, codigo FROM celdas WHERE estado = 'OCUPADA' LIMIT 1;")
    celda_ocupada = cursor.fetchone()
    celda_id = celda_ocupada["id"]
    conn.close()

    res = client.post(f"/celdas/{celda_id}/estado", data={
        "nuevo_estado": "MANTENIMIENTO"
    }, follow_redirects=True)

    assert res.status_code == 200
    assert b"est\xc3\xa1 ocupada" in res.data or b"No se puede" in res.data

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT estado FROM celdas WHERE id = ?;", (celda_id,))
    assert cursor.fetchone()["estado"] == "OCUPADA"
    conn.close()


def test_compatibilidad_vehiculo_celda_rechazo(client):
    """Verifica que el sistema rechace el ingreso de un tipo de vehículo incompatible con la celda."""
    login_admin(client)

    conn = get_db_connection()
    cursor = conn.cursor()

    # 1. Crear una moto libre
    cursor.execute("""
        INSERT INTO vehiculos (placa, marca, modelo, color, tipo, cliente_id, activo)
        VALUES ('MOT999', 'Bajaj', 'Pulsar 200', 'Azul', 'Motocicleta', 1, 1);
    """)
    moto_id = cursor.lastrowid

    # 2. Buscar celda disponible para Automóvil
    cursor.execute("SELECT id, codigo FROM celdas WHERE tipo_permitido = 'Automóvil' AND estado = 'DISPONIBLE' LIMIT 1;")
    celda_auto = cursor.fetchone()
    conn.commit()
    conn.close()

    # Intentar ingresar la motocicleta en una celda de automóvil
    res = client.post("/movimientos/entrada", data={
        "vehiculo_id": str(moto_id),
        "celda_id": str(celda_auto["id"]),
        "observaciones": "Intento incompatible"
    }, follow_redirects=True)

    assert b"no es compatible con la celda" in res.data


def test_compatibilidad_vehiculo_celda_exito(client):
    """Verifica que el ingreso proceda cuando los tipos de vehículo y celda son compatibles."""
    login_admin(client)

    conn = get_db_connection()
    cursor = conn.cursor()

    # 1. Crear moto libre
    cursor.execute("""
        INSERT INTO vehiculos (placa, marca, modelo, color, tipo, cliente_id, activo)
        VALUES ('MOT888', 'Auteco', 'Agility 125', 'Rojo', 'Motocicleta', 1, 1);
    """)
    moto_id = cursor.lastrowid

    # 2. Celda disponible para Motocicleta
    cursor.execute("SELECT id, codigo FROM celdas WHERE tipo_permitido = 'Motocicleta' AND estado = 'DISPONIBLE' LIMIT 1;")
    celda_moto = cursor.fetchone()
    conn.commit()
    conn.close()

    res = client.post("/movimientos/entrada", data={
        "vehiculo_id": str(moto_id),
        "celda_id": str(celda_moto["id"]),
        "observaciones": "Ingreso compatible moto"
    }, follow_redirects=True)

    assert b"Ingreso registrado exitosamente" in res.data


def test_impedir_utilizar_celdas_desactivadas(client):
    """Verifica que una celda desactivada no pueda ser asignada para un nuevo ingreso vehicular."""
    login_admin(client)

    conn = get_db_connection()
    cursor = conn.cursor()

    # Tomar vehículo disponible de automóvil
    cursor.execute("""
        SELECT id FROM vehiculos 
        WHERE tipo = 'Automóvil' AND activo = 1 
        AND id NOT IN (SELECT vehiculo_id FROM movimientos WHERE estado = 'ACTIVO')
        LIMIT 1;
    """)
    vehiculo_id = cursor.fetchone()["id"]

    # Tomar celda disponible y desactivarla
    cursor.execute("SELECT id, codigo FROM celdas WHERE estado = 'DISPONIBLE' AND activo = 1 LIMIT 1;")
    celda = cursor.fetchone()
    celda_id = celda["id"]
    cursor.execute("UPDATE celdas SET activo = 0 WHERE id = ?;", (celda_id,))
    conn.commit()
    conn.close()

    # Intentar registrar entrada en la celda desactivada
    res = client.post("/movimientos/entrada", data={
        "vehiculo_id": str(vehiculo_id),
        "celda_id": str(celda_id)
    }, follow_redirects=True)

    assert b"desactivada del sistema" in res.data

