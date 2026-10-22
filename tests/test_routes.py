"""
test_routes.py - Pruebas de integración HTTP de rutas, autenticación y vistas Flask.
"""

import pytest
import os
import tempfile
from app import app
from database import init_db


@pytest.fixture
def client():
    """Configura el cliente de pruebas de Flask con base de datos temporal."""
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


def login_as_admin(client):
    """Helper para autenticar sesión como administrador."""
    return client.post("/login", data={
        "username": "admin",
        "password": "admin123"
    }, follow_redirects=True)


def test_login_flow(client):
    """Prueba flujo de login con credenciales correctas e incorrectas."""
    # Acceso sin login a dashboard redirige a /login
    res = client.get("/", follow_redirects=False)
    assert res.status_code == 302
    assert "/login" in res.headers["Location"]

    # Login incorrecto
    res_bad = client.post("/login", data={"username": "admin", "password": "wrongpassword"}, follow_redirects=True)
    assert b"Credenciales incorrectas" in res_bad.data

    # Login correcto
    res_ok = login_as_admin(client)
    assert res_ok.status_code == 200
    assert b"Panel Principal" in res_ok.data


def test_dashboard_renders_stats(client):
    """Verifica que el dashboard cargue métricas y celdas."""
    login_as_admin(client)
    res = client.get("/")
    assert res.status_code == 200
    assert b"Distribuci\xc3\xb3n Visual de Celdas" in res.data
    assert b"Veh\xc3\xadculos Estacionados" in res.data


def test_crud_cliente(client):
    """Verifica registro, listado y edición de un nuevo cliente."""
    login_as_admin(client)

    # 1. Crear nuevo cliente
    nuevo_doc = "1199887766"
    res_post = client.post("/clientes/nuevo", data={
        "tipo_documento": "CC",
        "documento": nuevo_doc,
        "nombre": "Prueba Cliente Integration",
        "telefono": "3119998877",
        "email": "prueba@test.com",
        "direccion": "Calle 50 # 10-20"
    }, follow_redirects=True)

    assert res_post.status_code == 200
    assert b"registrado exitosamente" in res_post.data
    assert b"Prueba Cliente Integration" in res_post.data

    # 2. Intentar registrar el mismo documento debe fallar
    res_dup = client.post("/clientes/nuevo", data={
        "tipo_documento": "CC",
        "documento": nuevo_doc,
        "nombre": "Otro Nombre",
        "telefono": "3001112233"
    }, follow_redirects=True)
    assert b"Ya existe un cliente registrado con el documento" in res_dup.data


def test_crud_vehiculo(client):
    """Verifica registro de vehículo y validación de placa única."""
    login_as_admin(client)

    nueva_placa = "TST999"
    res_post = client.post("/vehiculos/nuevo", data={
        "placa": nueva_placa,
        "marca": "Chevrolet",
        "modelo": "Sail 2019",
        "color": "Gris",
        "tipo": "Automóvil",
        "cliente_id": "1"
    }, follow_redirects=True)

    assert res_post.status_code == 200
    assert b"registrado correctamente" in res_post.data
    assert b"TST999" in res_post.data

    # Intentar duplicar placa
    res_dup = client.post("/vehiculos/nuevo", data={
        "placa": nueva_placa,
        "marca": "Toyota",
        "modelo": "Corolla",
        "color": "Negro",
        "tipo": "Automóvil",
        "cliente_id": "1"
    }, follow_redirects=True)
    assert b"ya se encuentra registrada" in res_dup.data


def test_movimiento_entrada_y_salida(client):
    """Verifica el flujo completo HTTP de entrada de vehículo y posterior salida."""
    login_as_admin(client)

    # Crear vehículo para la prueba
    placa_test = "MOV123"
    client.post("/vehiculos/nuevo", data={
        "placa": placa_test,
        "marca": "Suzuki",
        "modelo": "Swift 2022",
        "color": "Azul",
        "tipo": "Automóvil",
        "cliente_id": "1"
    })

    # Obtener ID del vehículo recién creado
    import database
    conn = database.get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM vehiculos WHERE placa = ?;", (placa_test,))
    vehiculo_id = cursor.fetchone()["id"]

    # Buscar celda disponible
    cursor.execute("SELECT id, codigo FROM celdas WHERE estado = 'DISPONIBLE' LIMIT 1;")
    celda = cursor.fetchone()
    celda_id = celda["id"]
    conn.close()

    # 1. Registrar entrada
    res_in = client.post("/movimientos/entrada", data={
        "vehiculo_id": str(vehiculo_id),
        "celda_id": str(celda_id),
        "observaciones": "Entrada test HTTP"
    }, follow_redirects=True)

    assert res_in.status_code == 200
    assert b"Ingreso registrado exitosamente" in res_in.data

    # 2. Verificar que aparezca en la lista de activos
    res_activos = client.get("/movimientos")
    assert b"MOV123" in res_activos.data

    # 3. Registrar salida
    conn = database.get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM movimientos WHERE vehiculo_id = ? AND estado = 'ACTIVO';", (vehiculo_id,))
    mov_id = cursor.fetchone()["id"]
    conn.close()

    res_out = client.post(f"/movimientos/{mov_id}/salida", data={
        "observaciones_salida": "Salida sin problemas"
    }, follow_redirects=True)

    assert res_out.status_code == 200
    assert b"Salida registrada con" in res_out.data


def test_mensualidad_registro_y_duplicado(client):
    """Verifica registro de pago y prevención de duplicados vía HTTP."""
    login_as_admin(client)

    # Registrar mensualidad para periodo futuro 2027-01
    res = client.post("/mensualidades/nuevo", data={
        "vehiculo_id": "1",
        "periodo": "2027-01",
        "fecha_inicio": "2027-01-01",
        "fecha_fin": "2027-01-31",
        "valor": "190000",
        "fecha_pago": "2027-01-02",
        "metodo_pago": "Efectivo",
        "referencia_pago": "REC-TEST",
        "estado": "PAGADO",
        "observaciones": "Pago test"
    }, follow_redirects=True)

    assert res.status_code == 200
    assert b"registrada con" in res.data

    # Intentar registrar el mismo periodo para el mismo vehículo
    res_dup = client.post("/mensualidades/nuevo", data={
        "vehiculo_id": "1",
        "periodo": "2027-01",
        "fecha_inicio": "2027-01-01",
        "fecha_fin": "2027-01-31",
        "valor": "190000",
        "fecha_pago": "2027-01-02",
        "metodo_pago": "Efectivo",
        "referencia_pago": "REC-TEST-2",
        "estado": "PAGADO"
    }, follow_redirects=True)

    assert b"Ya existe un pago registrado" in res_dup.data


def test_novedades_registro_y_resolucion(client):
    """Verifica registro y resolución de incidentes en bitácora."""
    login_as_admin(client)

    res_post = client.post("/novedades/nueva", data={
        "tipo": "Objeto olvidado",
        "vehiculo_id": "1",
        "descripcion": "Se encontró sombrilla en celda"
    }, follow_redirects=True)

    assert res_post.status_code == 200
    assert b"Novedad registrada exitosamente" in res_post.data

    # Obtener ID de la novedad creada
    import database
    conn = database.get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM novedades ORDER BY id DESC LIMIT 1;")
    nov_id = cursor.fetchone()["id"]
    conn.close()

    # Resolver novedad
    res_sol = client.post(f"/novedades/{nov_id}/resolver", data={
        "estado": "SOLUCIONADO",
        "solucion_notas": "Entregado a propietario"
    }, follow_redirects=True)

    assert res_sol.status_code == 200
    assert b"actualizada a estado" in res_sol.data
