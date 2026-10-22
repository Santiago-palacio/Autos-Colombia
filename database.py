"""
database.py - Módulo de conexión y gestión de la base de datos SQLite para Autos Colombia.
"""

import os
import sqlite3
from datetime import datetime, date
from werkzeug.security import generate_password_hash

DEFAULT_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "autoscolombia.db")


def get_db_path():
    """Retorna la ruta del archivo de base de datos."""
    return os.environ.get("AUTOSCOLOMBIA_DB_PATH", DEFAULT_DB_PATH)


def get_db_connection(db_path=None):
    """
    Crea y retorna una conexión a la base de datos SQLite con claves foráneas habilitadas
    y row_factory configurado a sqlite3.Row.
    """
    path = db_path or get_db_path()
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def init_db(db_path=None):
    """
    Crea las tablas e índices necesarios si no existen, y ejecuta el semillero inicial
    únicamente si la base de datos está vacía.
    """
    conn = get_db_connection(db_path)
    cursor = conn.cursor()

    # 1. Tabla de Usuarios del sistema
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS usuarios (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nombre TEXT NOT NULL,
        username TEXT UNIQUE NOT NULL,
        email TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        rol TEXT NOT NULL DEFAULT 'operador',
        activo INTEGER NOT NULL DEFAULT 1,
        creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # 2. Tabla de Clientes
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS clientes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tipo_documento TEXT NOT NULL DEFAULT 'CC',
        documento TEXT UNIQUE NOT NULL,
        nombre TEXT NOT NULL,
        telefono TEXT NOT NULL,
        email TEXT,
        direccion TEXT,
        activo INTEGER NOT NULL DEFAULT 1,
        creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # 3. Tabla de Celdas de Parqueadero
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS celdas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        codigo TEXT UNIQUE NOT NULL,
        tipo_permitido TEXT NOT NULL,
        estado TEXT NOT NULL DEFAULT 'DISPONIBLE',
        ubicacion TEXT,
        creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # 4. Tabla de Vehículos
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS vehiculos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        placa TEXT UNIQUE NOT NULL,
        marca TEXT NOT NULL,
        modelo TEXT NOT NULL,
        color TEXT NOT NULL,
        tipo TEXT NOT NULL,
        cliente_id INTEGER NOT NULL REFERENCES clientes(id) ON DELETE RESTRICT,
        activo INTEGER NOT NULL DEFAULT 1,
        creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # 5. Tabla de Movimientos (Entradas y Salidas)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS movimientos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        vehiculo_id INTEGER NOT NULL REFERENCES vehiculos(id) ON DELETE RESTRICT,
        celda_id INTEGER NOT NULL REFERENCES celdas(id) ON DELETE RESTRICT,
        fecha_entrada TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        fecha_salida TIMESTAMP,
        usuario_id INTEGER REFERENCES usuarios(id),
        observaciones_entrada TEXT,
        observaciones_salida TEXT,
        estado TEXT NOT NULL DEFAULT 'ACTIVO'
    );
    """)

    # 6. Tabla de Mensualidades (Planes y Pagos)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS mensualidades (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        vehiculo_id INTEGER NOT NULL REFERENCES vehiculos(id) ON DELETE RESTRICT,
        cliente_id INTEGER NOT NULL REFERENCES clientes(id) ON DELETE RESTRICT,
        periodo TEXT NOT NULL,
        fecha_inicio DATE NOT NULL,
        fecha_fin DATE NOT NULL,
        valor REAL NOT NULL,
        fecha_pago DATE NOT NULL,
        metodo_pago TEXT NOT NULL,
        referencia_pago TEXT,
        estado TEXT NOT NULL DEFAULT 'PAGADO',
        observaciones TEXT,
        usuario_id INTEGER REFERENCES usuarios(id),
        creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(vehiculo_id, periodo)
    );
    """)

    # 7. Tabla de Novedades e Incidentes
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS novedades (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        vehiculo_id INTEGER REFERENCES vehiculos(id) ON DELETE SET NULL,
        tipo TEXT NOT NULL,
        descripcion TEXT NOT NULL,
        usuario_id INTEGER REFERENCES usuarios(id),
        estado TEXT NOT NULL DEFAULT 'ABIERTO',
        fecha TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        solucion_notas TEXT,
        creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # Índices para optimizar consultas frecuentes
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_clientes_documento ON clientes(documento);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_vehiculos_placa ON vehiculos(placa);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_celdas_codigo ON celdas(codigo);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_celdas_estado ON celdas(estado);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_movimientos_estado ON movimientos(estado);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_movimientos_vehiculo ON movimientos(vehiculo_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_movimientos_celda ON movimientos(celda_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_mensualidades_periodo ON mensualidades(periodo);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_mensualidades_vehiculo ON mensualidades(vehiculo_id);")

    conn.commit()

    # Sembrar datos de demostración si la base de datos está vacía
    cursor.execute("SELECT COUNT(*) AS total FROM usuarios;")
    count_users = cursor.fetchone()["total"]

    if count_users == 0:
        seed_demo_data(conn)

    conn.close()


def seed_demo_data(conn):
    """
    Inserta datos iniciales de demostración solo cuando la base de datos está recién creada.
    """
    cursor = conn.cursor()

    # 1. Usuarios iniciales (admin y operador)
    admin_pw = generate_password_hash("admin123")
    oper_pw = generate_password_hash("operador123")

    cursor.execute("""
        INSERT INTO usuarios (nombre, username, email, password_hash, rol, activo)
        VALUES 
        ('Administrador Autos Colombia', 'admin', 'admin@autoscolombia.com', ?, 'admin', 1),
        ('Carlos Mario Gómez (Operador)', 'operador', 'operador@autoscolombia.com', ?, 'operador', 1);
    """, (admin_pw, oper_pw))

    admin_id = 1

    # 2. Celdas de parqueadero
    # Automóviles y Camionetas
    celdas_autos = [
        ('A-01', 'Automóvil', 'Piso 1 - Bahía Norte'),
        ('A-02', 'Automóvil', 'Piso 1 - Bahía Norte'),
        ('A-03', 'Automóvil', 'Piso 1 - Bahía Norte'),
        ('A-04', 'Automóvil', 'Piso 1 - Bahía Central'),
        ('A-05', 'Automóvil', 'Piso 1 - Bahía Central'),
        ('A-06', 'Automóvil', 'Piso 1 - Bahía Sur'),
        ('A-07', 'Automóvil', 'Piso 1 - Bahía Sur'),
        ('A-08', 'Automóvil', 'Piso 1 - Bahía Sur'),
        ('C-01', 'Camioneta / SUV', 'Piso 1 - Bahía Especial'),
        ('C-02', 'Camioneta / SUV', 'Piso 1 - Bahía Especial'),
    ]
    # Motocicletas
    celdas_motos = [
        ('M-01', 'Motocicleta', 'Zona Motos - Lateral'),
        ('M-02', 'Motocicleta', 'Zona Motos - Lateral'),
        ('M-03', 'Motocicleta', 'Zona Motos - Lateral'),
        ('M-04', 'Motocicleta', 'Zona Motos - Entrada'),
        ('M-05', 'Motocicleta', 'Zona Motos - Entrada'),
        ('M-06', 'Motocicleta', 'Zona Motos - Entrada'),
    ]

    for codigo, tipo, ubicacion in celdas_autos + celdas_motos:
        cursor.execute("""
            INSERT INTO celdas (codigo, tipo_permitido, estado, ubicacion)
            VALUES (?, ?, 'DISPONIBLE', ?);
        """, (codigo, tipo, ubicacion))

    # 3. Clientes
    clientes_data = [
        ('CC', '1020304050', 'Alejandro Morales Restrepo', '3104509821', 'alejandro.morales@gmail.com', 'Calle 45 # 14-32, Bogotá'),
        ('CC', '52890123', 'Claudia Patricia Herrera', '3157894512', 'claudia.herrera@hotmail.com', 'Cra 15 # 85-20 Apt 402, Bogotá'),
        ('CC', '1098765432', 'David Fernando Rojas', '3006543210', 'david.rojas92@gmail.com', 'Av. Suba # 112-40, Bogotá'),
        ('NIT', '900854120-1', 'Inversiones & Logística Andina SAS', '6013456789', 'contacto@logisticaandina.com.co', 'Cra 7 # 71-52 Of. 801, Bogotá')
    ]

    for tipo_doc, doc, nom, tel, em, dir_c in clientes_data:
        cursor.execute("""
            INSERT INTO clientes (tipo_documento, documento, nombre, telefono, email, direccion, activo)
            VALUES (?, ?, ?, ?, ?, ?, 1);
        """, (tipo_doc, doc, nom, tel, em, dir_c))

    # 4. Vehículos
    vehiculos_data = [
        ('KGT482', 'Mazda', 'Mazda 3 Grand Touring 2022', 'Rojo Diamante', 'Automóvil', 1),
        ('JMQ190', 'Renault', 'Duster Intens 4x4 2023', 'Blanco Glaciar', 'Camioneta / SUV', 2),
        ('DXB34F', 'Yamaha', 'NMAX 155 Connected 2024', 'Negro Mate', 'Motocicleta', 3),
        ('WLY821', 'Chevrolet', 'Onix Sedan Turbo 2021', 'Gris Platino', 'Automóvil', 4)
    ]

    for placa, marca, mod, col, tip, cli_id in vehiculos_data:
        cursor.execute("""
            INSERT INTO vehiculos (placa, marca, modelo, color, tipo, cliente_id, activo)
            VALUES (?, ?, ?, ?, ?, ?, 1);
        """, (placa, marca, mod, col, tip, cli_id))

    # 5. Mensualidades
    # Periodo actual
    ahora = datetime.now()
    periodo_actual = ahora.strftime("%Y-%m")
    primer_dia_mes = date(ahora.year, ahora.month, 1).strftime("%Y-%m-%d")
    # Fin del mes (aproximado a 30 días)
    if ahora.month == 12:
        ultimo_dia_mes = date(ahora.year, 12, 31).strftime("%Y-%m-%d")
    else:
        # Siguiente mes día 1 menos 1 día
        from datetime import timedelta
        siguiente = date(ahora.year, ahora.month + 1, 1) - timedelta(days=1)
        ultimo_dia_mes = siguiente.strftime("%Y-%m-%d")

    # Pago 1: KGT482 al día
    cursor.execute("""
        INSERT INTO mensualidades 
        (vehiculo_id, cliente_id, periodo, fecha_inicio, fecha_fin, valor, fecha_pago, metodo_pago, referencia_pago, estado, observaciones, usuario_id)
        VALUES (1, 1, ?, ?, ?, 180000.0, ?, 'Transferencia Bancolombia', 'TRF-982143', 'PAGADO', 'Pago mensualidad completa', ?);
    """, (periodo_actual, primer_dia_mes, ultimo_dia_mes, ahora.strftime("%Y-%m-%d"), admin_id))

    # Pago 2: DXB34F al día (Moto)
    cursor.execute("""
        INSERT INTO mensualidades 
        (vehiculo_id, cliente_id, periodo, fecha_inicio, fecha_fin, valor, fecha_pago, metodo_pago, referencia_pago, estado, observaciones, usuario_id)
        VALUES (3, 3, ?, ?, ?, 90000.0, ?, 'Nequi / Daviplata', 'NEQ-445102', 'PAGADO', 'Mensualidad motocicleta', ?);
    """, (periodo_actual, primer_dia_mes, ultimo_dia_mes, ahora.strftime("%Y-%m-%d"), admin_id))

    # 6. Movimientos iniciales
    # KGT482 está estacionado en A-01
    cursor.execute("""
        INSERT INTO movimientos (vehiculo_id, celda_id, fecha_entrada, usuario_id, observaciones_entrada, estado)
        VALUES (1, 1, datetime('now', '-3 hours'), ?, 'Vehículo ingresa limpio, sin novedades visibles', 'ACTIVO');
    """, (admin_id,))
    cursor.execute("UPDATE celdas SET estado = 'OCUPADA' WHERE id = 1;")

    # DXB34F está estacionado en M-01
    cursor.execute("""
        INSERT INTO movimientos (vehiculo_id, celda_id, fecha_entrada, usuario_id, observaciones_entrada, estado)
        VALUES (3, 11, datetime('now', '-1 hours'), ?, 'Ingresa con casco y chaleco en compartimiento', 'ACTIVO');
    """, (admin_id,))
    cursor.execute("UPDATE celdas SET estado = 'OCUPADA' WHERE id = 11;")

    # Histórico de salida previa para JMQ190 en C-01
    cursor.execute("""
        INSERT INTO movimientos 
        (vehiculo_id, celda_id, fecha_entrada, fecha_salida, usuario_id, observaciones_entrada, observaciones_salida, estado)
        VALUES (2, 9, datetime('now', '-2 days'), datetime('now', '-1 days', '-5 hours'), ?, 'Entrada normal', 'Salida sin contratiempos', 'FINALIZADO');
    """, (admin_id,))

    # 7. Novedad de demostración
    cursor.execute("""
        INSERT INTO novedades (vehiculo_id, tipo, descripcion, usuario_id, estado, fecha, solucion_notas)
        VALUES (
            1, 
            'Golpe / Rayón previo', 
            'Pequeño rayón superficial en el guardabarros trasero derecho detectado en la inspección visual.', 
            ?, 
            'ABIERTO', 
            datetime('now', '-3 hours'),
            NULL
        );
    """, (admin_id,))

    conn.commit()
