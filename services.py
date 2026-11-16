"""
services.py - Capa de lógica del negocio y consultas seguras para Autos Colombia.
"""

from datetime import datetime, date
import sqlite3


def actualizar_estados_vencidos(conn):
    """
    Actualiza automáticamente a 'VENCIDO' aquellas mensualidades en estado 'PENDIENTE'
    cuya fecha de fin ya expiró respecto a la fecha actual.
    """
    cursor = conn.cursor()
    hoy_str = date.today().strftime("%Y-%m-%d")
    cursor.execute("""
        UPDATE mensualidades
        SET estado = 'VENCIDO'
        WHERE estado = 'PENDIENTE' AND fecha_fin < ?;
    """, (hoy_str,))
    conn.commit()


def get_dashboard_stats(conn):
    """
    Obtiene las métricas clave para el panel principal (dashboard).
    """
    actualizar_estados_vencidos(conn)
    cursor = conn.cursor()

    # 1. Vehículos dentro actualmente
    cursor.execute("SELECT COUNT(*) AS total FROM movimientos WHERE estado = 'ACTIVO';")
    vehiculos_dentro = cursor.fetchone()["total"]

    # 2. Total de celdas y disponibles
    cursor.execute("SELECT COUNT(*) AS total FROM celdas WHERE activo = 1;")
    total_celdas = cursor.fetchone()["total"]

    cursor.execute("SELECT COUNT(*) AS total FROM celdas WHERE estado = 'DISPONIBLE' AND activo = 1;")
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
            c.id, c.codigo, c.tipo_permitido, c.estado, c.ubicacion, c.activo,
            m.id AS movimiento_id,
            m.fecha_entrada,
            v.placa, v.marca, v.modelo, v.color, v.tipo AS tipo_vehiculo,
            cli.nombre AS cliente_nombre, cli.telefono AS cliente_telefono
        FROM celdas c
        LEFT JOIN movimientos m ON m.celda_id = c.id AND m.estado = 'ACTIVO'
        LEFT JOIN vehiculos v ON v.id = m.vehiculo_id
        LEFT JOIN clientes cli ON cli.id = v.cliente_id
        WHERE c.activo = 1
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


def es_tipo_compatible(tipo_vehiculo, tipo_permitido_celda):
    """
    Verifica la compatibilidad entre el tipo de vehículo y el tipo permitido por la celda.
    - Celdas 'Cualquiera' o 'Cualquiera / Mixta': compatibles con todo tipo de vehículo.
    - Tipos idénticos siempre son compatibles.
    - Vehículos livianos de 4 ruedas ('Automóvil', 'Camioneta / SUV'): compatibles entre sí.
    - 'Motocicleta': solo compatible con celdas de 'Motocicleta' o 'Cualquiera'.
    """
    if not tipo_permitido_celda:
        return True
    t_cel = tipo_permitido_celda.strip().lower()
    if t_cel in ("cualquiera", "cualquiera / mixta", "mixta"):
        return True
    
    t_veh = (tipo_vehiculo or "").strip().lower()
    if t_veh == t_cel:
        return True
    
    es_4_ruedas_veh = any(k in t_veh for k in ("automóvil", "automovil", "camioneta", "suv"))
    es_4_ruedas_cel = any(k in t_cel for k in ("automóvil", "automovil", "camioneta", "suv"))
    if es_4_ruedas_veh and es_4_ruedas_cel:
        return True

    return False


def registrar_entrada(conn, vehiculo_id, celda_id, usuario_id=None, observaciones=""):
    """
    Registra el ingreso de un vehículo en una celda disponible.
    Aplica reglas de negocio:
    - El vehículo no puede tener ya una estancia activa.
    - La celda debe existir, estar activa y estar en estado DISPONIBLE.
    - El tipo de vehículo debe ser compatible con el tipo permitido por la celda.
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

    # Validar que la celda exista, esté activa y esté DISPONIBLE
    cursor.execute("SELECT id, codigo, tipo_permitido, estado, activo FROM celdas WHERE id = ?;", (celda_id,))
    celda = cursor.fetchone()
    if not celda:
        raise ValueError("La celda especificada no existe.")
    if not celda["activo"]:
        raise ValueError(f"La celda {celda['codigo']} está desactivada del sistema.")
    if celda["estado"] != "DISPONIBLE":
        raise ValueError(f"La celda {celda['codigo']} no está disponible (Estado actual: {celda['estado']}).")

    # Validar compatibilidad entre el tipo de vehículo y la celda
    if not es_tipo_compatible(vehiculo["tipo"], celda["tipo_permitido"]):
        raise ValueError(
            f"El tipo de vehículo '{vehiculo['tipo']}' no es compatible con la celda {celda['codigo']} (Tipo permitido: '{celda['tipo_permitido']}')."
        )

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
                          valor, fecha_pago, metodo_pago="Efectivo", referencia_pago="", estado="PAGADO", 
                          observaciones="", usuario_id=None):
    """
    Registra el pago de una mensualidad. Impide registrar pagos duplicados para el mismo vehículo y periodo.
    Valida campos obligatorios, valores numéricos positivos y coherencia de fechas.
    """
    cursor = conn.cursor()

    if not vehiculo_id or not cliente_id or not periodo or not fecha_inicio or not fecha_fin or not fecha_pago or not metodo_pago:
        raise ValueError("Todos los campos obligatorios del pago deben ser diligenciados.")

    if str(fecha_inicio) > str(fecha_fin):
        raise ValueError("La fecha de inicio del periodo no puede ser posterior a la fecha de fin.")

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
    except (TypeError, ValueError) as e:
        if "mayor a cero" in str(e):
            raise
        raise ValueError("El valor ingresado no es un número válido.")

    # Si se registra como pendiente pero la fecha_fin ya pasó, asignar a VENCIDO
    estado_final = estado
    if estado == "PENDIENTE" and str(fecha_fin) < date.today().strftime("%Y-%m-%d"):
        estado_final = "VENCIDO"

    cursor.execute("""
        INSERT INTO mensualidades 
        (vehiculo_id, cliente_id, periodo, fecha_inicio, fecha_fin, valor, fecha_pago, metodo_pago, referencia_pago, estado, observaciones, usuario_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
    """, (
        vehiculo_id, cliente_id, periodo, fecha_inicio, fecha_fin,
        valor_float, fecha_pago, metodo_pago, referencia_pago.strip() if referencia_pago else None,
        estado_final, observaciones.strip() if observaciones else None, usuario_id
    ))

    mensualidad_id = cursor.lastrowid
    conn.commit()
    return mensualidad_id


def get_resumen_financiero(conn, periodo=None, fecha_desde=None, fecha_hasta=None, cliente_id=None):
    """
    Calcula los indicadores financieros del parqueadero:
    - Total recaudado (pagos completados 'PAGADO')
    - Cantidad de pagos realizados
    - Mensualidades pendientes
    - Mensualidades vencidas
    - Total de transacciones
    """
    actualizar_estados_vencidos(conn)
    cursor = conn.cursor()

    sql_base = "FROM mensualidades m WHERE 1=1"
    params = []

    if periodo and periodo.strip():
        sql_base += " AND m.periodo = ?"
        params.append(periodo.strip())

    if fecha_desde and fecha_desde.strip():
        sql_base += " AND date(m.fecha_pago) >= date(?)"
        params.append(fecha_desde.strip())

    if fecha_hasta and fecha_hasta.strip():
        sql_base += " AND date(m.fecha_pago) <= date(?)"
        params.append(fecha_hasta.strip())

    if cliente_id:
        sql_base += " AND m.cliente_id = ?"
        params.append(cliente_id)

    # 1. Total Recaudado (estado = 'PAGADO')
    cursor.execute(f"SELECT COALESCE(SUM(m.valor), 0.0) AS total {sql_base} AND m.estado = 'PAGADO';", params)
    total_recaudado = cursor.fetchone()["total"]

    # 2. Cantidad de pagos realizados
    cursor.execute(f"SELECT COUNT(*) AS total {sql_base} AND m.estado = 'PAGADO';", params)
    cantidad_pagos = cursor.fetchone()["total"]

    # 3. Mensualidades pendientes
    cursor.execute(f"SELECT COUNT(*) AS total {sql_base} AND m.estado = 'PENDIENTE';", params)
    mensualidades_pendientes = cursor.fetchone()["total"]

    # 4. Mensualidades vencidas
    cursor.execute(f"SELECT COUNT(*) AS total {sql_base} AND m.estado = 'VENCIDO';", params)
    mensualidades_vencidas = cursor.fetchone()["total"]

    # 5. Total de transacciones
    cursor.execute(f"SELECT COUNT(*) AS total {sql_base};", params)
    total_transacciones = cursor.fetchone()["total"]

    return {
        "total_recaudado": total_recaudado,
        "cantidad_pagos": cantidad_pagos,
        "mensualidades_pendientes": mensualidades_pendientes,
        "mensualidades_vencidas": mensualidades_vencidas,
        "total_transacciones": total_transacciones
    }


def get_historial_pagos(conn, query=None, cliente_id=None, periodo=None, fecha_desde=None, fecha_hasta=None, estado=None, metodo_pago=None):
    """
    Consulta transacciones de mensualidades y pagos con filtros combinables.
    """
    actualizar_estados_vencidos(conn)
    cursor = conn.cursor()

    sql = """
        SELECT 
            m.*,
            v.placa, v.marca, v.modelo, v.color, v.tipo AS tipo_vehiculo,
            cli.id AS cliente_id, cli.nombre AS cliente_nombre, cli.documento AS cliente_documento,
            cli.tipo_documento AS cliente_tipo_documento, cli.telefono AS cliente_telefono,
            cli.email AS cliente_email, cli.direccion AS cliente_direccion,
            u.nombre AS usuario_nombre, u.username AS usuario_username
        FROM mensualidades m
        JOIN vehiculos v ON v.id = m.vehiculo_id
        JOIN clientes cli ON cli.id = m.cliente_id
        LEFT JOIN usuarios u ON u.id = m.usuario_id
        WHERE 1=1
    """
    params = []

    if query and query.strip():
        term = f"%{query.strip().upper()}%"
        term_raw = f"%{query.strip()}%"
        sql += """ AND (
            v.placa LIKE ? OR 
            UPPER(cli.nombre) LIKE ? OR 
            cli.documento LIKE ? OR 
            m.referencia_pago LIKE ?
        )"""
        params.extend([term, term, term_raw, term_raw])

    if cliente_id:
        sql += " AND m.cliente_id = ?"
        params.append(cliente_id)

    if periodo and periodo.strip():
        sql += " AND m.periodo = ?"
        params.append(periodo.strip())

    if fecha_desde and fecha_desde.strip():
        sql += " AND date(m.fecha_pago) >= date(?)"
        params.append(fecha_desde.strip())

    if fecha_hasta and fecha_hasta.strip():
        sql += " AND date(m.fecha_pago) <= date(?)"
        params.append(fecha_hasta.strip())

    if estado and estado.strip() and estado.upper() != "TODOS":
        sql += " AND m.estado = ?"
        params.append(estado.strip().upper())

    if metodo_pago and metodo_pago.strip() and metodo_pago.upper() != "TODOS":
        sql += " AND m.metodo_pago = ?"
        params.append(metodo_pago.strip())

    sql += " ORDER BY m.fecha_pago DESC, m.id DESC;"

    cursor.execute(sql, params)
    return cursor.fetchall()


def get_pago_por_id(conn, pago_id):
    """
    Obtiene los datos completos de una mensualidad/pago por su ID.
    """
    actualizar_estados_vencidos(conn)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT 
            m.*,
            v.placa, v.marca, v.modelo, v.color, v.tipo AS tipo_vehiculo,
            cli.id AS cliente_id, cli.nombre AS cliente_nombre, cli.documento AS cliente_documento,
            cli.tipo_documento AS cliente_tipo_documento, cli.telefono AS cliente_telefono,
            cli.email AS cliente_email, cli.direccion AS cliente_direccion,
            u.nombre AS usuario_nombre, u.username AS usuario_username
        FROM mensualidades m
        JOIN vehiculos v ON v.id = m.vehiculo_id
        JOIN clientes cli ON cli.id = m.cliente_id
        LEFT JOIN usuarios u ON u.id = m.usuario_id
        WHERE m.id = ?;
    """, (pago_id,))
    return cursor.fetchone()


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
