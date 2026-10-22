"""
services.py - Capa de lógica del negocio y consultas seguras para Autos Colombia.
"""

from datetime import datetime, date
import sqlite3


def get_dashboard_stats(conn):
    """
    Obtiene las métricas clave para el panel principal (dashboard).
    """
    cursor = conn.cursor()

    # 1. Vehículos dentro actualmente
    cursor.execute("SELECT COUNT(*) AS total FROM movimientos WHERE estado = 'ACTIVO';")
    vehiculos_dentro = cursor.fetchone()["total"]

    # 2. Total de celdas y disponibles
    cursor.execute("SELECT COUNT(*) AS total FROM celdas;")
    total_celdas = cursor.fetchone()["total"]

    cursor.execute("SELECT COUNT(*) AS total FROM celdas WHERE estado = 'DISPONIBLE';")
    celdas_disponibles = cursor.fetchone()["total"]

    # 3. Novedades activas/abiertas
    cursor.execute("SELECT COUNT(*) AS total FROM novedades WHERE estado IN ('ABIERTO', 'EN_REVISION');")
    novedades_activas = cursor.fetchone()["total"]

    # 4. Estado de mensualidades para el periodo actual
    periodo_actual = datetime.now().strftime("%Y-%m")
    cursor.execute("""
        SELECT COUNT(DISTINCT v.id) AS total_vehiculos_activos
        FROM vehiculos v
        WHERE v.activo = 1;
    """)
    total_vehiculos = cursor.fetchone()["total_vehiculos_activos"]

    cursor.execute("""
        SELECT COUNT(DISTINCT m.vehiculo_id) AS total_pagadas
        FROM mensualidades m
        JOIN vehiculos v ON v.id = m.vehiculo_id
        WHERE m.periodo = ? AND m.estado = 'PAGADO' AND v.activo = 1;
    """, (periodo_actual,))
    pagadas_mes = cursor.fetchone()["total_pagadas"]

    pendientes_mes = max(0, total_vehiculos - pagadas_mes)

    # 5. Lista completa de celdas con estado actual y vehículo ocupante si aplica
    cursor.execute("""
        SELECT 
            c.id, c.codigo, c.tipo_permitido, c.estado, c.ubicacion,
            m.id AS movimiento_id,
            m.fecha_entrada,
            v.placa, v.marca, v.modelo, v.color, v.tipo AS tipo_vehiculo,
            cli.nombre AS cliente_nombre, cli.telefono AS cliente_telefono
        FROM celdas c
        LEFT JOIN movimientos m ON m.celda_id = c.id AND m.estado = 'ACTIVO'
        LEFT JOIN vehiculos v ON v.id = m.vehiculo_id
        LEFT JOIN clientes cli ON cli.id = v.cliente_id
        ORDER BY c.tipo_permitido ASC, c.codigo ASC;
    """)
    celdas_mapa = cursor.fetchall()

    # 6. Movimientos recientes (últimos 8)
    cursor.execute("""
        SELECT 
            m.id, m.fecha_entrada, m.fecha_salida, m.estado,
            m.observaciones_entrada, m.observaciones_salida,
            v.placa, v.tipo AS tipo_vehiculo, v.marca, v.modelo,
            c.codigo AS codigo_celda,
            cli.nombre AS cliente_nombre,
            u.nombre AS usuario_nombre
        FROM movimientos m
        JOIN vehiculos v ON v.id = m.vehiculo_id
        JOIN celdas c ON c.id = m.celda_id
        JOIN clientes cli ON cli.id = v.cliente_id
        LEFT JOIN usuarios u ON u.id = m.usuario_id
        ORDER BY m.id DESC
        LIMIT 8;
    """)
    movimientos_recientes = cursor.fetchall()

    return {
        "vehiculos_dentro": vehiculos_dentro,
        "celdas_disponibles": celdas_disponibles,
        "total_celdas": total_celdas,
        "porcentaje_ocupacion": round(((total_celdas - celdas_disponibles) / total_celdas * 100), 1) if total_celdas > 0 else 0,
        "mensualidades_pendientes": pendientes_mes,
        "mensualidades_al_dia": pagadas_mes,
        "novedades_activas": novedades_activas,
        "celdas_mapa": celdas_mapa,
        "movimientos_recientes": movimientos_recientes,
        "periodo_actual": periodo_actual
    }


def registrar_entrada(conn, vehiculo_id, celda_id, usuario_id=None, observaciones=""):
    """
    Registra el ingreso de un vehículo en una celda disponible.
    Aplica reglas de negocio:
    - El vehículo no puede tener ya una estancia activa.
    - La celda debe estar en estado DISPONIBLE.
    - Actualiza el estado de la celda a OCUPADA en la misma transacción.
    """
    cursor = conn.cursor()

    # Validar vehículo activo y existente
    cursor.execute("SELECT id, placa, tipo, activo FROM vehiculos WHERE id = ?;", (vehiculo_id,))
    vehiculo = cursor.fetchone()
    if not vehiculo:
        raise ValueError("El vehículo especificado no existe.")
    if not vehiculo["activo"]:
        raise ValueError(f"El vehículo {vehiculo['placa']} está inactivo en el sistema.")

    # Validar que no tenga estancia activa
    cursor.execute("""
        SELECT m.id, c.codigo 
        FROM movimientos m 
        JOIN celdas c ON c.id = m.celda_id
        WHERE m.vehiculo_id = ? AND m.estado = 'ACTIVO';
    """, (vehiculo_id,))
    estancia_activa = cursor.fetchone()
    if estancia_activa:
        raise ValueError(
            f"El vehículo {vehiculo['placa']} ya se encuentra dentro del parqueadero en la celda {estancia_activa['codigo']}."
        )

    # Validar que la celda exista y esté DISPONIBLE
    cursor.execute("SELECT id, codigo, tipo_permitido, estado FROM celdas WHERE id = ?;", (celda_id,))
    celda = cursor.fetchone()
    if not celda:
        raise ValueError("La celda especificada no existe.")
    if celda["estado"] != "DISPONIBLE":
        raise ValueError(f"La celda {celda['codigo']} no está disponible (Estado actual: {celda['estado']}).")

    # Registrar el movimiento
    cursor.execute("""
        INSERT INTO movimientos (vehiculo_id, celda_id, usuario_id, observaciones_entrada, estado)
        VALUES (?, ?, ?, ?, 'ACTIVO');
    """, (vehiculo_id, celda_id, usuario_id, observaciones.strip() if observaciones else None))

    movimiento_id = cursor.lastrowid

    # Ocupar la celda
    cursor.execute("UPDATE celdas SET estado = 'OCUPADA' WHERE id = ?;", (celda_id,))

    conn.commit()
    return movimiento_id


def registrar_salida(conn, movimiento_id, observaciones_salida=""):
    """
    Registra la salida de un vehículo, finalizando su movimiento y liberando la celda.
    """
    cursor = conn.cursor()

    # Validar movimiento activo
    cursor.execute("""
        SELECT m.id, m.celda_id, m.estado, v.placa, c.codigo AS codigo_celda
        FROM movimientos m
        JOIN vehiculos v ON v.id = m.vehiculo_id
        JOIN celdas c ON c.id = m.celda_id
        WHERE m.id = ?;
    """, (movimiento_id,))
    mov = cursor.fetchone()

    if not mov:
        raise ValueError("El registro de movimiento no fue encontrado.")
    if mov["estado"] != "ACTIVO":
        raise ValueError(f"El movimiento ya fue finalizado previamente para el vehículo {mov['placa']}.")

    # Actualizar movimiento a FINALIZADO con fecha y hora actual
    cursor.execute("""
        UPDATE movimientos 
        SET fecha_salida = CURRENT_TIMESTAMP,
            observaciones_salida = ?,
            estado = 'FINALIZADO'
        WHERE id = ?;
    """, (observaciones_salida.strip() if observaciones_salida else None, movimiento_id))

    # Liberar la celda correspondiente
    cursor.execute("UPDATE celdas SET estado = 'DISPONIBLE' WHERE id = ?;", (mov["celda_id"],))

    conn.commit()
    return mov


def registrar_mensualidad(conn, vehiculo_id, cliente_id, periodo, fecha_inicio, fecha_fin, 
                          valor, fecha_pago, metodo_pago, referencia_pago="", estado="PAGADO", 
                          observaciones="", usuario_id=None):
    """
    Registra el pago de una mensualidad. Impide registrar pagos duplicados para el mismo vehículo y periodo.
    """
    cursor = conn.cursor()

    # Validar duplicados de periodo para el vehículo
    cursor.execute("""
        SELECT id FROM mensualidades 
        WHERE vehiculo_id = ? AND periodo = ?;
    """, (vehiculo_id, periodo))
    existente = cursor.fetchone()

    if existente:
        raise ValueError(f"Ya existe un pago registrado para este vehículo en el periodo {periodo}.")

    try:
        valor_float = float(valor)
        if valor_float <= 0:
            raise ValueError("El valor de la mensualidad debe ser mayor a cero.")
    except (TypeError, ValueError):
        raise ValueError("El valor ingresado no es un número válido.")

    cursor.execute("""
        INSERT INTO mensualidades 
        (vehiculo_id, cliente_id, periodo, fecha_inicio, fecha_fin, valor, fecha_pago, metodo_pago, referencia_pago, estado, observaciones, usuario_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
    """, (
        vehiculo_id, cliente_id, periodo, fecha_inicio, fecha_fin,
        valor_float, fecha_pago, metodo_pago, referencia_pago.strip() if referencia_pago else None,
        estado, observaciones.strip() if observaciones else None, usuario_id
    ))

    mensualidad_id = cursor.lastrowid
    conn.commit()
    return mensualidad_id


def get_historial_movimientos(conn, placa=None, fecha_desde=None, fecha_hasta=None, estado=None):
    """
    Consulta el historial completo de movimientos con filtros opcionales.
    """
    cursor = conn.cursor()
    query = """
        SELECT 
            m.id, m.fecha_entrada, m.fecha_salida, m.estado,
            m.observaciones_entrada, m.observaciones_salida,
            v.placa, v.tipo AS tipo_vehiculo, v.marca, v.modelo, v.color,
            c.codigo AS codigo_celda, c.tipo_permitido AS celda_tipo,
            cli.nombre AS cliente_nombre, cli.documento AS cliente_documento,
            u.nombre AS usuario_nombre
        FROM movimientos m
        JOIN vehiculos v ON v.id = m.vehiculo_id
        JOIN celdas c ON c.id = m.celda_id
        JOIN clientes cli ON cli.id = v.cliente_id
        LEFT JOIN usuarios u ON u.id = m.usuario_id
        WHERE 1=1
    """
    params = []

    if placa and placa.strip():
        query += " AND v.placa LIKE ?"
        params.append(f"%{placa.strip().upper()}%")

    if fecha_desde and fecha_desde.strip():
        query += " AND date(m.fecha_entrada) >= date(?)"
        params.append(fecha_desde.strip())

    if fecha_hasta and fecha_hasta.strip():
        query += " AND date(m.fecha_entrada) <= date(?)"
        params.append(fecha_hasta.strip())

    if estado and estado.strip() and estado.upper() != "TODOS":
        query += " AND m.estado = ?"
        params.append(estado.strip().upper())

    query += " ORDER BY m.id DESC"

    cursor.execute(query, params)
    return cursor.fetchall()
