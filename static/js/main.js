/**
 * main.js - Lógica interactiva para el sistema Autos Colombia
 */

document.addEventListener("DOMContentLoaded", function () {
  initModals();
  initSidebarMobile();
  initPlacaFormatters();
  initSpotCardClicks();
  initSalidaModals();
  initMensualidadVehiculoListener();
  initTableLiveFilter();
  initConfirmActions();
});

/* ==========================================================================
   1. Gestión de Modales
   ========================================================================== */
function openModal(modalId) {
  const modal = document.getElementById(modalId);
  if (modal) {
    modal.classList.add("active");
    document.body.style.overflow = "hidden";
  }
}

function closeModal(modalId) {
  const modal = document.getElementById(modalId);
  if (modal) {
    modal.classList.remove("active");
    document.body.style.overflow = "";
  }
}

function initModals() {
  // Botones que abren modales
  document.querySelectorAll("[data-modal-target]").forEach((trigger) => {
    trigger.addEventListener("click", function (e) {
      e.preventDefault();
      const targetId = this.getAttribute("data-modal-target");
      openModal(targetId);
    });
  });

  // Botones que cierran modales
  document.querySelectorAll("[data-modal-close]").forEach((btn) => {
    btn.addEventListener("click", function () {
      const modal = this.closest(".modal-overlay");
      if (modal) {
        modal.classList.remove("active");
        document.body.style.overflow = "";
      }
    });
  });

  // Cerrar al hacer clic fuera de la ventana modal
  document.querySelectorAll(".modal-overlay").forEach((overlay) => {
    overlay.addEventListener("click", function (e) {
      if (e.target === this) {
        this.classList.remove("active");
        document.body.style.overflow = "";
      }
    });
  });

  // Cerrar con la tecla ESC
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape") {
      document.querySelectorAll(".modal-overlay.active").forEach((openModalEl) => {
        openModalEl.classList.remove("active");
      });
      document.body.style.overflow = "";
    }
  });
}

/* ==========================================================================
   2. Menú Lateral Móvil
   ========================================================================== */
function initSidebarMobile() {
  const toggleBtn = document.getElementById("btn-toggle-sidebar");
  const sidebar = document.querySelector(".sidebar");

  if (toggleBtn && sidebar) {
    toggleBtn.addEventListener("click", function () {
      sidebar.classList.toggle("open");
    });

    // Cerrar al hacer clic fuera del sidebar en móvil
    document.addEventListener("click", function (e) {
      if (
        sidebar.classList.contains("open") &&
        !sidebar.contains(e.target) &&
        !toggleBtn.contains(e.target)
      ) {
        sidebar.classList.remove("open");
      }
    });
  }
}

/* ==========================================================================
   3. Formateador de Placas (Mayúsculas y sin espacios extra)
   ========================================================================== */
function initPlacaFormatters() {
  const placaInputs = document.querySelectorAll(
    'input[name="placa"], input[data-placa]'
  );
  placaInputs.forEach((input) => {
    input.addEventListener("input", function () {
      this.value = this.value.toUpperCase().replace(/\s+/g, "");
    });
  });
}

/* ==========================================================================
   4. Clic en Celdas del Mapa de Parqueadero
   ========================================================================== */
function initSpotCardClicks() {
  const availableSpots = document.querySelectorAll(".spot-card.disponible");
  const selectCelda = document.getElementById("select-celda-ingreso");
  const modalIngreso = document.getElementById("modal-nueva-entrada");

  if (availableSpots.length && modalIngreso && selectCelda) {
    availableSpots.forEach((card) => {
      card.addEventListener("click", function () {
        const celdaId = this.getAttribute("data-celda-id");
        if (celdaId) {
          selectCelda.value = celdaId;
          openModal("modal-nueva-entrada");
        }
      });
    });
  }
}

/* ==========================================================================
   5. Modal de Salida de Vehículos con Confirmación
   ========================================================================== */
function initSalidaModals() {
  const salidaBtns = document.querySelectorAll(".btn-registrar-salida");
  const formSalida = document.getElementById("form-salida-vehiculo");
  const spanPlaca = document.getElementById("salida-placa-span");
  const spanCelda = document.getElementById("salida-celda-span");

  if (salidaBtns.length && formSalida) {
    salidaBtns.forEach((btn) => {
      btn.addEventListener("click", function () {
        const movId = this.getAttribute("data-movimiento-id");
        const placa = this.getAttribute("data-placa");
        const celda = this.getAttribute("data-celda");
        const origen = this.getAttribute("data-origen") || "movimientos";

        formSalida.action = `/movimientos/${movId}/salida`;
        const origenInput = formSalida.querySelector('input[name="origen"]');
        if (origenInput) origenInput.value = origen;

        if (spanPlaca) spanPlaca.textContent = placa;
        if (spanCelda) spanCelda.textContent = celda;

        openModal("modal-salida-vehiculo");
      });
    });
  }
}

/* ==========================================================================
   6. Selección Dinámica de Vehículo en Mensualidades
   ========================================================================== */
function initMensualidadVehiculoListener() {
  const vehiculoSelect = document.getElementById("mensualidad-vehiculo-select");
  const infoBox = document.getElementById("cliente-info-preview");
  const inputValor = document.getElementById("mensualidad-valor-input");

  if (vehiculoSelect && infoBox) {
    vehiculoSelect.addEventListener("change", function () {
      const vehiculoId = this.value;
      if (!vehiculoId) {
        infoBox.style.display = "none";
        return;
      }

      fetch(`/api/vehiculo/${vehiculoId}`)
        .then((response) => {
          if (!response.ok) throw new Error("No se pudo obtener el vehículo");
          return response.json();
        })
        .then((data) => {
          infoBox.style.display = "block";
          document.getElementById("info-cliente-nombre").textContent = data.cliente_nombre;
          document.getElementById("info-cliente-doc").textContent = data.cliente_documento;
          document.getElementById("info-vehiculo-detalles").textContent = `${data.marca} ${data.modelo} (${data.tipo})`;

          // Sugerir tarifa estándar si el campo no ha sido editado
          if (inputValor && (!inputValor.value || inputValor.dataset.autoFilled === "true")) {
            if (data.tipo.includes("Moto")) {
              inputValor.value = 90000;
            } else if (data.tipo.includes("Camioneta") || data.tipo.includes("SUV")) {
              inputValor.value = 220000;
            } else {
              inputValor.value = 180000;
            }
            inputValor.dataset.autoFilled = "true";
          }
        })
        .catch((err) => {
          console.error("Error al consultar vehículo:", err);
        });
    });

    if (inputValor) {
      inputValor.addEventListener("input", function () {
        this.dataset.autoFilled = "false";
      });
    }
  }
}

/* ==========================================================================
   7. Filtrado Rápido en Tablas (Búsqueda en cliente sin recargar)
   ========================================================================== */
function initTableLiveFilter() {
  const filterInputs = document.querySelectorAll("[data-live-filter]");
  filterInputs.forEach((input) => {
    const tableId = input.getAttribute("data-live-filter");
    const table = document.getElementById(tableId);

    if (table) {
      input.addEventListener("input", function () {
        const filterVal = this.value.toLowerCase().trim();
        const rows = table.querySelectorAll("tbody tr");

        rows.forEach((row) => {
          const text = row.textContent.toLowerCase();
          row.style.display = text.includes(filterVal) ? "" : "none";
        });
      });
    }
  });
}

/* ==========================================================================
   8. Confirmación antes de Acciones Críticas
   ========================================================================== */
function initConfirmActions() {
  document.querySelectorAll("[data-confirm]").forEach((el) => {
    el.addEventListener("click", function (e) {
      const msg = this.getAttribute("data-confirm") || "¿Está seguro de realizar esta acción?";
      if (!confirm(msg)) {
        e.preventDefault();
      }
    });
  });
}
