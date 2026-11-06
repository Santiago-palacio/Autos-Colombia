"""
test_usuarios.py - Pruebas automatizadas de la Gestión de Usuarios, Roles y Permisos (Iteración 2).
"""

import pytest
import os
import tempfile
from app import app
from database import init_db, get_db_connection
from werkzeug.security import check_password_hash


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
    """Autentica la sesión como administrador."""
    return client.post("/login", data={
        "username": "admin",
        "password": "admin123"
    }, follow_redirects=True)


def login_operador(client):
    """Autentica la sesión como operador."""
    return client.post("/login", data={
        "username": "operador",
        "password": "operador123"
    }, follow_redirects=True)


def test_registrar_usuario_exitoso(client):
    """Verifica el registro exitoso de un nuevo usuario con contraseña cifrada."""
    login_admin(client)

    res = client.post("/usuarios/nuevo", data={
        "nombre": "Laura Marcela Gómez",
        "username": "lgomez",
        "email": "laura.gomez@autoscolombia.com",
        "rol": "operador",
        "password": "passwordSeguro123",
        "confirm_password": "passwordSeguro123"
    }, follow_redirects=True)

    assert res.status_code == 200
    assert b"registrado exitosamente" in res.data
    assert b"Laura Marcela G\xc3\xb3mez" in res.data or b"Laura Marcela" in res.data

    # Verificar en la base de datos que se haya guardado y la clave esté cifrada con hash
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM usuarios WHERE username = 'lgomez';")
    user = cursor.fetchone()
    conn.close()

    assert user is not None
    assert user["nombre"] == "Laura Marcela Gómez"
    assert user["rol"] == "operador"
    assert user["activo"] == 1
    assert user["password_hash"] != "passwordSeguro123"
    assert check_password_hash(user["password_hash"], "passwordSeguro123")


def test_impedir_username_duplicado(client):
    """Verifica que el sistema rechace el registro de nombres de usuario repetidos."""
    login_admin(client)

    # Intentar registrar usuario con username 'operador' (ya existe en seed)
    res = client.post("/usuarios/nuevo", data={
        "nombre": "Otro Operador",
        "username": "operador",
        "email": "otro.correo@test.com",
        "rol": "operador",
        "password": "password123",
        "confirm_password": "password123"
    }, follow_redirects=True)

    assert res.status_code == 200
    assert b"ya se encuentra registrado" in res.data


def test_impedir_email_duplicado(client):
    """Verifica que el sistema rechace el registro de correos electrónicos repetidos."""
    login_admin(client)

    # Intentar registrar usuario con email de admin
    res = client.post("/usuarios/nuevo", data={
        "nombre": "Usuario Clon Email",
        "username": "clon_email",
        "email": "admin@autoscolombia.com",
        "rol": "operador",
        "password": "password123",
        "confirm_password": "password123"
    }, follow_redirects=True)

    assert res.status_code == 200
    assert b"ya se encuentra registrado" in res.data


def test_editar_usuario(client):
    """Verifica la edición de datos de un usuario existente y actualización de contraseña."""
    login_admin(client)

    # Crear usuario previo
    client.post("/usuarios/nuevo", data={
        "nombre": "Pedro Morales",
        "username": "pmorales",
        "email": "pmorales@test.com",
        "rol": "operador",
        "password": "claveVieja123",
        "confirm_password": "claveVieja123"
    })

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM usuarios WHERE username = 'pmorales';")
    user_id = cursor.fetchone()["id"]
    conn.close()

    # Editar datos y contraseña
    res = client.post(f"/usuarios/{user_id}/editar", data={
        "nombre": "Pedro Antonio Morales Restrepo",
        "username": "pmorales_edit",
        "email": "pmorales_nuevo@test.com",
        "rol": "operador",
        "password": "claveNueva456",
        "confirm_password": "claveNueva456"
    }, follow_redirects=True)

    assert res.status_code == 200
    assert b"actualizado correctamente" in res.data

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM usuarios WHERE id = ?;", (user_id,))
    upd = cursor.fetchone()
    conn.close()

    assert upd["nombre"] == "Pedro Antonio Morales Restrepo"
    assert upd["username"] == "pmorales_edit"
    assert upd["email"] == "pmorales_nuevo@test.com"
    assert check_password_hash(upd["password_hash"], "claveNueva456")


def test_activar_y_desactivar_usuario(client):
    """Verifica la conmutación de estado activo / inactivo de un usuario."""
    login_admin(client)

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, activo FROM usuarios WHERE username = 'operador';")
    user = cursor.fetchone()
    user_id = user["id"]
    conn.close()

    # 1. Desactivar operador
    res_desact = client.post(f"/usuarios/{user_id}/toggle", follow_redirects=True)
    assert res_desact.status_code == 200
    assert b"desactivado exitosamente" in res_desact.data

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT activo FROM usuarios WHERE id = ?;", (user_id,))
    assert cursor.fetchone()["activo"] == 0
    conn.close()

    # 2. Reactivar operador
    res_act = client.post(f"/usuarios/{user_id}/toggle", follow_redirects=True)
    assert res_act.status_code == 200
    assert b"activado exitosamente" in res_act.data

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT activo FROM usuarios WHERE id = ?;", (user_id,))
    assert cursor.fetchone()["activo"] == 1
    conn.close()


def test_impedir_login_usuario_inactivo(client):
    """Verifica que un usuario desactivado no pueda iniciar sesión en el sistema."""
    login_admin(client)

    # Desactivar operador
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE usuarios SET activo = 0 WHERE username = 'operador';")
    conn.commit()
    conn.close()

    # Cerrar sesión admin
    client.get("/logout")

    # Intentar login como operador inactivo
    res = client.post("/login", data={
        "username": "operador",
        "password": "operador123"
    }, follow_redirects=True)

    assert b"inactiva" in res.data or b"inactivo" in res.data
    # Verificar que no accede al dashboard
    assert b"Panel Principal" not in res.data


def test_permisos_administrador_acceso_gestion_usuarios(client):
    """Verifica que un usuario con rol de Administrador pueda acceder a la gestión de usuarios."""
    login_admin(client)

    res = client.get("/usuarios")
    assert res.status_code == 200
    assert b"Gesti\xc3\xb3n de Usuarios" in res.data

    res_nuevo = client.get("/usuarios/nuevo")
    assert res_nuevo.status_code == 200
    assert b"Registrar Nuevo Usuario" in res_nuevo.data


def test_restricciones_operador_gestion_usuarios(client):
    """Verifica que un Operador no pueda acceder ni gestionar usuarios en el backend (HTTP 403)."""
    login_operador(client)

    # 1. Intentar acceder a listado
    res_list = client.get("/usuarios")
    assert res_list.status_code == 403
    assert b"Acceso Denegado" in res_list.data or b"administrador" in res_list.data

    # 2. Intentar acceder al formulario de nuevo usuario
    res_nuevo = client.get("/usuarios/nuevo")
    assert res_nuevo.status_code == 403

    # 3. Intentar crear usuario mediante POST
    res_post = client.post("/usuarios/nuevo", data={
        "nombre": "Intruso",
        "username": "intruso",
        "email": "intruso@test.com",
        "rol": "admin",
        "password": "password123",
        "confirm_password": "password123"
    })
    assert res_post.status_code == 403

    # 4. Intentar conmutar estado de otro usuario
    res_toggle = client.post("/usuarios/1/toggle")
    assert res_toggle.status_code == 403


def test_impedir_desactivar_ultimo_administrador(client):
    """Verifica que no sea posible desactivar al único administrador activo del sistema."""
    login_admin(client)

    # Verificar que solo hay 1 admin
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM usuarios WHERE rol = 'admin';")
    admin_id = cursor.fetchone()["id"]
    conn.close()

    # Intentar desactivar al admin
    res = client.post(f"/usuarios/{admin_id}/toggle", follow_redirects=True)
    assert res.status_code == 200
    assert b"No puede desactivar" in res.data or b"\xc3\xbanico administrador" in res.data

    # El admin debe seguir activo
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT activo FROM usuarios WHERE id = ?;", (admin_id,))
    assert cursor.fetchone()["activo"] == 1
    conn.close()


def test_validacion_roles_permitidos(client):
    """Verifica que el sistema rechace la asignación de roles no permitidos."""
    login_admin(client)

    res = client.post("/usuarios/nuevo", data={
        "nombre": "Rol Invalido",
        "username": "rol_invalido",
        "email": "rol_inv@test.com",
        "rol": "superadmin_hacker",
        "password": "password123",
        "confirm_password": "password123"
    }, follow_redirects=True)

    assert b"no es v\xc3\xa1lido" in res.data

