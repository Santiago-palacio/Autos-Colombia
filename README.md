# Autos Colombia - Sistema de Gestión de Parqueadero

Sistema web integral desarrollado en Python con Flask y SQLite para la administración, control de accesos, tarifas y gestión operativa de parqueaderos por mensualidades en Colombia.

---

## 🚀 Funcionalidades del Sistema

### Iteración 1 (Operación y Control Base)
- **Control de Entradas y Salidas**: Registro en tiempo real de ingresos y salidas vehiculares con liberación automática de celdas.
- **Gestión de Celdas y Bahías**: Monitoreo de disponibilidad en vivo con mapa visual e indicadores de ocupación.
- **Directorio de Clientes**: Registro, consulta, edición y activación/desactivación lógica de propietarios y afiliados.
- **Gestión de Vehículos**: Control de parque automotor, validación de placas únicas y asociación a clientes.
- **Control de Mensualidades**: Registro de pagos periódicos, estados (pagado, pendiente, anulado) y tarifas sugeridas dinámicas.
- **Bitácora de Novedades**: Reporte y seguimiento de incidentes o novedades operativas con flujo de resolución.
- **Historial de Movimientos**: Auditoría y consulta histórica filtrable por placa, rango de fechas y estado de estancia.
- **Panel Administrativo (Dashboard)**: Estadísticas en vivo de cupos disponibles, porcentaje de ocupación e ingresos del periodo.

### Iteración 2 (Gestión de Usuarios, Control de Acceso y Gestión Avanzada de Celdas)
- **Módulo de Gestión de Usuarios**:
  - Listado general de usuarios del sistema con filtrado en tiempo real.
  - Registro de nuevos usuarios con validación de obligatoriedad y unicidad de username y correo.
  - Edición de información personal y actualización segura de contraseñas.
  - Activación y desactivación lógica de cuentas de usuario.
  - Asignación de roles del sistema: `Administrador` y `Operador`.
  - Cifrado unidireccional de contraseñas con hash seguro mediante Werkzeug (PBKDF2/Scrypt).
  - Bloqueo automático de inicio de sesión para usuarios inactivos o dados de baja.
- **Control de Acceso Basado en Roles (RBAC)**:
  - Decorador `@admin_required` que restringe el backend ante accesos no autorizados (HTTP 403 Forbidden).
  - El administrador gestiona usuarios y configuraciones del parqueadero.
  - El operador realiza las tareas operativas habituales sin acceso a la gestión de usuarios.
  - Reglas de integridad: ningún administrador puede desactivarse a sí mismo en sesión y se impide la desactivación del último administrador activo.
- **Gestión Avanzada de Celdas**:
  - Edición completa de celdas (código identificador, tipo de vehículo permitido y ubicación).
  - Conmutación de estados operativos entre `DISPONIBLE` y `MANTENIMIENTO`.
  - Baja lógica y reactivación de celdas (campo `activo`), impidiendo su oferta para nuevos ingresos.
  - Validación de compatibilidad entre el tipo de vehículo y el tipo permitido por la celda.
  - Regla de negocio: prohibición de desactivar o pasar a mantenimiento celdas ocupadas.
- **Seguridad Mejorada**:
  - Protección contra ataques CSRF (Cross-Site Request Forgery) mediante tokens en formularios.
  - Prevención de redirección abierta (Open Redirect) tras el inicio de sesión.
  - Consultas SQL 100% parametrizadas para inmunidad contra inyecciones SQL.
  - Clave secreta configurable por variable de entorno (`AUTOSCOLOMBIA_SECRET_KEY`).
  - Configuración estricta de cookies de sesión (`HttpOnly`, `SameSite=Lax`).

---

## 🛠️ Tecnologías Utilizadas

- **Backend**: Python 3.10+, Flask 3.x
- **Base de Datos**: SQLite3 con claves foráneas activas (`PRAGMA foreign_keys = ON;`)
- **Frontend**: HTML5, Vanilla CSS moderno (modo oscuro institucional responsivo), JavaScript Vanilla
- **Seguridad**: Werkzeug Security (Hashing seguro de contraseñas), Secrets (Tokens CSRF criptográficos)
- **Pruebas Automatizadas**: Pytest

---

## 📂 Estructura del Proyecto

```text
Autoscolombia/
├── app.py                     # Controlador web Flask: rutas HTTP, autenticación, RBAC y filtros
├── database.py                # Conexión SQLite, esquemas DDL, migraciones automáticas y semillero
├── services.py                # Capa de lógica de negocio: reglas de entrada/salida y compatibilidad
├── autoscolombia.db           # Base de datos SQLite operacional
├── requirements.txt           # Dependencias del proyecto
├── iniciar.bat / powershell.cmd # Scripts de conveniencia para ejecución en Windows
├── README.md                  # Documentación técnica del proyecto
├── static/
│   ├── css/styles.css         # Estilos visuales institucionales
│   └── js/main.js             # Lógica e interactividad del cliente
├── templates/
│   ├── base.html              # Plantilla base con barra lateral y modales
│   ├── login.html             # Pantalla de acceso
│   ├── dashboard.html         # Panel de métricas y mapa visual
│   ├── 403.html / 404.html / 500.html # Páginas de error y acceso denegado
│   ├── celdas/                # Vistas de celdas (listado, edición)
│   ├── clientes/              # Vistas de clientes (listado, creación, edición)
│   ├── mensualidades/         # Vistas de mensualidades y pagos
│   ├── movimientos/           # Vistas de estancias activas e historial
│   ├── novedades/             # Bitácora de incidentes
│   └── usuarios/              # Vistas de administración de usuarios (Iteración 2)
└── tests/
    ├── test_database.py       # Pruebas de restricciones e integridad en SQLite
    ├── test_services.py       # Pruebas de reglas de negocio en capa de servicios
    ├── test_routes.py         # Pruebas de integración HTTP de la Iteración 1
    ├── test_celdas.py         # Pruebas de la gestión de celdas (Iteración 2)
    └── test_usuarios.py       # Pruebas de usuarios, roles y RBAC (Iteración 2)
```

---

## 📋 Requisitos Previos

- Python 3.10 o superior instalado en el sistema.
- Gestor de paquetes `pip`.

---

## 💻 Instalación y Puesta en Marcha

1. **Clonar el repositorio:**
   ```bash
   git clone https://github.com/Santiago-palacio/Autos-Colombia.git
   cd Autos-Colombia
   ```

2. **Instalar dependencias:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Ejecutar la aplicación:**
   - En Windows mediante el script:
     ```cmd
     iniciar.bat
     ```
   - O mediante consola:
     ```bash
     python app.py
     ```

4. **Acceder en el navegador:**
   - Ingresa a: `http://127.0.0.1:5000`

---

## 👥 Usuarios de Prueba para Evaluación Académica

El sistema inicializa automáticamente dos cuentas de demostración:

| Rol | Usuario | Contraseña Demo | Permisos |
| :--- | :--- | :--- | :--- |
| **Administrador** | `admin` | `admin123` | Acceso completo: Gestión de usuarios, celdas, reportes y operaciones |
| **Operador** | `operador` | `operador123` | Operación del parqueadero: Entradas, salidas, mensualidades, novedades |

> **Nota de Seguridad:** En un entorno de producción real, cambie las contraseñas inmediatamente y configure la variable de entorno `AUTOSCOLOMBIA_SECRET_KEY`.

---

## 🧪 Ejecución de Pruebas Automatizadas

Para ejecutar la suite completa de 37 pruebas unitarias y de integración:

```bash
python -m pytest
```

Para ejecutar con reporte detallado (verbose):
```bash
python -m pytest -v
```
