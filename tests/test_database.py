"""
test_database.py - Pruebas automatizadas de la base de datos y restricciones de SQLite.
"""

import pytest
import sqlite3
import os
import tempfile
from database import get_db_connection, init_db, seed_demo_data


@pytest.fixture
def test_db():
    """Crea una base de datos temporal aislada para cada prueba."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    init_db(path)
    yield path
    if os.path.exists(path):
        os.remove(path)


def test_init_db_creates_tables_and_seeds(test_db):
    """Verifica que las tablas se creen correctamente y se siembren datos iniciales."""
    conn = get_db_connection(test_db)
    cursor = conn.cursor()

    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = [row["name"] for row in cursor.fetchall()]

    assert "usuarios" in tables
    assert "clientes" in tables
    assert "vehiculos" in tables
    assert "celdas" in tables
    assert "movimientos" in tables
    assert "mensualidades" in tables
    assert "novedades" in tables

    # Verificar que los datos iniciales existan
    cursor.execute("SELECT COUNT(*) AS total FROM usuarios;")
    assert cursor.fetchone()["total"] >= 2

    cursor.execute("SELECT COUNT(*) AS total FROM celdas;")
    assert cursor.fetchone()["total"] >= 14

    cursor.execute("SELECT COUNT(*) AS total FROM vehiculos;")
    assert cursor.fetchone()["total"] >= 4

    conn.close()


def test_foreign_key_enforcement(test_db):
    """Verifica que las restricciones de clave foránea estén activas y bloqueen inconsistencias."""
    conn = get_db_connection(test_db)
    cursor = conn.cursor()

    # Intentar insertar un vehículo con un cliente_id que no existe
    with pytest.raises(sqlite3.IntegrityError):
        cursor.execute("""
            INSERT INTO vehiculos (placa, marca, modelo, color, tipo, cliente_id, activo)
            VALUES ('ZZZ999', 'Test', 'Model', 'Gris', 'Automóvil', 999999, 1);
        """)
        conn.commit()

    conn.close()


def test_unique_plate_constraint(test_db):
    """Verifica que la restricción de placa única sea respetada."""
    conn = get_db_connection(test_db)
    cursor = conn.cursor()

    cursor.execute("SELECT placa, cliente_id FROM vehiculos LIMIT 1;")
    row = cursor.fetchone()
    placa_existente = row["placa"]
    cliente_id = row["cliente_id"]

    # Intentar insertar un vehículo con la misma placa
    with pytest.raises(sqlite3.IntegrityError):
        cursor.execute("""
            INSERT INTO vehiculos (placa, marca, modelo, color, tipo, cliente_id, activo)
            VALUES (?, 'Otra', 'Marca', 'Blanco', 'Automóvil', ?, 1);
        """, (placa_existente, cliente_id))
        conn.commit()

    conn.close()


def test_unique_mensualidad_periodo_constraint(test_db):
    """Verifica que no se permitan dos pagos para el mismo vehículo y mismo periodo."""
    conn = get_db_connection(test_db)
    cursor = conn.cursor()

    cursor.execute("SELECT vehiculo_id, cliente_id, periodo FROM mensualidades LIMIT 1;")
    m = cursor.fetchone()

    with pytest.raises(sqlite3.IntegrityError):
        cursor.execute("""
            INSERT INTO mensualidades 
            (vehiculo_id, cliente_id, periodo, fecha_inicio, fecha_fin, valor, fecha_pago, metodo_pago, estado)
            VALUES (?, ?, ?, '2026-10-01', '2026-10-31', 180000, '2026-10-05', 'Efectivo', 'PAGADO');
        """, (m["vehiculo_id"], m["cliente_id"], m["periodo"]))
        conn.commit()

    conn.close()
