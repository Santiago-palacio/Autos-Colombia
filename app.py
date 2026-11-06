"""
app.py - Servidor web principal Flask para el sistema Autos Colombia.
"""

import os
import secrets
from functools import wraps
from datetime import datetime, date
from flask import (
    Flask, render_template, request, redirect, url_for, flash, session, jsonify, g
)
from werkzeug.security import check_password_hash, generate_password_hash

from database import get_db_connection, init_db
import services

app = Flask(__name__)
app.secret_key = os.environ.get("AUTOSCOLOMBIA_SECRET_KEY", "autos-colombia-secret-key-2026-prod")

# Configuración de seguridad de cookies de sesión
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=False  # Permite pruebas locales sobre HTTP
)

# Inicializar la base de datos al arrancar
with app.app_context():
    init_db()


# ---------------------------------------------------------
# Protección CSRF (Cross-Site Request Forgery)
# ---------------------------------------------------------
def get_csrf_token():
    """Genera u obtiene el token CSRF vinculado a la sesión actual."""
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_hex(32)
    return session["csrf_token"]


app.jinja_env.globals["csrf_token"] = get_csrf_token


@app.before_request
def check_csrf():
    """Valida el token CSRF en peticiones con métodos de modificación (POST, PUT, DELETE, PATCH)."""
    if request.method in ("POST", "PUT", "DELETE", "PATCH"):
        # Exención automática en entorno de pruebas unitarias/automatizadas
        if app.config.get("TESTING") or app.config.get("WTF_CSRF_ENABLED") is False:
            return

        token = request.form.get("csrf_token") or request.headers.get("X-CSRFToken")
        session_token = session.get("csrf_token")

        if not session_token or not token or not secrets.compare_digest(session_token, token):
            flash("Solicitud no válida o sesión expirada (token CSRF ausente o incorrecto).", "danger")
            return render_template("403.html"), 403


# ---------------------------------------------------------
# Filtros personalizados para Jinja2
# ---------------------------------------------------------
@app.template_filter("currency_cop")
def currency_cop(val):
    """Formatea valores monetarios en pesos colombianos, ej: $ 180.000"""
    try:
        val_float = float(val)
        return f"${val_float:,.0f}".replace(",", ".")
    except (ValueError, TypeError):
        return "$0"


@app.template_filter("format_datetime")
def format_datetime_filter(dt_str):
    """Formatea fechas y horas para visualización amigable en español."""
    if not dt_str:
        return "-"
    try:
        # Maneja tanto 'YYYY-MM-DD HH:MM:SS' como ISO
        cleaned = str(dt_str).replace("T", " ").split(".")[0]
        dt = datetime.strptime(cleaned, "%Y-%m-%d %H:%M:%S")
        meses = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]
        mes_txt = meses[dt.month - 1]
        hora_12 = dt.strftime("%I:%M %p").lower()
        return f"{dt.day:02d} {mes_txt} {dt.year}, {hora_12}"
    except Exception:
        return str(dt_str)


@app.template_filter("format_date")
def format_date_filter(d_str):
    """Formatea fechas YYYY-MM-DD a DD/MM/YYYY"""
    if not d_str:
        return "-"
    try:
        dt = datetime.strptime(str(d_str)[:10], "%Y-%m-%d")
        return dt.strftime("%d/%m/%Y")
    except Exception:
        return str(d_str)


# ---------------------------------------------------------
# Conexión por petición y decoradores de autenticación y roles
# ---------------------------------------------------------
def get_db():
    if "db" not in g:
        g.db = get_db_connection()
    return g.db


@app.teardown_appcontext
def close_db(error):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_id" not in session:
            flash("Debe iniciar sesión para acceder a esta sección.", "warning")
            return redirect(url_for("login", next=request.url))
        return f(*args, **kwargs)
    return decorated_function


def admin_required(f):
    """Decorador de control de acceso por rol: Restringe el acceso exclusivamente a administradores."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_id" not in session:
            flash("Debe iniciar sesión para acceder a esta sección.", "warning")
            return redirect(url_for("login", next=request.url))
        if session.get("user_role") != "admin":
            flash("Acceso denegado: Se requieren permisos de administrador para realizar esta acción.", "danger")
            return render_template("403.html"), 403
        return f(*args, **kwargs)
    return decorated_function


@app.context_processor
def inject_global_context():
    """Inyecta el usuario actual y la fecha de hoy a todas las plantillas."""
    return {
        "current_user": session.get("user_name"),
        "current_user_id": session.get("user_id"),
        "current_user_role": session.get("user_role"),
        "today_str": date.today().strftime("%Y-%m-%d"),
        "current_period": datetime.now().strftime("%Y-%m")
    }


# ---------------------------------------------------------
# Rutas de Autenticación
# ---------------------------------------------------------
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()

        if not username or not password:
            flash("Por favor ingrese su usuario y contraseña.", "danger")
            return render_template("login.html")

        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM usuarios WHERE username = ?;", (username,))
        user = cursor.fetchone()

        if user:
            if not user["activo"]:
                flash("Su cuenta de usuario se encuentra inactiva. Comuníquese con el administrador.", "danger")
                return render_template("login.html")

            if check_password_hash(user["password_hash"], password):
                session.clear()
                session["user_id"] = user["id"]
                session["user_name"] = user["nombre"]
                session["user_role"] = user["rol"]
                session["csrf_token"] = secrets.token_hex(32)
                flash(f"¡Bienvenido de nuevo, {user['nombre']}!", "success")
                next_url = request.args.get("next")
                if next_url and next_url.startswith("/") and not next_url.startswith("//"):
                    return redirect(next_url)
                return redirect(url_for("dashboard"))

        flash("Credenciales incorrectas o usuario inactivo.", "danger")

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("Ha cerrado su sesión de forma segura.", "info")
    return redirect(url_for("login"))


# ---------------------------------------------------------
# 1. Panel Principal (Dashboard)
# ---------------------------------------------------------
@app.route("/")
@login_required
def dashboard():
    conn = get_db()
    stats = services.get_dashboard_stats(conn)

    # Listas auxiliares para modales de acción rápida
    cursor = conn.cursor()
    cursor.execute("""
        SELECT v.id, v.placa, v.marca, v.modelo, v.tipo, cli.nombre AS cliente_nombre
        FROM vehiculos v
        JOIN clientes cli ON cli.id = v.cliente_id
        WHERE v.activo = 1
        AND v.id NOT IN (SELECT vehiculo_id FROM movimientos WHERE estado = 'ACTIVO')
        ORDER BY v.placa ASC;
    """)
    vehiculos_disponibles_ingreso = cursor.fetchall()

    cursor.execute("""
        SELECT id, codigo, tipo_permitido, ubicacion
        FROM celdas
        WHERE estado = 'DISPONIBLE' AND activo = 1
        ORDER BY codigo ASC;
    """)
    celdas_disponibles_ingreso = cursor.fetchall()

    return render_template(
        "dashboard.html",
        stats=stats,
        vehiculos_disponibles=vehiculos_disponibles_ingreso,
        celdas_disponibles=celdas_disponibles_ingreso
    )


# ---------------------------------------------------------
# 2. Gestión de Clientes
# ---------------------------------------------------------
@app.route("/clientes")
@login_required
def clientes_index():
    query = request.args.get("q", "").strip()
    conn = get_db()
    cursor = conn.cursor()

    if query:
        search = f"%{query}%"
        cursor.execute("""
            SELECT c.*, COUNT(v.id) AS total_vehiculos
            FROM clientes c
            LEFT JOIN vehiculos v ON v.cliente_id = c.id
            WHERE c.nombre LIKE ? OR c.documento LIKE ? OR c.telefono LIKE ?
            GROUP BY c.id
            ORDER BY c.nombre ASC;
        """, (search, search, search))
    else:
        cursor.execute("""
            SELECT c.*, COUNT(v.id) AS total_vehiculos
            FROM clientes c
            LEFT JOIN vehiculos v ON v.cliente_id = c.id
            GROUP BY c.id
            ORDER BY c.nombre ASC;
        """)
    clientes = cursor.fetchall()

    return render_template("clientes/index.html", clientes=clientes, query=query)


@app.route("/clientes/nuevo", methods=["GET", "POST"])
@login_required
def clientes_nuevo():
    if request.method == "POST":
        tipo_documento = request.form.get("tipo_documento", "CC").strip()
        documento = request.form.get("documento", "").strip()
        nombre = request.form.get("nombre", "").strip()
        telefono = request.form.get("telefono", "").strip()
        email = request.form.get("email", "").strip()
        direccion = request.form.get("direccion", "").strip()

        # Validaciones de servidor
        if not documento or not nombre or not telefono:
            flash("Documento, nombre completo y teléfono son obligatorios.", "danger")
            return render_template("clientes/form.html", cliente=request.form, es_nuevo=True)

        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM clientes WHERE documento = ?;", (documento,))
        if cursor.fetchone():
            flash(f"Ya existe un cliente registrado con el documento {documento}.", "danger")
            return render_template("clientes/form.html", cliente=request.form, es_nuevo=True)

        cursor.execute("""
            INSERT INTO clientes (tipo_documento, documento, nombre, telefono, email, direccion, activo)
            VALUES (?, ?, ?, ?, ?, ?, 1);
        """, (tipo_documento, documento, nombre, telefono, email or None, direccion or None))
        conn.commit()

        flash(f"Cliente '{nombre}' registrado exitosamente.", "success")
        return redirect(url_for("clientes_index"))

    return render_template("clientes/form.html", cliente={}, es_nuevo=True)


@app.route("/clientes/<int:cliente_id>/editar", methods=["GET", "POST"])
@login_required
def clientes_editar(cliente_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM clientes WHERE id = ?;", (cliente_id,))
    cliente = cursor.fetchone()

    if not cliente:
        flash("Cliente no encontrado.", "danger")
        return redirect(url_for("clientes_index"))

    if request.method == "POST":
        tipo_documento = request.form.get("tipo_documento", "CC").strip()
        documento = request.form.get("documento", "").strip()
        nombre = request.form.get("nombre", "").strip()
        telefono = request.form.get("telefono", "").strip()
        email = request.form.get("email", "").strip()
        direccion = request.form.get("direccion", "").strip()

        if not documento or not nombre or not telefono:
            flash("Documento, nombre y teléfono son obligatorios.", "danger")
            return render_template("clientes/form.html", cliente=request.form, es_nuevo=False, cliente_id=cliente_id)

        # Verificar unicidad de documento excluyendo el cliente actual
        cursor.execute("SELECT id FROM clientes WHERE documento = ? AND id != ?;", (documento, cliente_id))
        if cursor.fetchone():
            flash(f"Ya existe otro cliente con el documento {documento}.", "danger")
            return render_template("clientes/form.html", cliente=request.form, es_nuevo=False, cliente_id=cliente_id)

        cursor.execute("""
            UPDATE clientes
            SET tipo_documento = ?, documento = ?, nombre = ?, telefono = ?, email = ?, direccion = ?
            WHERE id = ?;
        """, (tipo_documento, documento, nombre, telefono, email or None, direccion or None, cliente_id))
        conn.commit()

        flash(f"Datos de '{nombre}' actualizados correctamente.", "success")
        return redirect(url_for("clientes_index"))

    return render_template("clientes/form.html", cliente=cliente, es_nuevo=False, cliente_id=cliente_id)


@app.route("/clientes/<int:cliente_id>/toggle", methods=["POST"])
@login_required
def clientes_toggle(cliente_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, nombre, activo FROM clientes WHERE id = ?;", (cliente_id,))
    cliente = cursor.fetchone()
    if not cliente:
        flash("Cliente no encontrado.", "danger")
        return redirect(url_for("clientes_index"))

    nuevo_estado = 0 if cliente["activo"] == 1 else 1
    cursor.execute("UPDATE clientes SET activo = ? WHERE id = ?;", (nuevo_estado, cliente_id))
    conn.commit()

    accion = "activado" if nuevo_estado == 1 else "desactivado"
    flash(f"Cliente '{cliente['nombre']}' {accion} con éxito.", "info")
    return redirect(url_for("clientes_index"))


# ---------------------------------------------------------
# 3. Gestión de Vehículos
# ---------------------------------------------------------
@app.route("/vehiculos")
@login_required
def vehiculos_index():
    query = request.args.get("q", "").strip()
    tipo = request.args.get("tipo", "").strip()
    conn = get_db()
    cursor = conn.cursor()

    sql = """
        SELECT 
            v.*, cli.nombre AS cliente_nombre, cli.documento AS cliente_documento,
            (SELECT m.id FROM movimientos m WHERE m.vehiculo_id = v.id AND m.estado = 'ACTIVO') AS movimiento_activo_id,
            (SELECT c.codigo FROM movimientos m JOIN celdas c ON c.id = m.celda_id WHERE m.vehiculo_id = v.id AND m.estado = 'ACTIVO') AS celda_actual
        FROM vehiculos v
        JOIN clientes cli ON cli.id = v.cliente_id
        WHERE 1=1
    """
    params = []

    if query:
        sql += " AND (v.placa LIKE ? OR v.marca LIKE ? OR v.modelo LIKE ? OR cli.nombre LIKE ?)"
        term = f"%{query}%"
        params.extend([term, term, term, term])

    if tipo and tipo != "TODOS":
        sql += " AND v.tipo = ?"
        params.append(tipo)

    sql += " ORDER BY v.placa ASC;"

    cursor.execute(sql, params)
    vehiculos = cursor.fetchall()

    return render_template("vehiculos/index.html", vehiculos=vehiculos, query=query, tipo_seleccionado=tipo)


@app.route("/vehiculos/nuevo", methods=["GET", "POST"])
@login_required
def vehiculos_nuevo():
    conn = get_db()
    cursor = conn.cursor()

    if request.method == "POST":
        placa = request.form.get("placa", "").strip().upper()
        marca = request.form.get("marca", "").strip()
        modelo = request.form.get("modelo", "").strip()
        color = request.form.get("color", "").strip()
        tipo = request.form.get("tipo", "").strip()
        cliente_id = request.form.get("cliente_id", "").strip()

        cursor.execute("SELECT id, nombre FROM clientes WHERE activo = 1 ORDER BY nombre ASC;")
        clientes = cursor.fetchall()

        if not placa or not marca or not modelo or not color or not tipo or not cliente_id:
            flash("Todos los campos marcados con asterisco son obligatorios.", "danger")
            return render_template("vehiculos/form.html", vehiculo=request.form, clientes=clientes, es_nuevo=True)

        # Validar placa única
        cursor.execute("SELECT id FROM vehiculos WHERE placa = ?;", (placa,))
        if cursor.fetchone():
            flash(f"La placa {placa} ya se encuentra registrada en el sistema.", "danger")
            return render_template("vehiculos/form.html", vehiculo=request.form, clientes=clientes, es_nuevo=True)

        cursor.execute("""
            INSERT INTO vehiculos (placa, marca, modelo, color, tipo, cliente_id, activo)
            VALUES (?, ?, ?, ?, ?, ?, 1);
        """, (placa, marca, modelo, color, tipo, cliente_id))
        conn.commit()

        flash(f"Vehículo con placa {placa} registrado correctamente.", "success")
        return redirect(url_for("vehiculos_index"))

    cursor.execute("SELECT id, nombre, documento FROM clientes WHERE activo = 1 ORDER BY nombre ASC;")
    clientes = cursor.fetchall()
    return render_template("vehiculos/form.html", vehiculo={}, clientes=clientes, es_nuevo=True)


@app.route("/vehiculos/<int:vehiculo_id>/editar", methods=["GET", "POST"])
@login_required
def vehiculos_editar(vehiculo_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM vehiculos WHERE id = ?;", (vehiculo_id,))
    vehiculo = cursor.fetchone()

    if not vehiculo:
        flash("Vehículo no encontrado.", "danger")
        return redirect(url_for("vehiculos_index"))

    cursor.execute("SELECT id, nombre, documento FROM clientes WHERE activo = 1 ORDER BY nombre ASC;")
    clientes = cursor.fetchall()

    if request.method == "POST":
        placa = request.form.get("placa", "").strip().upper()
        marca = request.form.get("marca", "").strip()
        modelo = request.form.get("modelo", "").strip()
        color = request.form.get("color", "").strip()
        tipo = request.form.get("tipo", "").strip()
        cliente_id = request.form.get("cliente_id", "").strip()

        if not placa or not marca or not modelo or not color or not tipo or not cliente_id:
            flash("Todos los campos marcados son obligatorios.", "danger")
            return render_template("vehiculos/form.html", vehiculo=request.form, clientes=clientes, es_nuevo=False, vehiculo_id=vehiculo_id)

        # Validar placa única excluyendo el actual
        cursor.execute("SELECT id FROM vehiculos WHERE placa = ? AND id != ?;", (placa, vehiculo_id))
        if cursor.fetchone():
            flash(f"La placa {placa} ya está registrada para otro vehículo.", "danger")
            return render_template("vehiculos/form.html", vehiculo=request.form, clientes=clientes, es_nuevo=False, vehiculo_id=vehiculo_id)

        cursor.execute("""
            UPDATE vehiculos
            SET placa = ?, marca = ?, modelo = ?, color = ?, tipo = ?, cliente_id = ?
            WHERE id = ?;
        """, (placa, marca, modelo, color, tipo, cliente_id, vehiculo_id))
        conn.commit()

        flash(f"Vehículo {placa} actualizado satisfactoriamente.", "success")
        return redirect(url_for("vehiculos_index"))

    return render_template("vehiculos/form.html", vehiculo=vehiculo, clientes=clientes, es_nuevo=False, vehiculo_id=vehiculo_id)


@app.route("/vehiculos/<int:vehiculo_id>/toggle", methods=["POST"])
@login_required
def vehiculos_toggle(vehiculo_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, placa, activo FROM vehiculos WHERE id = ?;", (vehiculo_id,))
    vehiculo = cursor.fetchone()

    if not vehiculo:
        flash("Vehículo no encontrado.", "danger")
        return redirect(url_for("vehiculos_index"))

    # Si se va a desactivar, revisar si está actualmente dentro
    if vehiculo["activo"] == 1:
        cursor.execute("SELECT id FROM movimientos WHERE vehiculo_id = ? AND estado = 'ACTIVO';", (vehiculo_id,))
        if cursor.fetchone():
            flash(f"No se puede desactivar el vehículo {vehiculo['placa']} porque está actualmente dentro del parqueadero.", "danger")
            return redirect(url_for("vehiculos_index"))

    nuevo_estado = 0 if vehiculo["activo"] == 1 else 1
    cursor.execute("UPDATE vehiculos SET activo = ? WHERE id = ?;", (nuevo_estado, vehiculo_id))
    conn.commit()

    accion = "activado" if nuevo_estado == 1 else "desactivado"
    flash(f"Vehículo {vehiculo['placa']} {accion} correctamente.", "info")
    return redirect(url_for("vehiculos_index"))


# ---------------------------------------------------------
# 4. Gestión de Celdas
# ---------------------------------------------------------
@app.route("/celdas")
@login_required
def celdas_index():
    filtro_estado = request.args.get("filtro", "TODOS").strip().upper()
    conn = get_db()
    cursor = conn.cursor()

    sql = """
        SELECT 
            c.*,
            m.id AS movimiento_id,
            m.fecha_entrada,
            v.placa, v.tipo AS tipo_vehiculo,
            cli.nombre AS cliente_nombre
        FROM celdas c
        LEFT JOIN movimientos m ON m.celda_id = c.id AND m.estado = 'ACTIVO'
        LEFT JOIN vehiculos v ON v.id = m.vehiculo_id
        LEFT JOIN clientes cli ON cli.id = v.cliente_id
        WHERE 1=1
    """
    params = []
    if filtro_estado == "ACTIVAS":
        sql += " AND c.activo = 1"
    elif filtro_estado == "INACTIVAS":
        sql += " AND c.activo = 0"
    elif filtro_estado == "DISPONIBLES":
        sql += " AND c.estado = 'DISPONIBLE' AND c.activo = 1"

    sql += " ORDER BY c.activo DESC, c.tipo_permitido ASC, c.codigo ASC;"
    cursor.execute(sql, params)
    celdas = cursor.fetchall()

    return render_template("celdas/index.html", celdas=celdas, filtro_seleccionado=filtro_estado)


@app.route("/celdas/nueva", methods=["POST"])
@login_required
def celdas_nueva():
    codigo = request.form.get("codigo", "").strip().upper()
    tipo_permitido = request.form.get("tipo_permitido", "Automóvil").strip()
    ubicacion = request.form.get("ubicacion", "").strip()

    if not codigo:
        flash("El código identificador de la celda es obligatorio.", "danger")
        return redirect(url_for("celdas_index"))

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM celdas WHERE codigo = ?;", (codigo,))
    if cursor.fetchone():
        flash(f"Ya existe una celda registrada con el código {codigo}.", "danger")
        return redirect(url_for("celdas_index"))

    cursor.execute("""
        INSERT INTO celdas (codigo, tipo_permitido, estado, ubicacion, activo)
        VALUES (?, ?, 'DISPONIBLE', ?, 1);
    """, (codigo, tipo_permitido, ubicacion or None))
    conn.commit()

    flash(f"Celda {codigo} creada con éxito.", "success")
    return redirect(url_for("celdas_index"))


@app.route("/celdas/<int:celda_id>/editar", methods=["GET", "POST"])
@login_required
def celdas_editar(celda_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM celdas WHERE id = ?;", (celda_id,))
    celda = cursor.fetchone()

    if not celda:
        flash("Celda no encontrada.", "danger")
        return redirect(url_for("celdas_index"))

    if request.method == "POST":
        codigo = request.form.get("codigo", "").strip().upper()
        tipo_permitido = request.form.get("tipo_permitido", "").strip()
        ubicacion = request.form.get("ubicacion", "").strip()

        if not codigo or not tipo_permitido:
            flash("El código identificador y el tipo de vehículo permitido son obligatorios.", "danger")
            return render_template("celdas/form.html", celda=request.form, celda_id=celda_id)

        # Validar que no se registre dos veces el mismo código de celda
        cursor.execute("SELECT id FROM celdas WHERE codigo = ? AND id != ?;", (codigo, celda_id))
        if cursor.fetchone():
            flash(f"Ya existe otra celda con el código {codigo}.", "danger")
            return render_template("celdas/form.html", celda=request.form, celda_id=celda_id)

        cursor.execute("""
            UPDATE celdas
            SET codigo = ?, tipo_permitido = ?, ubicacion = ?
            WHERE id = ?;
        """, (codigo, tipo_permitido, ubicacion or None, celda_id))
        conn.commit()

        flash(f"Celda {codigo} actualizada satisfactoriamente.", "success")
        return redirect(url_for("celdas_index"))

    return render_template("celdas/form.html", celda=celda, celda_id=celda_id)


@app.route("/celdas/<int:celda_id>/estado", methods=["POST"])
@login_required
def celdas_cambiar_estado(celda_id):
    nuevo_estado = request.form.get("nuevo_estado", "").strip()
    if nuevo_estado not in ("DISPONIBLE", "MANTENIMIENTO"):
        flash("Estado de celda no válido.", "danger")
        return redirect(url_for("celdas_index"))

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, codigo, estado, activo FROM celdas WHERE id = ?;", (celda_id,))
    celda = cursor.fetchone()

    if not celda:
        flash("Celda no encontrada.", "danger")
        return redirect(url_for("celdas_index"))

    if not celda["activo"]:
        flash(f"No se puede cambiar el estado de la celda {celda['codigo']} porque está desactivada.", "danger")
        return redirect(url_for("celdas_index"))

    # No se puede pasar a mantenimiento si está ocupada
    if celda["estado"] == "OCUPADA":
        flash(f"No se puede colocar en mantenimiento la celda {celda['codigo']} porque está ocupada. Registre primero la salida del vehículo.", "danger")
        return redirect(url_for("celdas_index"))

    cursor.execute("UPDATE celdas SET estado = ? WHERE id = ?;", (nuevo_estado, celda_id))
    conn.commit()

    flash(f"La celda {celda['codigo']} ahora está en estado '{nuevo_estado}'.", "info")
    return redirect(url_for("celdas_index"))


@app.route("/celdas/<int:celda_id>/toggle", methods=["POST"])
@login_required
def celdas_toggle(celda_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, codigo, estado, activo FROM celdas WHERE id = ?;", (celda_id,))
    celda = cursor.fetchone()

    if not celda:
        flash("Celda no encontrada.", "danger")
        return redirect(url_for("celdas_index"))

    # Regla: No permitir desactivar una celda que esté ocupada
    if celda["activo"] == 1 and celda["estado"] == "OCUPADA":
        flash(f"No se puede desactivar la celda {celda['codigo']} porque está actualmente ocupada. Registre primero la salida del vehículo.", "danger")
        return redirect(url_for("celdas_index"))

    nuevo_estado = 0 if celda["activo"] == 1 else 1
    cursor.execute("UPDATE celdas SET activo = ? WHERE id = ?;", (nuevo_estado, celda_id))
    conn.commit()

    accion = "activada" if nuevo_estado == 1 else "desactivada"
    flash(f"Celda {celda['codigo']} {accion} correctamente.", "info")
    return redirect(url_for("celdas_index"))


# ---------------------------------------------------------
# 5. Entradas, Salidas y Control de Ocupación
# ---------------------------------------------------------
@app.route("/movimientos")
@login_required
def movimientos_index():
    conn = get_db()
    cursor = conn.cursor()

    # Vehículos actualmente estacionados (movimientos activos)
    cursor.execute("""
        SELECT 
            m.id, m.fecha_entrada, m.observaciones_entrada,
            v.id AS vehiculo_id, v.placa, v.marca, v.modelo, v.color, v.tipo AS tipo_vehiculo,
            c.id AS celda_id, c.codigo AS codigo_celda, c.ubicacion AS celda_ubicacion,
            cli.nombre AS cliente_nombre, cli.telefono AS cliente_telefono,
            u.nombre AS usuario_nombre
        FROM movimientos m
        JOIN vehiculos v ON v.id = m.vehiculo_id
        JOIN celdas c ON c.id = m.celda_id
        JOIN clientes cli ON cli.id = v.cliente_id
        LEFT JOIN usuarios u ON u.id = m.usuario_id
        WHERE m.estado = 'ACTIVO'
        ORDER BY m.fecha_entrada DESC;
    """)
    movimientos_activos = cursor.fetchall()

    # Vehículos disponibles para ingresar (que no estén dentro y estén activos)
    cursor.execute("""
        SELECT v.id, v.placa, v.marca, v.modelo, v.tipo, cli.nombre AS cliente_nombre
        FROM vehiculos v
        JOIN clientes cli ON cli.id = v.cliente_id
        WHERE v.activo = 1
        AND v.id NOT IN (SELECT vehiculo_id FROM movimientos WHERE estado = 'ACTIVO')
        ORDER BY v.placa ASC;
    """)
    vehiculos_disponibles = cursor.fetchall()

    # Celdas disponibles
    cursor.execute("""
        SELECT id, codigo, tipo_permitido, ubicacion
        FROM celdas
        WHERE estado = 'DISPONIBLE' AND activo = 1
        ORDER BY codigo ASC;
    """)
    celdas_disponibles = cursor.fetchall()

    return render_template(
        "movimientos/index.html",
        movimientos=movimientos_activos,
        vehiculos_disponibles=vehiculos_disponibles,
        celdas_disponibles=celdas_disponibles
    )


@app.route("/movimientos/entrada", methods=["POST"])
@login_required
def movimientos_entrada():
    vehiculo_id = request.form.get("vehiculo_id", "").strip()
    celda_id = request.form.get("celda_id", "").strip()
    observaciones = request.form.get("observaciones", "").strip()
    usuario_id = session.get("user_id")

    if not vehiculo_id or not celda_id:
        flash("Debe seleccionar un vehículo y una celda para el ingreso.", "danger")
        return redirect(url_for("movimientos_index"))

    conn = get_db()
    try:
        services.registrar_entrada(
            conn=conn,
            vehiculo_id=int(vehiculo_id),
            celda_id=int(celda_id),
            usuario_id=usuario_id,
            observaciones=observaciones
        )
        flash("¡Ingreso registrado exitosamente! La celda ha sido marcada como ocupada.", "success")
    except ValueError as e:
        flash(f"Error al registrar entrada: {str(e)}", "danger")
    except Exception as e:
        flash(f"Error inesperado al registrar entrada: {str(e)}", "danger")

    # Retornar a la página de origen si fue desde el dashboard
    origen = request.form.get("origen", "movimientos")
    if origen == "dashboard":
        return redirect(url_for("dashboard"))
    return redirect(url_for("movimientos_index"))


@app.route("/movimientos/<int:movimiento_id>/salida", methods=["POST"])
@login_required
def movimientos_salida(movimiento_id):
    observaciones_salida = request.form.get("observaciones_salida", "").strip()
    conn = get_db()

    try:
        mov = services.registrar_salida(
            conn=conn,
            movimiento_id=movimiento_id,
            observaciones_salida=observaciones_salida
        )
        flash(f"¡Salida registrada con éxito! El vehículo {mov['placa']} ha salido y la celda {mov['codigo_celda']} quedó libre.", "success")
    except ValueError as e:
        flash(f"Error al procesar la salida: {str(e)}", "danger")
    except Exception as e:
        flash(f"Error inesperado en salida: {str(e)}", "danger")

    origen = request.form.get("origen", "movimientos")
    if origen == "dashboard":
        return redirect(url_for("dashboard"))
    return redirect(url_for("movimientos_index"))


# ---------------------------------------------------------
# 6. Historial de Movimientos con Filtros
# ---------------------------------------------------------
@app.route("/movimientos/historial")
@login_required
def movimientos_historial():
    placa = request.args.get("placa", "").strip().upper()
    fecha_desde = request.args.get("fecha_desde", "").strip()
    fecha_hasta = request.args.get("fecha_hasta", "").strip()
    estado = request.args.get("estado", "TODOS").strip()

    conn = get_db()
    movimientos = services.get_historial_movimientos(
        conn=conn,
        placa=placa,
        fecha_desde=fecha_desde,
        fecha_hasta=fecha_hasta,
        estado=estado
    )

    return render_template(
        "movimientos/historial.html",
        movimientos=movimientos,
        placa=placa,
        fecha_desde=fecha_desde,
        fecha_hasta=fecha_hasta,
        estado=estado
    )


# ---------------------------------------------------------
# 7. Gestión de Mensualidades
# ---------------------------------------------------------
@app.route("/mensualidades")
@login_required
def mensualidades_index():
    periodo = request.args.get("periodo", "").strip()
    estado = request.args.get("estado", "TODOS").strip()
    conn = get_db()
    cursor = conn.cursor()

    sql = """
        SELECT 
            m.*,
            v.placa, v.marca, v.modelo, v.tipo AS tipo_vehiculo,
            cli.nombre AS cliente_nombre, cli.documento AS cliente_documento, cli.telefono AS cliente_telefono,
            u.nombre AS usuario_nombre
        FROM mensualidades m
        JOIN vehiculos v ON v.id = m.vehiculo_id
        JOIN clientes cli ON cli.id = m.cliente_id
        LEFT JOIN usuarios u ON u.id = m.usuario_id
        WHERE 1=1
    """
    params = []

    if periodo:
        sql += " AND m.periodo = ?"
        params.append(periodo)

    if estado and estado != "TODOS":
        sql += " AND m.estado = ?"
        params.append(estado)

    sql += " ORDER BY m.periodo DESC, m.fecha_pago DESC;"

    cursor.execute(sql, params)
    mensualidades = cursor.fetchall()

    # Obtener lista de periodos existentes para el selector de filtro
    cursor.execute("SELECT DISTINCT periodo FROM mensualidades ORDER BY periodo DESC;")
    periodos_disponibles = [r["periodo"] for r in cursor.fetchall()]

    return render_template(
        "mensualidades/index.html",
        mensualidades=mensualidades,
        periodos_disponibles=periodos_disponibles,
        periodo_seleccionado=periodo,
        estado_seleccionado=estado
    )


@app.route("/mensualidades/nuevo", methods=["GET", "POST"])
@login_required
def mensualidades_nuevo():
    conn = get_db()
    cursor = conn.cursor()

    if request.method == "POST":
        vehiculo_id = request.form.get("vehiculo_id", "").strip()
        periodo = request.form.get("periodo", "").strip()
        fecha_inicio = request.form.get("fecha_inicio", "").strip()
        fecha_fin = request.form.get("fecha_fin", "").strip()
        valor = request.form.get("valor", "").strip()
        fecha_pago = request.form.get("fecha_pago", "").strip()
        metodo_pago = request.form.get("metodo_pago", "Efectivo").strip()
        referencia_pago = request.form.get("referencia_pago", "").strip()
        estado = request.form.get("estado", "PAGADO").strip()
        observaciones = request.form.get("observaciones", "").strip()
        usuario_id = session.get("user_id")

        if not vehiculo_id or not periodo or not fecha_inicio or not fecha_fin or not valor or not fecha_pago:
            flash("Todos los campos marcados con asterisco son requeridos.", "danger")
            cursor.execute("""
                SELECT v.id, v.placa, v.marca, v.modelo, v.tipo, cli.id AS cliente_id, cli.nombre AS cliente_nombre
                FROM vehiculos v
                JOIN clientes cli ON cli.id = v.cliente_id
                WHERE v.activo = 1
                ORDER BY v.placa ASC;
            """)
            vehiculos = cursor.fetchall()
            return render_template("mensualidades/form.html", vehiculos=vehiculos, datos=request.form)

        # Buscar el cliente asociado al vehículo
        cursor.execute("SELECT cliente_id FROM vehiculos WHERE id = ?;", (vehiculo_id,))
        row_v = cursor.fetchone()
        if not row_v:
            flash("Vehículo no válido.", "danger")
            return redirect(url_for("mensualidades_index"))
        cliente_id = row_v["cliente_id"]

        try:
            services.registrar_mensualidad(
                conn=conn,
                vehiculo_id=int(vehiculo_id),
                cliente_id=cliente_id,
                periodo=periodo,
                fecha_inicio=fecha_inicio,
                fecha_fin=fecha_fin,
                valor=valor,
                fecha_pago=fecha_pago,
                metodo_pago=metodo_pago,
                referencia_pago=referencia_pago,
                estado=estado,
                observaciones=observaciones,
                usuario_id=usuario_id
            )
            flash(f"Mensualidad para el periodo {periodo} registrada con éxito.", "success")
            return redirect(url_for("mensualidades_index"))
        except ValueError as e:
            flash(f"Error al registrar pago de mensualidad: {str(e)}", "danger")
            cursor.execute("""
                SELECT v.id, v.placa, v.marca, v.modelo, v.tipo, cli.id AS cliente_id, cli.nombre AS cliente_nombre
                FROM vehiculos v
                JOIN clientes cli ON cli.id = v.cliente_id
                WHERE v.activo = 1
                ORDER BY v.placa ASC;
            """)
            vehiculos = cursor.fetchall()
            return render_template("mensualidades/form.html", vehiculos=vehiculos, datos=request.form)

    # Cargar lista de vehículos activos con sus clientes
    cursor.execute("""
        SELECT v.id, v.placa, v.marca, v.modelo, v.tipo, cli.id AS cliente_id, cli.nombre AS cliente_nombre
        FROM vehiculos v
        JOIN clientes cli ON cli.id = v.cliente_id
        WHERE v.activo = 1
        ORDER BY v.placa ASC;
    """)
    vehiculos = cursor.fetchall()

    hoy = date.today()
    primer_dia = date(hoy.year, hoy.month, 1).strftime("%Y-%m-%d")
    periodo_def = hoy.strftime("%Y-%m")
    # Fin del mes
    if hoy.month == 12:
        ultimo_dia = date(hoy.year, 12, 31).strftime("%Y-%m-%d")
    else:
        from datetime import timedelta
        ultimo_dia = (date(hoy.year, hoy.month + 1, 1) - timedelta(days=1)).strftime("%Y-%m-%d")

    datos_defecto = {
        "periodo": periodo_def,
        "fecha_inicio": primer_dia,
        "fecha_fin": ultimo_dia,
        "fecha_pago": hoy.strftime("%Y-%m-%d"),
        "valor": 180000,
        "metodo_pago": "Efectivo",
        "estado": "PAGADO"
    }

    return render_template("mensualidades/form.html", vehiculos=vehiculos, datos=datos_defecto)


@app.route("/mensualidades/<int:id>/estado", methods=["POST"])
@login_required
def mensualidades_cambiar_estado(id):
    nuevo_estado = request.form.get("nuevo_estado", "").strip()
    if nuevo_estado not in ("PAGADO", "PENDIENTE", "ANULADO"):
        flash("Estado de mensualidad inválido.", "danger")
        return redirect(url_for("mensualidades_index"))

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE mensualidades SET estado = ? WHERE id = ?;", (nuevo_estado, id))
    conn.commit()

    flash(f"Estado de la mensualidad actualizado a '{nuevo_estado}'.", "info")
    return redirect(url_for("mensualidades_index"))


# ---------------------------------------------------------
# 8. Gestión de Novedades e Incidentes
# ---------------------------------------------------------
@app.route("/novedades")
@login_required
def novedades_index():
    estado = request.args.get("estado", "TODOS").strip()
    conn = get_db()
    cursor = conn.cursor()

    sql = """
        SELECT 
            n.*,
            v.placa, v.marca, v.modelo,
            u.nombre AS usuario_nombre
        FROM novedades n
        LEFT JOIN vehiculos v ON v.id = n.vehiculo_id
        LEFT JOIN usuarios u ON u.id = n.usuario_id
        WHERE 1=1
    """
    params = []

    if estado and estado != "TODOS":
        sql += " AND n.estado = ?"
        params.append(estado)

    sql += " ORDER BY n.fecha DESC;"

    cursor.execute(sql, params)
    novedades = cursor.fetchall()

    # Vehículos activos para el modal de registro rápido
    cursor.execute("SELECT id, placa, marca, modelo FROM vehiculos WHERE activo = 1 ORDER BY placa ASC;")
    vehiculos = cursor.fetchall()

    return render_template(
        "novedades/index.html",
        novedades=novedades,
        vehiculos=vehiculos,
        estado_seleccionado=estado
    )


@app.route("/novedades/nueva", methods=["POST"])
@login_required
def novedades_nueva():
    vehiculo_id = request.form.get("vehiculo_id", "").strip()
    tipo = request.form.get("tipo", "").strip()
    descripcion = request.form.get("descripcion", "").strip()
    usuario_id = session.get("user_id")

    if not tipo or not descripcion:
        flash("El tipo de novedad y la descripción detallada son requeridos.", "danger")
        return redirect(url_for("novedades_index"))

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO novedades (vehiculo_id, tipo, descripcion, usuario_id, estado, fecha)
        VALUES (?, ?, ?, ?, 'ABIERTO', CURRENT_TIMESTAMP);
    """, (int(vehiculo_id) if vehiculo_id else None, tipo, descripcion, usuario_id))
    conn.commit()

    flash("Novedad registrada exitosamente en la bitácora.", "success")
    return redirect(url_for("novedades_index"))


@app.route("/novedades/<int:novedad_id>/resolver", methods=["POST"])
@login_required
def novedades_resolver(novedad_id):
    nuevo_estado = request.form.get("estado", "SOLUCIONADO").strip()
    solucion_notas = request.form.get("solucion_notas", "").strip()

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE novedades
        SET estado = ?, solucion_notas = ?
        WHERE id = ?;
    """, (nuevo_estado, solucion_notas or None, novedad_id))
    conn.commit()

    flash(f"Novedad #{novedad_id} actualizada a estado '{nuevo_estado}'.", "info")
    return redirect(url_for("novedades_index"))


# ---------------------------------------------------------
# API Helper para soporte de formularios dinámicos
# ---------------------------------------------------------
@app.route("/api/vehiculo/<int:vehiculo_id>")
@login_required
def api_vehiculo(vehiculo_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT v.*, cli.nombre AS cliente_nombre, cli.documento AS cliente_documento, cli.telefono AS cliente_telefono
        FROM vehiculos v
        JOIN clientes cli ON cli.id = v.cliente_id
        WHERE v.id = ?;
    """, (vehiculo_id,))
    row = cursor.fetchone()
    if not row:
        return jsonify({"error": "Vehículo no encontrado"}), 404

    return jsonify(dict(row))


# ---------------------------------------------------------
# 9. Gestión de Usuarios del Sistema (Iteración 2)
# ---------------------------------------------------------
@app.route("/usuarios")
@login_required
@admin_required
def usuarios_index():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, nombre, username, email, rol, activo, creado_en
        FROM usuarios
        ORDER BY nombre ASC;
    """)
    usuarios = cursor.fetchall()
    return render_template("usuarios/index.html", usuarios=usuarios)


@app.route("/usuarios/nuevo", methods=["GET", "POST"])
@login_required
@admin_required
def usuarios_nuevo():
    if request.method == "POST":
        nombre = request.form.get("nombre", "").strip()
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip()
        rol = request.form.get("rol", "").strip().lower()
        password = request.form.get("password", "").strip()
        confirm_password = request.form.get("confirm_password", "").strip()

        # Validaciones de campos obligatorios
        if not nombre or not username or not email or not rol or not password:
            flash("Todos los campos marcados con asterisco son obligatorios.", "danger")
            return render_template("usuarios/form.html", usuario=request.form, es_nuevo=True)

        # Validar que no se asignen roles ajenos al sistema
        if rol not in ("admin", "operador"):
            flash("El rol asignado no es válido. Los roles permitidos son Administrador y Operador.", "danger")
            return render_template("usuarios/form.html", usuario=request.form, es_nuevo=True)

        # Validar coincidencia de contraseña
        if password != confirm_password:
            flash("Las contraseñas ingresadas no coinciden.", "danger")
            return render_template("usuarios/form.html", usuario=request.form, es_nuevo=True)

        if len(password) < 6:
            flash("La contraseña debe tener una longitud mínima de 6 caracteres.", "danger")
            return render_template("usuarios/form.html", usuario=request.form, es_nuevo=True)

        conn = get_db()
        cursor = conn.cursor()

        # Validar username no repetido
        cursor.execute("SELECT id FROM usuarios WHERE LOWER(username) = LOWER(?);", (username,))
        if cursor.fetchone():
            flash(f"El nombre de usuario '{username}' ya se encuentra registrado.", "danger")
            return render_template("usuarios/form.html", usuario=request.form, es_nuevo=True)

        # Validar email no repetido
        cursor.execute("SELECT id FROM usuarios WHERE LOWER(email) = LOWER(?);", (email,))
        if cursor.fetchone():
            flash(f"El correo electrónico '{email}' ya se encuentra registrado.", "danger")
            return render_template("usuarios/form.html", usuario=request.form, es_nuevo=True)

        # Hash seguro de contraseña mediante Werkzeug
        password_hash = generate_password_hash(password)

        cursor.execute("""
            INSERT INTO usuarios (nombre, username, email, password_hash, rol, activo)
            VALUES (?, ?, ?, ?, ?, 1);
        """, (nombre, username, email, password_hash, rol))
        conn.commit()

        flash(f"Usuario '{nombre}' registrado exitosamente con rol {rol}.", "success")
        return redirect(url_for("usuarios_index"))

    return render_template("usuarios/form.html", usuario={}, es_nuevo=True)


@app.route("/usuarios/<int:usuario_id>/editar", methods=["GET", "POST"])
@login_required
@admin_required
def usuarios_editar(usuario_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM usuarios WHERE id = ?;", (usuario_id,))
    usuario = cursor.fetchone()

    if not usuario:
        flash("Usuario no encontrado.", "danger")
        return redirect(url_for("usuarios_index"))

    if request.method == "POST":
        nombre = request.form.get("nombre", "").strip()
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip()
        rol = request.form.get("rol", "").strip().lower()
        password = request.form.get("password", "").strip()
        confirm_password = request.form.get("confirm_password", "").strip()

        if not nombre or not username or not email or not rol:
            flash("Nombre, nombre de usuario, correo electrónico y rol son obligatorios.", "danger")
            return render_template("usuarios/form.html", usuario=request.form, es_nuevo=False, usuario_id=usuario_id)

        if rol not in ("admin", "operador"):
            flash("Rol inválido. Se permite únicamente 'admin' u 'operador'.", "danger")
            return render_template("usuarios/form.html", usuario=request.form, es_nuevo=False, usuario_id=usuario_id)

        # Validar username no repetido excluyendo el usuario actual
        cursor.execute("SELECT id FROM usuarios WHERE LOWER(username) = LOWER(?) AND id != ?;", (username, usuario_id))
        if cursor.fetchone():
            flash(f"El nombre de usuario '{username}' ya está en uso por otro usuario.", "danger")
            return render_template("usuarios/form.html", usuario=request.form, es_nuevo=False, usuario_id=usuario_id)

        # Validar email no repetido excluyendo el usuario actual
        cursor.execute("SELECT id FROM usuarios WHERE LOWER(email) = LOWER(?) AND id != ?;", (email, usuario_id))
        if cursor.fetchone():
            flash(f"El correo electrónico '{email}' ya pertenece a otro usuario.", "danger")
            return render_template("usuarios/form.html", usuario=request.form, es_nuevo=False, usuario_id=usuario_id)

        # Regla: Si se cambia el rol de admin a operador, verificar que no sea el último admin activo
        if usuario["rol"] == "admin" and rol != "admin" and usuario["activo"] == 1:
            cursor.execute("SELECT COUNT(*) AS total FROM usuarios WHERE rol = 'admin' AND activo = 1;")
            if cursor.fetchone()["total"] <= 1:
                flash("No se puede cambiar el rol del único administrador activo del sistema.", "danger")
                return render_template("usuarios/form.html", usuario=request.form, es_nuevo=False, usuario_id=usuario_id)

        # Si se ingresó nueva contraseña, validar y actualizar
        if password:
            if password != confirm_password:
                flash("Las contraseñas no coinciden.", "danger")
                return render_template("usuarios/form.html", usuario=request.form, es_nuevo=False, usuario_id=usuario_id)
            if len(password) < 6:
                flash("La contraseña debe tener una longitud mínima de 6 caracteres.", "danger")
                return render_template("usuarios/form.html", usuario=request.form, es_nuevo=False, usuario_id=usuario_id)
            new_hash = generate_password_hash(password)
            cursor.execute("""
                UPDATE usuarios
                SET nombre = ?, username = ?, email = ?, rol = ?, password_hash = ?
                WHERE id = ?;
            """, (nombre, username, email, rol, new_hash, usuario_id))
        else:
            cursor.execute("""
                UPDATE usuarios
                SET nombre = ?, username = ?, email = ?, rol = ?
                WHERE id = ?;
            """, (nombre, username, email, rol, usuario_id))

        conn.commit()

        # Si el usuario editó su propia cuenta, actualizar datos de sesión
        if session.get("user_id") == usuario_id:
            session["user_name"] = nombre
            session["user_role"] = rol

        flash(f"Usuario '{nombre}' actualizado correctamente.", "success")
        return redirect(url_for("usuarios_index"))

    return render_template("usuarios/form.html", usuario=usuario, es_nuevo=False, usuario_id=usuario_id)


@app.route("/usuarios/<int:usuario_id>/toggle", methods=["POST"])
@login_required
@admin_required
def usuarios_toggle(usuario_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, nombre, rol, activo FROM usuarios WHERE id = ?;", (usuario_id,))
    usuario = cursor.fetchone()

    if not usuario:
        flash("Usuario no encontrado.", "danger")
        return redirect(url_for("usuarios_index"))

    # Regla: Ningún administrador puede desactivarse a sí mismo
    if usuario_id == session.get("user_id"):
        flash("No puede desactivar su propia cuenta mientras tiene la sesión activa.", "danger")
        return redirect(url_for("usuarios_index"))

    # Regla: No se debe permitir desactivar al último administrador activo
    if usuario["rol"] == "admin" and usuario["activo"] == 1:
        cursor.execute("SELECT COUNT(*) AS total FROM usuarios WHERE rol = 'admin' AND activo = 1;")
        total_admins = cursor.fetchone()["total"]
        if total_admins <= 1:
            flash("No se puede desactivar al único administrador activo del sistema.", "danger")
            return redirect(url_for("usuarios_index"))

    nuevo_estado = 0 if usuario["activo"] == 1 else 1
    cursor.execute("UPDATE usuarios SET activo = ? WHERE id = ?;", (nuevo_estado, usuario_id))
    conn.commit()

    accion = "activado" if nuevo_estado == 1 else "desactivado"
    flash(f"Usuario '{usuario['nombre']}' {accion} exitosamente.", "info")
    return redirect(url_for("usuarios_index"))


# ---------------------------------------------------------
# Manejadores de Errores
# ---------------------------------------------------------
@app.errorhandler(403)
def forbidden_error(error):
    return render_template("403.html"), 403


@app.errorhandler(404)
def not_found_error(error):
    return render_template("404.html"), 404


@app.errorhandler(500)
def internal_error(error):
    return render_template("500.html"), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
