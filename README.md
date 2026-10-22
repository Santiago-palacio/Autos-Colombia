# Autos Colombia - Sistema de Gestión de Parqueadero

Sistema web integral desarrollado en Python con Flask y SQLite para la administración y control operativo de parqueaderos en Colombia.

## 🚀 Características Principales

- **Control de Entradas y Salidas**: Registro en tiempo real de vehículos (carros y motos) con cálculo automático de tarifas por minuto/hora.
- **Gestión de Celdas y Cupos**: Monitoreo de disponibilidad de celdas para automóviles y motocicletas.
- **Clientes y Vehículos**: Directorio de propietarios y vehículos frecuentes con historial de visitas.
- **Mensualidades**: Control de pagos periódicos, estados (pagado, pendiente, anulado) y vigencias.
- **Bitácora de Novedades**: Registro y seguimiento de incidentes o reportes en el parqueadero.
- **Panel Administrativo (Dashboard)**: Estadísticas en vivo de ocupación, ingresos y movimientos diarios.

---

## 🛠️ Tecnologías Utilizadas

- **Backend**: Python 3, Flask
- **Base de Datos**: SQLite3
- **Frontend**: HTML5, Vanilla CSS moderno, JavaScript
- **Pruebas**: Pytest

---

## 📋 Requisitos Previos

- Python 3.10 o superior instalado en el sistema.

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
   - En Windows, simplemente ejecuta el archivo:
     ```cmd
     iniciar.bat
     ```
   - O mediante la consola:
     ```bash
     python app.py
     ```

4. **Acceder en el navegador:**
   - Abre `http://127.0.0.1:5000`

---

## 🧪 Ejecución de Pruebas

Para ejecutar la suite de pruebas automatizadas:
```bash
pytest
```
