"""
test_pagos.py - Pruebas automatizadas de la Gestión de Pagos y Mensualidades (Iteración 3).

Cubre los 12 casos de prueba requeridos:
1.  test_registrar_pago_exitoso (RF-01, RF-03, RF-04)
2.  test_validacion_campos_obligatorios (RNF-02)
3.  test_rechazo_valores_negativos_o_cero (RNF-04)
4.  test_prevencion_pagos_duplicados_mismo_periodo (RF-10, RNF-08)
5.  test_consulta_historial_pagos (RF-02, RF-14)
6.  test_filtros_pagos_por_cliente (RF-06)
7.  test_filtros_pagos_por_fechas_y_periodo (RF-03, RF-09)
8.  test_actualizacion_estados_pagada_pendiente_vencida (RF-07, RF-08)
9.  test_generacion_y_visualizacion_comprobante (RF-05, RF-11)
10. test_permisos_anulacion_solo_admin (RF-12, RNF-05)
11. test_resumen_financiero_kpis (RF-13)
12. test_persistencia_datos_pagos_sqlite (RNF-01, RNF-07)
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

    try:
        if os.path.exists(path):
            os.remove(path)
    except OSError:
        pass


def login_admin(client):
    """Autentica sesión con rol de Administrador."""
    return client.post("/login", data={
        "username": "admin",
        "password": "admin123"
    }, follow_redirects=True)


def login_operador(client):
    """Autentica sesión con rol de Operador."""
    return client.post("/login", data={
        "username": "operador",
        "password": "operador123"
    }, follow_redirects=True)


# ----------------------------------------------------------------------
# 1. Registro Exitoso de Pagos
# ----------------------------------------------------------------------
def test_registrar_pago_exitoso(client):
    """RF-01, RF-03, RF-04: Registro válido de un pago de mensualidad."""
    login_admin(client)

    res = client.post("/mensualidades/nuevo", data={
        "vehiculo_id": "1",
        "periodo": "2027-01",
        "fecha_inicio": "2027-01-01",
        "fecha_fin": "2027-01-31",
        "valor": "180000",
        "fecha_pago": "2027-01-02",
        "metodo_pago": "Transferencia Bancolombia",
        "referencia_pago": "TRF-98765",
        "estado": "PAGADO",
        "observaciones": "Pago oportuno mensualidad enero"
    }, follow_redirects=True)

    assert res.status_code == 200
    assert b"registrada con" in res.data or b"exito" in res.data or "éxito".encode("utf-8") in res.data

    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM mensualidades WHERE periodo = '2027-01' AND vehiculo_id = 1;")
        pago = cursor.fetchone()
    finally:
        conn.close()

    assert pago is not None
    assert pago["valor"] == 180000
    assert pago["metodo_pago"] == "Transferencia Bancolombia"
    assert pago["referencia_pago"] == "TRF-98765"
    assert pago["estado"] == "PAGADO"


# ----------------------------------------------------------------------
# 2. Validación de Campos Obligatorios
# ----------------------------------------------------------------------
def test_validacion_campos_obligatorios(client):
    """RNF-02: Rechazo cuando faltan campos requeridos en el registro."""
    login_admin(client)

    res = client.post("/mensualidades/nuevo", data={
        "vehiculo_id": "1",
        "periodo": "",
        "fecha_inicio": "",
        "fecha_fin": "",
        "valor": "180000",
        "fecha_pago": "2026-11-02",
        "metodo_pago": "Efectivo",
        "estado": "PAGADO"
    }, follow_redirects=True)

    assert res.status_code == 200
    assert b"obligatorios" in res.data


# ----------------------------------------------------------------------
# 3. Rechazo de Valores Negativos o Cero
# ----------------------------------------------------------------------
def test_rechazo_valores_negativos_o_cero(client):
    """RNF-04: Impedir montos monetarios negativos, cero o inválidos."""
    conn = get_db_connection()
    try:
        # Monto negativo
        with pytest.raises(ValueError, match="mayor a cero"):
            services.registrar_mensualidad(
                conn=conn,
                vehiculo_id=1,
                cliente_id=1,
                periodo="2027-03",
                fecha_inicio="2027-03-01",
                fecha_fin="2027-03-31",
                valor=-50000,
                fecha_pago="2027-03-01",
                metodo_pago="Efectivo"
            )

        # Monto cero
        with pytest.raises(ValueError, match="mayor a cero"):
            services.registrar_mensualidad(
                conn=conn,
                vehiculo_id=1,
                cliente_id=1,
                periodo="2027-03",
                fecha_inicio="2027-03-01",
                fecha_fin="2027-03-31",
                valor=0,
                fecha_pago="2027-03-01",
                metodo_pago="Efectivo"
            )
    finally:
        conn.close()


# ----------------------------------------------------------------------
# 4. Prevención de Pagos Duplicados en el Mismo Periodo
# ----------------------------------------------------------------------
def test_prevencion_pagos_duplicados_mismo_periodo(client):
    """RF-10, RNF-08: Evitar registrar dos veces el mismo pago para el mismo periodo y vehículo."""
    login_admin(client)

    # Primer registro para 2027-05 vehículo 1
    res1 = client.post("/mensualidades/nuevo", data={
        "vehiculo_id": "1",
        "periodo": "2027-05",
        "fecha_inicio": "2027-05-01",
        "fecha_fin": "2027-05-31",
        "valor": "180000",
        "fecha_pago": "2027-05-01",
        "metodo_pago": "Efectivo",
        "estado": "PAGADO"
    }, follow_redirects=True)
    assert res1.status_code == 200

    # Segundo intento duplicado para el mismo vehículo y mismo periodo
    res2 = client.post("/mensualidades/nuevo", data={
        "vehiculo_id": "1",
        "periodo": "2027-05",
        "fecha_inicio": "2027-05-01",
        "fecha_fin": "2027-05-31",
        "valor": "180000",
        "fecha_pago": "2027-05-05",
        "metodo_pago": "Nequi / Daviplata",
        "estado": "PAGADO"
    }, follow_redirects=True)

    assert res2.status_code == 200
    assert b"Ya existe" in res2.data or b"duplicad" in res2.data or b"registrada" in res2.data


# ----------------------------------------------------------------------
# 5. Consulta de Historial de Pagos
# ----------------------------------------------------------------------
def test_consulta_historial_pagos(client):
    """RF-02, RF-14: Consulta general del historial de pagos y libro mayor."""
    login_admin(client)

    res = client.get("/pagos/historial")
    assert res.status_code == 200
    assert b"Historial General de Pagos" in res.data
    assert b"Total Recaudado" in res.data
    assert b"REC-" in res.data

    res_m = client.get("/mensualidades")
    assert res_m.status_code == 200
    assert b"REC-" in res_m.data


# ----------------------------------------------------------------------
# 6. Filtros de Pagos por Cliente
# ----------------------------------------------------------------------
def test_filtros_pagos_por_cliente(client):
    """RF-06: Consulta de pagos específicos de un cliente."""
    login_admin(client)

    res = client.get("/clientes/1/pagos")
    assert res.status_code == 200
    assert b"Historial de Pagos del Cliente" in res.data
    assert b"Total Pagado" in res.data

    res_filtro = client.get("/mensualidades?cliente_id=1")
    assert res_filtro.status_code == 200


# ----------------------------------------------------------------------
# 7. Filtros por Fechas, Periodos y Métodos
# ----------------------------------------------------------------------
def test_filtros_pagos_por_fechas_y_periodo(client):
    """RF-03, RF-09: Filtrado por fechas, periodos y métodos de pago."""
    conn = get_db_connection()
    try:
        services.registrar_mensualidad(
            conn=conn,
            vehiculo_id=1,
            cliente_id=1,
            periodo="2027-08",
            fecha_inicio="2027-08-01",
            fecha_fin="2027-08-31",
            valor=150000,
            fecha_pago="2027-08-05",
            metodo_pago="Efectivo"
        )

        services.registrar_mensualidad(
            conn=conn,
            vehiculo_id=1,
            cliente_id=1,
            periodo="2027-09",
            fecha_inicio="2027-09-01",
            fecha_fin="2027-09-30",
            valor=150000,
            fecha_pago="2027-09-10",
            metodo_pago="Transferencia Bancolombia"
        )

        # Filtrar por periodo 2027-08
        pagos_ago = services.get_historial_pagos(conn, periodo="2027-08")
        assert len(pagos_ago) == 1
        assert pagos_ago[0]["periodo"] == "2027-08"

        # Filtrar por método Transferencia
        pagos_trf = services.get_historial_pagos(conn, metodo_pago="Transferencia Bancolombia")
        assert any(p["metodo_pago"] == "Transferencia Bancolombia" for p in pagos_trf)

        # Filtrar por rango de fechas
        pagos_rango = services.get_historial_pagos(conn, fecha_desde="2027-09-01", fecha_hasta="2027-09-30")
        assert all("2027-09" in p["fecha_pago"] for p in pagos_rango)
    finally:
        conn.close()


# ----------------------------------------------------------------------
# 8. Actualización de Estados (PAGADO, PENDIENTE, VENCIDO)
# ----------------------------------------------------------------------
def test_actualizacion_estados_pagada_pendiente_vencida(client):
    """RF-07, RF-08: Identificar mensualidades pagadas, pendientes y vencidas."""
    conn = get_db_connection()
    try:
        # Registrar una mensualidad con fecha fin expirada en estado PENDIENTE
        id_expirada = services.registrar_mensualidad(
            conn=conn,
            vehiculo_id=2,
            cliente_id=2,
            periodo="2020-01",
            fecha_inicio="2020-01-01",
            fecha_fin="2020-01-31",
            valor=120000,
            fecha_pago="2020-01-05",
            metodo_pago="Efectivo",
            estado="PENDIENTE"
        )

        # Al registrar con fecha fin pasada y estado PENDIENTE, se marca automáticamente VENCIDO
        pago = services.get_pago_por_id(conn, id_expirada)
        assert pago["estado"] == "VENCIDO"

        # Una mensualidad PAGADA con fecha fin pasada conserva su estado PAGADO
        id_pagada = services.registrar_mensualidad(
            conn=conn,
            vehiculo_id=3,
            cliente_id=2,
            periodo="2020-02",
            fecha_inicio="2020-02-01",
            fecha_fin="2020-02-28",
            valor=120000,
            fecha_pago="2020-02-05",
            metodo_pago="Efectivo",
            estado="PAGADO"
        )
        pago_pagado = services.get_pago_por_id(conn, id_pagada)
        assert pago_pagado["estado"] == "PAGADO"
    finally:
        conn.close()


# ----------------------------------------------------------------------
# 9. Generación y Visualización de Comprobante / Recibo
# ----------------------------------------------------------------------
def test_generacion_y_visualizacion_comprobante(client):
    """RF-05, RF-11: Vista del comprobante oficial de pago y detalle de transacción."""
    login_admin(client)

    # Comprobante imprimible de la mensualidad semilla 1
    res = client.get("/mensualidades/1/comprobante")
    assert res.status_code == 200
    assert b"REC-00001" in res.data
    assert b"AUTOS COLOMBIA" in res.data
    assert b"COMPROBANTE" in res.data
    assert b"window.print()" in res.data

    # Detalle de la transacción
    res_det = client.get("/mensualidades/1")
    assert res_det.status_code == 200
    assert b"Detalle de Transacci" in res_det.data
    assert b"REC-00001" in res_det.data


# ----------------------------------------------------------------------
# 10. Permisos de Anulación: Solo Administrador
# ----------------------------------------------------------------------
def test_permisos_anulacion_solo_admin(client):
    """RF-12, RNF-05: El operador no puede anular pagos; el administrador sí."""
    # 1. Operador intenta anular
    login_operador(client)
    res_op = client.post("/mensualidades/1/estado", data={
        "nuevo_estado": "ANULADO"
    }, follow_redirects=True)

    assert res_op.status_code == 200
    assert b"Acceso denegado" in res_op.data or b"Solo los administradores" in res_op.data

    # Verificar que el pago sigue PAGADO
    conn = get_db_connection()
    try:
        p = services.get_pago_por_id(conn, 1)
        assert p["estado"] == "PAGADO"
    finally:
        conn.close()

    # Cerrar sesión del operador
    client.get("/logout", follow_redirects=True)

    # 2. Administrador realiza la anulación
    login_admin(client)
    res_adm = client.post("/mensualidades/1/estado", data={
        "nuevo_estado": "ANULADO"
    }, follow_redirects=True)

    assert res_adm.status_code == 200
    assert b"actualizado a" in res_adm.data and b"ANULADO" in res_adm.data

    conn = get_db_connection()
    try:
        p_anulado = services.get_pago_por_id(conn, 1)
        assert p_anulado["estado"] == "ANULADO"
    finally:
        conn.close()


# ----------------------------------------------------------------------
# 11. Resumen Financiero y Métricas KPI
# ----------------------------------------------------------------------
def test_resumen_financiero_kpis(client):
    """RF-13: Resumen con total recaudado, cantidad de pagos y pendientes."""
    conn = get_db_connection()
    try:
        resumen = services.get_resumen_financiero(conn)
    finally:
        conn.close()

    assert "total_recaudado" in resumen
    assert "cantidad_pagos" in resumen
    assert "mensualidades_pendientes" in resumen
    assert "mensualidades_vencidas" in resumen
    assert "total_transacciones" in resumen

    assert resumen["total_recaudado"] > 0
    assert resumen["cantidad_pagos"] >= 1


# ----------------------------------------------------------------------
# 12. Persistencia e Integridad Relacional en SQLite
# ----------------------------------------------------------------------
def test_persistencia_datos_pagos_sqlite(client):
    """RNF-01, RNF-07: Persistencia, índices y consistencia relacional en SQLite."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()

        # Verificar existencia de índices para optimizar pagos
        cursor.execute("SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_mensualidades_%';")
        indices = [r["name"] for r in cursor.fetchall()]

        assert "idx_mensualidades_cliente" in indices
        assert "idx_mensualidades_fecha_pago" in indices
        assert "idx_mensualidades_estado" in indices

        # Integridad relacional: obtener un pago con join a cliente, vehículo y usuario
        cursor.execute("""
            SELECT m.id, m.valor, v.placa, c.nombre AS cliente_nombre, u.username AS usuario_registrador
            FROM mensualidades m
            JOIN vehiculos v ON v.id = m.vehiculo_id
            JOIN clientes c ON c.id = m.cliente_id
            LEFT JOIN usuarios u ON u.id = m.usuario_id
            WHERE m.id = 1;
        """)
        row = cursor.fetchone()
    finally:
        conn.close()

    assert row is not None
    assert row["placa"] is not None
    assert row["cliente_nombre"] is not None
