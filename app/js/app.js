const form = document.getElementById("transaction-form");
const message = document.getElementById("form-message");
const transactionsList = document.getElementById("transactions-list");
const backendStatus = document.getElementById("backend-status");
const exportMonthInput = document.getElementById("export-month");
const exportCsvButton = document.getElementById("export-csv-btn");
const reloadButton = document.getElementById("reload-btn");
const formTitle = document.getElementById("form-title");
const submitButton = document.getElementById("submit-btn");
const cancelEditButton = document.getElementById("cancel-edit-btn");
const dateInput = document.getElementById("data");
const categorySelect = document.getElementById("categoria");
const periodFilter = document.getElementById("period-filter");
const chartCanvas = document.getElementById("balance-chart");
const categoriesList = document.getElementById("categories-list");
const totalEntrate = document.getElementById("tot-entrate");
const totalSpese = document.getElementById("tot-spese");
const saldoFinale = document.getElementById("saldo-finale");

const objectiveForm = document.getElementById("objective-form");
const objectiveFormTitle = document.getElementById("objective-form-title");
const objectiveSubmitButton = document.getElementById("objective-submit-btn");
const cancelObjectiveEditButton = document.getElementById("cancel-objective-edit-btn");
const nomeObiettivoInput = document.getElementById("nome_obiettivo");
const costoObiettivoInput = document.getElementById("costo_obiettivo");
const dataTargetObiettivoInput = document.getElementById("data_target_obiettivo");
const objectivesList = document.getElementById("objectives-list");
const objectiveMessage = document.getElementById("objective-message");
const categoriesTotal = document.getElementById("categories-total");
const storicoPeriodLabel = document.getElementById("storico-period-label");

const aiRunBtn = document.getElementById("ai-run-btn");
const aiMessage = document.getElementById("ai-message");
const aiOutput = document.getElementById("ai-output");

let transazioniCorrenti = [];
let obiettiviCorrenti = [];
let editingId = null;
let editingObjectiveId = null;
let saldoChart = null;

dateInput.value = currentMonth();
exportMonthInput.value = currentCalendarMonth();

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  clearMessage();

  const formData = new FormData(form);
  const transazione = {
    tipo: formData.get("tipo"),
    importo: Number(document.getElementById("importo").value),
    data: dateInput.value,
    categoria: categorySelect.value,
    nota: document.getElementById("nota").value,
    evitabile: document.getElementById("evitabile").checked
  };

  try {
    if (editingId) {
      await api.updateTransazione(editingId, transazione);
      showMessage("Transazione aggiornata.", "ok");
    } else {
      await api.createTransazione(transazione);
      showMessage("Transazione salvata nel database locale.", "ok");
    }

    resetForm();
    await refreshData();
  } catch (error) {
    showMessage(error.message, "error");
  }
});

reloadButton.addEventListener("click", refreshData);
periodFilter.addEventListener("change", loadStorico);
exportCsvButton.addEventListener("click", exportCurrentMonthCsv);

cancelEditButton.addEventListener("click", () => {
  resetForm();
  showMessage("Modifica annullata.", "ok");
});

transactionsList.addEventListener("click", async (event) => {
  const button = event.target.closest("button[data-action]");
  if (!button) {
    return;
  }

  const id = Number(button.dataset.id);
  const action = button.dataset.action;

  if (action === "edit") {
    startEdit(id);
    return;
  }

  if (action === "delete") {
    await deleteTransazione(id);
  }
});

// OBIETTIVI: submit + delete
objectiveForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  objectiveMessage.textContent = "";
  objectiveMessage.className = "message";

  const payload = {
    nome: nomeObiettivoInput.value,
    costo: Number(costoObiettivoInput.value),
    data_target: dataTargetObiettivoInput.value
  };

  try {
    if (editingObjectiveId) {
      await api.updateObiettivo(editingObjectiveId, payload);
      objectiveMessage.textContent = "Obiettivo aggiornato.";
    } else {
      await api.createObiettivo(payload);
      objectiveMessage.textContent = "Obiettivo salvato.";
    }

    resetObjectiveForm();
    objectiveMessage.className = "message ok";
    await loadObiettivi();
  } catch (error) {
    objectiveMessage.textContent = error.message;
    objectiveMessage.className = "message error";
  }
});

cancelObjectiveEditButton.addEventListener("click", () => {
  resetObjectiveForm();
  objectiveMessage.textContent = "Modifica annullata.";
  objectiveMessage.className = "message ok";
});

objectivesList.addEventListener("click", async (event) => {
  const button = event.target.closest("button[data-action]");
  if (!button) {
    return;
  }
  const id = Number(button.dataset.id);
  const action = button.dataset.action;

  if (action === "edit-objective") {
    startObjectiveEdit(id);
    return;
  }

  if (action !== "delete-objective") {
    return;
  }

  const confirmed = window.confirm("Vuoi eliminare questo obiettivo?");
  if (!confirmed) {
    return;
  }

  try {
    await api.deleteObiettivo(id);
    if (editingObjectiveId === id) {
      resetObjectiveForm();
    }
    await loadObiettivi();
  } catch (error) {
    objectiveMessage.textContent = error.message;
    objectiveMessage.className = "message error";
  }
});

// AI: esegui analisi sul periodo selezionato nello storico
aiRunBtn.addEventListener("click", async () => {
  aiMessage.textContent = "";
  aiMessage.className = "message";
  aiOutput.textContent = "";

  try {
    aiMessage.textContent = "Sto generando l'analisi...";
    aiMessage.className = "message ok";
    const data = await api.analisiAi(periodFilter.value);
    const report = data.report || {};
    aiOutput.textContent = JSON.stringify(report, null, 2);
    aiMessage.textContent = "Report salvato.";
    aiMessage.className = "message ok";
  } catch (error) {
    aiMessage.textContent = error.message;
    aiMessage.className = "message error";
  }
});

async function checkBackend() {
  try {
    await api.health();
    backendStatus.textContent = "backend attivo";
    backendStatus.className = "status ok";
  } catch (error) {
    backendStatus.textContent = "backend non raggiungibile";
    backendStatus.className = "status error";
  }
}

async function refreshData() {
  await loadTransazioni();
  await loadStorico();
  await loadObiettivi();
}

async function loadTransazioni() {
  try {
    const data = await api.listTransazioni();
    transazioniCorrenti = data.transazioni;
    renderTransazioni(transazioniCorrenti);
  } catch (error) {
    transactionsList.innerHTML = `<div class="empty-state">${escapeHtml(error.message)}</div>`;
  }
}

async function loadStorico() {
  try {
    const data = await api.getStorico(periodFilter.value);
    renderStorico(data.storico);
  } catch (error) {
    drawChart([]);
    categoriesList.innerHTML = `<div class="empty-state">${escapeHtml(error.message)}</div>`;
    categoriesTotal.textContent = "";
    storicoPeriodLabel.textContent = "";
  }
}

function renderTransazioni(transazioni) {
  if (!transazioni.length) {
    transactionsList.innerHTML = '<div class="empty-state">Nessuna transazione ancora.</div>';
    return;
  }

  transactionsList.innerHTML = transazioni.map((transazione) => {
    const sign = transazione.tipo === "entrata" ? "+" : "-";
    const amount = formatEuro(transazione.importo);
    const avoidable = transazione.evitabile ? " · evitabile" : "";
    const note = transazione.nota ? ` · ${escapeHtml(transazione.nota)}` : "";

    return `
      <article class="transaction-item">
        <div>
          <div class="transaction-title">${escapeHtml(formatCategory(transazione.categoria))}</div>
          <div class="transaction-meta">${formatDate(transazione.data)}${avoidable}${note}</div>
        </div>
        <div class="transaction-side">
          <div class="transaction-amount ${transazione.tipo}">
            ${sign}${amount}
          </div>
          <div class="transaction-actions">
            <button class="icon-btn" type="button" data-action="edit" data-id="${transazione.id}">Modifica</button>
            <button class="icon-btn danger" type="button" data-action="delete" data-id="${transazione.id}">Elimina</button>
          </div>
        </div>
      </article>
    `;
  }).join("");
}

function renderStorico(storico) {
  totalEntrate.textContent = formatEuro(storico.totale_entrate);
  totalSpese.textContent = formatEuro(storico.totale_spese);
  saldoFinale.textContent = formatEuro(storico.saldo_finale);
  saldoFinale.className = `metric-value ${storico.saldo_finale >= 0 ? "positive" : "negative"}`;

  if (storico.mese_inizio && storico.mese_fine) {
    if (storico.mese_inizio === storico.mese_fine) {
      storicoPeriodLabel.textContent = `Periodo: ${formatMonth(storico.mese_inizio)}`;
    } else {
      storicoPeriodLabel.textContent =
        `Periodo: ${formatMonth(storico.mese_inizio)} – ${formatMonth(storico.mese_fine)}`;
    }
  } else {
    storicoPeriodLabel.textContent = "";
  }

  drawChart(storico.punti);
  renderCategorie(storico.categorie);

  const sommaCategorie = storico.totale_categorie ?? storico.categorie.reduce(
    (sum, item) => sum + Number(item.totale),
    0
  );
  categoriesTotal.textContent = `Totale categorie: ${formatEuro(sommaCategorie)}`;
}

function drawChart(punti) {
  // Chart.js: distruggi grafico precedente per evitare duplicati
  if (saldoChart) {
    saldoChart.destroy();
    saldoChart = null;
  }

  const ctx = chartCanvas.getContext("2d");
  const width = chartCanvas.width;
  const height = chartCanvas.height;

  ctx.clearRect(0, 0, width, height);
  ctx.fillStyle = "#ffffff";
  ctx.fillRect(0, 0, width, height);

  if (!punti.length) {
    ctx.fillStyle = "#6a6a61";
    ctx.font = "14px system-ui";
    ctx.textAlign = "center";
    ctx.fillText("Nessun dato da mostrare", width / 2, height / 2);
    return;
  }

  const labels = punti.map((punto) => formatMonth(punto.mese));
  const values = punti.map((punto) => Number(punto.saldo));
  const pointColors = punti.map((punto) => (punto.saldo >= 0 ? "#315c19" : "#9b2929"));

  // Evita che Chart.js calcoli dimensioni strane su layout responsive
  chartCanvas.style.height = `${height}px`;
  chartCanvas.style.width = "100%";

  saldoChart = new Chart(ctx, {
    type: "line",
    data: {
      labels,
      datasets: [
        {
          data: values,
          borderColor: "#315c19",
          backgroundColor: "rgba(49, 92, 25, 0.08)",
          fill: false,
          tension: 0.25,
          pointRadius: 4,
          pointHoverRadius: 5,
          pointBackgroundColor: pointColors,
          pointBorderColor: pointColors,
          borderWidth: 2
        }
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: (ctx2) => `${ctx2.parsed.y.toFixed(2)} EUR`
          }
        }
      },
      scales: {
        x: {
          grid: { display: false },
          ticks: {
            color: "#6a6a61",
            maxTicksLimit: 8
          }
        },
        y: {
          grid: { color: "#e5e5dc" },
          ticks: { display: false }
        }
      }
    }
  });
}

function renderCategorie(categorie) {
  if (!categorie.length) {
    categoriesList.innerHTML = '<div class="empty-state">Nessuna spesa nel periodo.</div>';
    categoriesTotal.textContent = "";
    return;
  }

  const max = Math.max(...categorie.map((item) => item.totale), 1);
  categoriesList.innerHTML = categorie.map((item) => {
    const width = Math.max(6, (item.totale / max) * 100);
    return `
      <div class="category-row">
        <div class="category-info">
          <span>${escapeHtml(formatCategory(item.categoria))}</span>
          <strong>${formatEuro(item.totale)}</strong>
        </div>
        <div class="category-bar">
          <span style="width: ${width}%"></span>
        </div>
      </div>
    `;
  }).join("");
}

async function loadObiettivi() {
  try {
    const data = await api.listObiettivi();
    obiettiviCorrenti = data.obiettivi || [];
    renderObiettivi(obiettiviCorrenti);
  } catch (error) {
    objectivesList.innerHTML = `<div class="empty-state">${escapeHtml(error.message)}</div>`;
  }
}

function renderObiettivi(obiettivi) {
  if (!obiettivi.length) {
    objectivesList.innerHTML = '<div class="empty-state">Nessun obiettivo ancora.</div>';
    return;
  }

  objectivesList.innerHTML = obiettivi.map((obj) => {
    const percent = Math.max(0, Math.min(100, Number(obj.percentuale) || 0));
    return `
      <div class="objective-row">
        <div class="objective-header">
          <div class="objective-name">${escapeHtml(obj.nome)}</div>
          <div class="transaction-actions">
            <button class="icon-btn" type="button" data-action="edit-objective" data-id="${obj.id}">Modifica</button>
            <button class="icon-btn danger" type="button" data-action="delete-objective" data-id="${obj.id}">Elimina</button>
          </div>
        </div>
        <div class="objective-meta">
          <span>Accumulato: <strong>${formatEuro(obj.accumulato)}</strong></span>
          <span>Costo: <strong>${formatEuro(obj.costo)}</strong></span>
          <span>· ${percent}%</span>
        </div>
        <div class="objective-progress">
          <div class="objective-progress-fill" style="width:${percent}%"></div>
        </div>
        <div class="objective-submeta">
          Target: ${formatMonth(obj.data_target)} · Stima: ${escapeHtml(obj.stima_tempo)}
        </div>
      </div>
    `;
  }).join("");
}

function startObjectiveEdit(id) {
  const obiettivo = obiettiviCorrenti.find((item) => item.id === id);
  if (!obiettivo) {
    objectiveMessage.textContent = "Obiettivo non trovato.";
    objectiveMessage.className = "message error";
    return;
  }

  editingObjectiveId = id;
  objectiveFormTitle.textContent = "Modifica obiettivo";
  objectiveSubmitButton.textContent = "Aggiorna obiettivo";
  cancelObjectiveEditButton.classList.remove("hidden");

  nomeObiettivoInput.value = obiettivo.nome;
  costoObiettivoInput.value = obiettivo.costo;
  dataTargetObiettivoInput.value = normalizeMonth(obiettivo.data_target);

  objectiveMessage.textContent = "";
  objectiveMessage.className = "message";
  objectiveForm.scrollIntoView({ behavior: "smooth", block: "start" });
}

function resetObjectiveForm() {
  editingObjectiveId = null;
  objectiveForm.reset();
  objectiveFormTitle.textContent = "Aggiungi obiettivo";
  objectiveSubmitButton.textContent = "Salva obiettivo";
  cancelObjectiveEditButton.classList.add("hidden");
}

function startEdit(id) {
  const transazione = transazioniCorrenti.find((item) => item.id === id);
  if (!transazione) {
    showMessage("Transazione non trovata.", "error");
    return;
  }

  ensureCategoryOption(transazione.categoria);
  editingId = id;
  formTitle.textContent = "Modifica transazione";
  submitButton.textContent = "Aggiorna transazione";
  cancelEditButton.classList.remove("hidden");

  form.querySelector(`input[name="tipo"][value="${transazione.tipo}"]`).checked = true;
  document.getElementById("importo").value = transazione.importo;
  dateInput.value = normalizeMonth(transazione.data);
  categorySelect.value = transazione.categoria;
  document.getElementById("nota").value = transazione.nota || "";
  document.getElementById("evitabile").checked = transazione.evitabile;

  clearMessage();
  form.scrollIntoView({ behavior: "smooth", block: "start" });
}

async function deleteTransazione(id) {
  const transazione = transazioniCorrenti.find((item) => item.id === id);
  const label = transazione ? formatCategory(transazione.categoria) : "questa transazione";
  const confirmed = window.confirm(`Vuoi eliminare "${label}"?`);

  if (!confirmed) {
    return;
  }

  try {
    await api.deleteTransazione(id);
    if (editingId === id) {
      resetForm();
    }
    showMessage("Transazione eliminata.", "ok");
    await refreshData();
  } catch (error) {
    showMessage(error.message, "error");
  }
}

function resetForm() {
  editingId = null;
  form.reset();
  dateInput.value = currentMonth();
  formTitle.textContent = "Aggiungi transazione";
  submitButton.textContent = "Salva transazione";
  cancelEditButton.classList.add("hidden");
}

function ensureCategoryOption(value) {
  const exists = Array.from(categorySelect.options).some((option) => option.value === value);
  if (!value || exists) {
    return;
  }

  const option = document.createElement("option");
  option.value = value;
  option.textContent = formatCategory(value);
  categorySelect.appendChild(option);
}

function formatEuro(value) {
  return new Intl.NumberFormat("it-IT", {
    style: "currency",
    currency: "EUR"
  }).format(Number(value));
}

function formatDate(value) {
  return formatMonth(value);
}

function formatMonth(value) {
  const monthValue = normalizeMonth(value);
  return new Intl.DateTimeFormat("it-IT", {
    month: "long",
    year: "numeric"
  }).format(new Date(`${monthValue}-01T00:00:00`));
}

function currentMonth() {
  const oggi = new Date();
  const meseScorso = new Date(
    oggi.getFullYear(),
    oggi.getMonth() - 1,
    1
  );

  return `${meseScorso.getFullYear()}-${String(meseScorso.getMonth() + 1).padStart(2, "0")}`;
}

function currentCalendarMonth() {
  const oggi = new Date();
  return `${oggi.getFullYear()}-${String(oggi.getMonth() + 1).padStart(2, "0")}`;
}

async function exportCurrentMonthCsv() {
  const month = exportMonthInput.value;
  if (!month) {
    showMessage("Seleziona un mese da esportare.", "error");
    return;
  }

  exportCsvButton.disabled = true;
  try {
    const { blob, filename } = await api.downloadExportCsv(month);
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
    showMessage(`Export completato: ${filename}`, "ok");
  } catch (error) {
    showMessage(error.message, "error");
  } finally {
    exportCsvButton.disabled = false;
  }
}

function normalizeMonth(value) {
  return String(value).slice(0, 7);
}

function formatCategory(value) {
  return String(value).replaceAll("_", " ");
}

function showMessage(text, type) {
  message.textContent = text;
  message.className = `message ${type}`;
}

function clearMessage() {
  message.textContent = "";
  message.className = "message";
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

checkBackend();
refreshData();
