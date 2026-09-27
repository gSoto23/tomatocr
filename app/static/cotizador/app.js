// CONFIGURACIÓN API INTERNA
const API_URL = "/api/quotes/";

const CRM_API = "/clientes/api/";
// Admin and ventas pick the client's account (Clientes); the client role types the name as before.
const PICKS_ACCOUNT = !!(window.COTIZADOR && window.COTIZADOR.picksAccount);

const COUNTER_KEY = "tomato_quote_counter_v1";
const DRAFT_KEY = "tomato_quote_draft_v1";
const $ = (id) => document.getElementById(id);

let state = {
  quoteNumber: "",
  issueDate: "",
  validDays: 15,
  currency: "CRC",
  serviceType: "Jardinería",
  frequency: "Por demanda",
  client: { name: "", id: "", email: "", phone: "", address: "" },
  accountId: null,
  accountName: "",
  opportunityId: null,
  opportunityTitle: "",
  notes: "",
  terms: "",
  taxEnabled: true,
  taxRate: 13,
  discount: 0,
  items: []
};

// --- 0. Gestión de Tema (Light/Dark) ---
function initTheme() {
  const savedTheme = localStorage.getItem("tomato_theme") || "light";
  applyTheme(savedTheme);

  $("btnTheme").onclick = () => {
    const isDark = document.body.classList.contains("dark-mode");
    applyTheme(isDark ? "light" : "dark");
  };
}

function applyTheme(theme) {
  const logo = $("mainLogo");
  if (theme === "dark") {
    document.body.classList.add("dark-mode");
    logo.src = "/static/cotizador/LogoTomatoW.png";
    localStorage.setItem("tomato_theme", "dark");
  } else {
    document.body.classList.remove("dark-mode");
    logo.src = "/static/cotizador/LogoTomatoB.png";
    localStorage.setItem("tomato_theme", "light");
  }
}

// --- 1. Seguridad ---
// Evaluada directamente en el router via Depends(get_current_user)
async function checkAccess() {
  return true;
}

// --- 2. Lógica de Negocio y Supabase SQL ---
function calc() {
  const subtotal = state.items.reduce((acc, it) => acc + (it.qty * it.unitPrice), 0);
  const discount = Math.max(0, Number(state.discount || 0));
  const taxableBase = Math.max(0, subtotal - discount);
  const tax = state.taxEnabled ? taxableBase * (state.taxRate / 100) : 0;
  const total = taxableBase + tax;

  autoSaveDraft();
  return { subtotal, discount, tax, total };
}

async function saveToSQL() {
  if (PICKS_ACCOUNT && !state.accountId) return showToast("Elija la cuenta del cliente (o créela) antes de guardar.", "error");
  if (!state.client.name.trim()) return showToast("Ingrese el nombre del cliente antes de guardar.", "error");

  const { subtotal, tax, total } = calc();
  const record = {
    numero_cotizacion: state.quoteNumber,
    fecha_emision: state.issueDate,
    cliente_nombre: state.client.name,
    cliente_datos: state.client,
    moneda: state.currency,
    tipo_servicio: state.serviceType,
    frecuencia: state.frequency,
    validez_dias: state.validDays,
    notes: state.notes,
    terminos: state.terms,
    subtotal, iva: tax, total,
    discount: Number(state.discount || 0),
    tax_rate: Number(state.taxRate || 0),
    items: state.items,
    account_id: state.accountId,
    opportunity_id: state.opportunityId
  };

  const response = await fetch(API_URL, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(record)
  });

  if (!response.ok) {
    let detail = response.statusText;
    try { detail = (await response.json()).detail || detail; } catch (e) {}
    showToast("Error guardando: " + detail, "error");
  } else {
    showToast("Sincronizado en el servidor", "success");
    renderRecent();
  }
}

async function renderRecent() {
  const response = await fetch(API_URL);
  if (!response.ok) return;
  const data = await response.json();

  $("recentBody").innerHTML = data.map(r => `
    <tr>
      <td class="font-bold">${r.numero_cotizacion}</td>
      <td>${escapeHtml(r.cliente_nombre)}</td>
      ${PICKS_ACCOUNT ? `<td>${escapeHtml(r.account_name || "—")}</td>` : ""}
      <td class="muted">${r.fecha_emision}</td>
      <td class="text-right font-bold">${formatMoney(r.total || 0, r.moneda)}</td>
      <td class="text-right">
        <button class="btn py-1 px-3 text-xs" onclick="loadFromSQL('${r.id}')">Cargar</button>
      </td>
    </tr>
  `).join("") || `<tr><td colspan='${PICKS_ACCOUNT ? 6 : 5}' class='text-center muted'>No hay historial en la nube</td></tr>`;
}

window.loadFromSQL = async (id) => {
  const response = await fetch(API_URL + id);
  if (response.ok) {
    accountContacts = [];
    const data = await response.json();
    state = {
      quoteNumber: data.numero_cotizacion,
      issueDate: data.fecha_emision,
      client: data.cliente_datos,
      currency: data.moneda,
      serviceType: data.tipo_servicio,
      frequency: data.frecuencia || "Por demanda",
      validDays: data.validez_dias,
      notes: data.notes || "",
      terms: data.terminos || "",
      items: data.items,
      taxEnabled: data.iva > 0,
      taxRate: data.tax_rate ?? 13,
      discount: data.discount || 0,
      accountId: data.account_id || null,
      accountName: data.account_name || "",
      opportunityId: data.opportunity_id || null,
      opportunityTitle: ""
    };
    bindForm();
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }
};

// --- 3. UI y Utilidades ---
function formatMoney(amount, currency) {
  const locale = currency === "USD" ? "en-US" : "es-CR";
  return new Intl.NumberFormat(locale, { style: "currency", currency }).format(amount);
}

function renderItems() {
  const body = $("itemsBody");
  body.innerHTML = "";
  state.items.forEach(it => {
    const tr = document.createElement("tr");
    tr.className = "align-top";
    tr.innerHTML = `
      <td><select class="inp" data-f="type">
        <option ${it.type === "Servicio" ? "selected" : ""}>Servicio</option>
        <option ${it.type === "Material" ? "selected" : ""}>Material</option>
      </select></td>
      <td><textarea class="inp" rows="${Math.min(6, Math.max(1, String(it.description || "").split("\n").length))}" data-f="description"
        placeholder="Qué incluye este ítem">${escapeHtml(it.description)}</textarea></td>
      <td><input class="inp" value="${escapeHtml(it.unit)}" data-f="unit" /></td>
      <td><input class="inp text-right" type="number" min="0" step="0.01" value="${it.qty}" data-f="qty" /></td>
      <td><input class="inp text-right" type="number" min="0" step="0.01" value="${it.unitPrice}" data-f="unitPrice" /></td>
      <td class="text-right font-bold pt-3">${formatMoney(it.qty * it.unitPrice, state.currency)}</td>
      <td class="text-center whitespace-nowrap">
        <button class="btn border-none px-2" title="Duplicar ítem" onclick="duplicateItem('${it.id}')">⧉</button>
        <button class="btn border-none px-2" title="Quitar ítem" onclick="removeItem('${it.id}')">✕</button>
      </td>
    `;
    tr.querySelectorAll("[data-f]").forEach(el => {
      el.onchange = (e) => {
        it[el.dataset.f] = (el.type === "number") ? Number(e.target.value) : e.target.value;
        renderTotals(); renderItems();
      };
      if (el.tagName === "TEXTAREA") {
        el.oninput = (e) => {  // grow while typing, without re-rendering the table
          it.description = e.target.value;
          e.target.rows = Math.min(6, Math.max(1, e.target.value.split("\n").length));
          renderQuality();
        };
      }
    });
    body.appendChild(tr);
  });
}

function renderTotals() {
  const { subtotal, discount, tax, total } = calc();
  $("subtotalView").textContent = formatMoney(subtotal, state.currency);
  $("taxView").textContent = formatMoney(tax, state.currency);
  $("totalView").textContent = formatMoney(total, state.currency);
  renderQuality();
}

function addItem(type) {
  state.items.push({ id: crypto.randomUUID(), type, description: "", unit: type === "Material" ? "Unidad" : "Visita", qty: 1, unitPrice: 0 });
  renderItems(); renderTotals();
}

function removeItem(id) {
  state.items = state.items.filter(x => x.id !== id);
  renderItems(); renderTotals();
}

function duplicateItem(id) {
  const index = state.items.findIndex(x => x.id === id);
  if (index < 0) return;
  state.items.splice(index + 1, 0, { ...state.items[index], id: crypto.randomUUID() });
  renderItems(); renderTotals();
}

// --- Revisión de "cotización completa" ---
function checkQuote() {
  const errors = [], warnings = [];
  const c = state.client || {};
  if (PICKS_ACCOUNT && !state.accountId) errors.push("Elegir la cuenta del cliente");
  if (!String(c.name || "").trim()) errors.push("Nombre del cliente");
  if (!state.issueDate) errors.push("Fecha de emisión");
  if (!(Number(state.validDays) > 0)) errors.push("Validez en días");
  if (!state.items.length) errors.push("Al menos un ítem");
  state.items.forEach((it, i) => {
    const n = i + 1;
    if (!String(it.description || "").trim()) errors.push(`Descripción del ítem ${n}`);
    if (!(Number(it.qty) > 0)) errors.push(`Cantidad del ítem ${n}`);
    if (!(Number(it.unitPrice) > 0)) errors.push(`Precio del ítem ${n}`);
    if (!String(it.unit || "").trim()) warnings.push(`Unidad del ítem ${n}`);
  });
  const { subtotal, discount } = calc();
  if (discount > subtotal) errors.push("El descuento es mayor que el subtotal");
  if (!String(c.id || "").trim()) warnings.push("Nombre del contacto");
  if (!String(c.email || "").trim() && !String(c.phone || "").trim()) warnings.push("Correo o teléfono del cliente");
  if (!String(c.address || "").trim()) warnings.push("Dirección o ubicación del servicio");
  if (!String(state.notes || "").trim()) warnings.push("Notas / alcance");
  if (!String(state.terms || "").trim()) warnings.push("Términos");
  return { errors, warnings };
}

function renderQuality() {
  const panel = $("qualityPanel");
  if (!panel) return;
  const { errors, warnings } = checkQuote();
  const list = (items, color) => items.map(t => `<li class="${color}">${escapeHtml(t)}</li>`).join("");
  if (!errors.length && !warnings.length) {
    panel.innerHTML = `<div class="rounded-md border border-green-600/40 p-3 text-sm text-green-700">✓ Cotización completa, lista para exportar.</div>`;
  } else {
    panel.innerHTML = `<div class="rounded-md border p-3 text-sm">
      ${errors.length ? `<p class="font-semibold text-red-600">Falta para exportar:</p><ul class="list-disc pl-5">${list(errors, "text-red-600")}</ul>` : `<p class="font-semibold text-green-700">✓ Lista para exportar</p>`}
      ${warnings.length ? `<p class="font-semibold mt-2" style="color:#b45309">Recomendado completar:</p><ul class="list-disc pl-5">${list(warnings, "")}</ul>` : ""}
    </div>`;
  }
  $("btnPDF").disabled = errors.length > 0;
  $("btnPDF").classList.toggle("opacity-50", errors.length > 0);
}

let autoSaveTimer;
function autoSaveDraft() {
  clearTimeout(autoSaveTimer);
  autoSaveTimer = setTimeout(() => {
    localStorage.setItem(DRAFT_KEY, JSON.stringify(state));
  }, 1000);
}

function bindForm() {
  $("quoteNumberPill").textContent = state.quoteNumber;
  $("issueDate").value = state.issueDate;
  $("validDays").value = state.validDays;
  $("currency").value = state.currency;
  $("serviceType").value = state.serviceType;
  $("frequency").value = state.frequency;
  $("clientName").value = state.client.name || "";
  $("clientId").value = state.client.id || "";
  $("clientEmail").value = state.client.email || "";
  $("clientPhone").value = state.client.phone || "";
  $("clientAddress").value = state.client.address || "";
  $("notes").value = state.notes || "";
  $("terms").value = state.terms || "";
  $("taxEnabled").checked = state.taxEnabled;
  $("taxRate").value = state.taxRate;
  $("discount").value = state.discount;
  renderAccount();
  renderItems(); renderTotals(); renderRecent();
}

async function init() {
  accountContacts = [];
  let n = 1;
  try {
    const res = await fetch(API_URL + "next-number");
    if (res.ok) {
      const data = await res.json();
      n = data.next_number || 1;
    }
  } catch (e) {
    console.error("Error fetching next number", e);
  }

  state = {
    quoteNumber: `TCR-${new Date().getFullYear()}-${String(n).padStart(4, '0')}`,
    issueDate: new Date().toISOString().split('T')[0],
    validDays: 15, currency: "CRC", serviceType: "Jardinería", frequency: "Por demanda",
    client: { name: "", id: "", email: "", phone: "", address: "" },
    accountId: null, accountName: "", opportunityId: null, opportunityTitle: "",
    notes: "", terms: "1. Validez: 15 días.\n2. Incluye mano de obra.",
    taxEnabled: true, taxRate: 13, discount: 0,
    items: [{ id: crypto.randomUUID(), type: "Servicio", description: "", unit: "Visita", qty: 1, unitPrice: 0 }]
  };
  bindForm();
  await loadOpportunityFromUrl();
}

// --- Cuenta del cliente (Clientes) ---
let accountContacts = [];

function renderAccount() {
  if (!PICKS_ACCOUNT) return;
  const chosen = !!state.accountId;
  $("accountChosen").classList.toggle("hidden", !chosen);
  $("accountSearchBox").classList.toggle("hidden", chosen);
  $("accountChosenName").textContent = state.accountName || "";
  $("opportunityBadge").textContent = state.opportunityId ? `Oportunidad: ${state.opportunityTitle || "#" + state.opportunityId}` : "";
  $("contactPickerBox").style.display = chosen ? "" : "none";
  renderQuality();
  if (chosen && !accountContacts.length) {
    fetch(CRM_API + "cuentas/" + state.accountId).then(r => r.ok ? r.json() : null).then(acc => {
      if (acc) { accountContacts = acc.contacts; renderContactOptions(); }
    });
  }
}

function renderContactOptions() {
  const select = $("contactSelect");
  select.innerHTML = `<option value="">— Sin contacto —</option>` + accountContacts.map(c =>
    `<option value="${c.id}">${escapeHtml(c.name)}${c.email ? " · " + escapeHtml(c.email) : ""}</option>`).join("");
  const current = accountContacts.find(c => c.name === state.client.id);
  select.value = current ? String(current.id) : "";
}

function applyContact(contact) {
  state.client.id = contact ? contact.name : "";
  state.client.email = contact && contact.email ? contact.email : "";
  state.client.phone = contact && contact.phone ? contact.phone : "";
  $("clientId").value = state.client.id;
  $("clientEmail").value = state.client.email;
  $("clientPhone").value = state.client.phone;
  renderQuality();
}

function selectAccount(account, keepOpportunity = false) {
  state.accountId = account.id;
  state.accountName = account.name;
  if (!keepOpportunity) { state.opportunityId = null; state.opportunityTitle = ""; }
  state.client.name = account.name;
  if (account.address && !state.client.address) state.client.address = account.address;
  $("clientName").value = state.client.name;
  $("clientAddress").value = state.client.address || "";
  accountContacts = account.contacts || [];
  applyContact(accountContacts.find(c => c.is_primary) || accountContacts[0] || null);
  $("accountResults").classList.add("hidden");
  $("accountSimilar").classList.add("hidden");
  $("accountSearch").value = "";
  renderAccount();
  renderContactOptions();
  autoSaveDraft();
}

let searchTimer = null;
function searchAccounts(query) {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(async () => {
    const response = await fetch(CRM_API + "cuentas?q=" + encodeURIComponent(query));
    if (!response.ok) return;
    const accounts = await response.json();
    window._accountResults = accounts;
    const create = query.trim()
      ? `<button type="button" class="block w-full text-left px-3 py-2 font-semibold hover:bg-gray-100" onclick="createAccount(false)">+ Crear cuenta «${escapeHtml(query.trim())}»</button>` : "";
    $("accountResults").innerHTML = accounts.map((a, i) =>
      `<button type="button" class="block w-full text-left px-3 py-2 hover:bg-gray-100" onclick="selectAccount(window._accountResults[${i}])">
        ${escapeHtml(a.name)}${a.tax_id ? ` <span class="text-xs text-gray-500">· ${escapeHtml(a.tax_id)}</span>` : ""}</button>`).join("") + create;
    $("accountResults").classList.toggle("hidden", !accounts.length && !create);
  }, 250);
}

window.selectAccount = selectAccount;
window.createAccount = async (confirmed) => {
  const name = $("accountSearch").value.trim();
  if (!name) return;
  const response = await fetch(CRM_API + "cuentas", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, confirm: confirmed })
  });
  const data = await response.json();
  if (response.status === 409) {
    window._similarAccounts = data.similar;
    $("accountSimilar").innerHTML = `<p class="font-semibold">Ya hay cuentas parecidas. ¿Es alguna de estas?</p>` +
      data.similar.map((a, i) => `<button type="button" class="btn py-1 px-3 text-xs mt-2 mr-2" onclick="selectAccount(window._similarAccounts[${i}])">Usar «${escapeHtml(a.name)}»</button>`).join("") +
      `<div class="mt-3"><button type="button" class="btn py-1 px-3 text-xs" onclick="createAccount(true)">Es otro cliente: crear «${escapeHtml(name)}»</button></div>`;
    $("accountSimilar").classList.remove("hidden");
    $("accountResults").classList.add("hidden");
    return;
  }
  if (!response.ok) return showToast(data.detail || "No se pudo crear la cuenta", "error");
  showToast(`Cuenta creada: ${data.name}`, "success");
  selectAccount(data);
};

async function loadOpportunityFromUrl() {
  const id = new URLSearchParams(window.location.search).get("opportunity_id");
  if (!PICKS_ACCOUNT || !id) return;
  const response = await fetch(CRM_API + "oportunidades/" + encodeURIComponent(id));
  if (!response.ok) return showToast("No se encontró la oportunidad", "error");
  const data = await response.json();
  state.opportunityId = data.id;
  state.opportunityTitle = data.title;
  selectAccount(data.account, true);
}

function wireListeners() {
  initTheme();
  $("btnSave").onclick = saveToSQL;
  $("btnAddService").onclick = () => addItem("Servicio");
  $("btnAddMaterial").onclick = () => addItem("Material");
  $("btnNew").onclick = () => confirm("¿Nueva cotización?") && init();
  $("btnDuplicate").onclick = async () => {
    let n = 1;
    try {
      const res = await fetch(API_URL + "next-number");
      if (res.ok) {
        const data = await res.json();
        n = data.next_number || 1;
      }
    } catch (e) {}
    state.quoteNumber = `TCR-${new Date().getFullYear()}-${String(n).padStart(4, '0')}`;
    state.issueDate = new Date().toISOString().split('T')[0];
    bindForm();
  };
  $("btnClearDraft").onclick = () => confirm("¿Borrar borrador?") && (localStorage.removeItem(DRAFT_KEY) || init());
  $("btnRefreshRecent").onclick = renderRecent;
  $("btnPDF").onclick = exportPDF;

  const simpleInputs = ["issueDate", "validDays", "currency", "serviceType", "frequency", "taxEnabled", "taxRate", "discount", "notes", "terms"];
  simpleInputs.forEach(id => {
    $(id).addEventListener("input", (e) => {
      state[id] = e.target.type === "checkbox" ? e.target.checked : e.target.value;
      renderTotals();
      if (id === "currency") renderItems();
    });
  });

  if (PICKS_ACCOUNT) {
    $("accountSearch").addEventListener("input", (e) => searchAccounts(e.target.value));
    $("accountSearch").addEventListener("focus", (e) => searchAccounts(e.target.value));
    $("btnChangeAccount").onclick = () => {
      state.accountId = null; state.accountName = ""; state.opportunityId = null; state.opportunityTitle = "";
      accountContacts = [];
      renderAccount();
      $("accountSearch").focus();
    };
    $("contactSelect").addEventListener("change", (e) => {
      applyContact(accountContacts.find(c => String(c.id) === e.target.value) || null);
      autoSaveDraft();
    });
  }

  const clientInputs = ["clientName", "clientId", "clientEmail", "clientPhone", "clientAddress"];
  clientInputs.forEach(id => {
    $(id).addEventListener("input", (e) => {
      state.client[id.replace("client", "").toLowerCase()] = e.target.value;
      renderQuality();
    });
  });
}

function escapeHtml(s) {
  return String(s ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
}

window.showToast = function(message, type = "success") {
  let container = document.getElementById("toastContainer");
  if (!container) {
    container = document.createElement("div");
    container.id = "toastContainer";
    container.className = "fixed bottom-5 right-5 z-50 flex flex-col gap-2";
    document.body.appendChild(container);
  }
  const toast = document.createElement("div");
  const isErr = type === "error";
  toast.className = `px-5 py-3 rounded-lg shadow-xl text-white font-medium text-sm transition-all duration-300 transform translate-y-10 opacity-0 flex items-center gap-3 ${isErr ? 'bg-red-500' : 'bg-green-600'}`;
  toast.innerHTML = isErr 
    ? `<svg class="w-5 h-5 flex-shrink-0" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"></path></svg> <span>${escapeHtml(message)}</span>`
    : `<svg class="w-5 h-5 flex-shrink-0" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M5 13l4 4L19 7"></path></svg> <span>${escapeHtml(message)}</span>`;
  
  container.appendChild(toast);
  
  // Trigger entry animation
  requestAnimationFrame(() => {
    toast.classList.remove("translate-y-10", "opacity-0");
  });

  // Autoremove
  setTimeout(() => {
    toast.classList.add("opacity-0", "translate-y-10");
    setTimeout(() => toast.remove(), 300);
  }, 3500);
};

function exportPDF() {
  const { errors } = checkQuote();
  if (errors.length) return showToast("Complete antes de exportar: " + errors.slice(0, 3).join(", ") + (errors.length > 3 ? "…" : ""), "error");
  const totals = calc();
  const win = window.open("", "_blank");
  if (!win) return showToast("El navegador bloqueó la ventana del PDF. Permita ventanas emergentes para este sitio.", "error");
  win.document.write(buildPrintableHTML({ ...state, totals }));
  win.document.close();
  // Print once the logo has loaded, so it is never missing from the PDF.
  const printWhenReady = () => { win.focus(); win.print(); };
  const logo = win.document.querySelector("img.logo");
  if (logo && !logo.complete) { logo.onload = printWhenReady; logo.onerror = printWhenReady; } else { setTimeout(printWhenReady, 150); }
}

// Issuer data shown on every quote.
const ISSUER = {
  name: "TOMATO COSTA RICA ANY S.R.L.",
  taxId: "3-102-876296",
  address: "Alajuela, Costa Rica",
  phone: "+506 7080 8613",
  web: "www.tomatocr.com",
};

function formatDateCR(iso) {
  if (!iso) return "";
  const [y, m, d] = String(iso).split("-");
  return d && m && y ? `${d}/${m}/${y}` : String(iso);
}

function addDays(iso, days) {
  const date = new Date(`${iso}T12:00:00`);
  if (isNaN(date)) return "";
  date.setDate(date.getDate() + Number(days || 0));
  return date.toISOString().slice(0, 10);
}

function buildPrintableHTML(data) {
  const e = escapeHtml;
  const money = (v) => formatMoney(v, data.currency);
  const c = data.client || {};
  const rows = data.items.map((it, i) => `
    <tr>
      <td class="num">${i + 1}</td>
      <td><span class="tag">${e(it.type)}</span><div class="desc">${e(it.description)}</div></td>
      <td>${e(it.unit)}</td>
      <td class="r">${e(it.qty)}</td>
      <td class="r">${money(it.unitPrice)}</td>
      <td class="r strong">${money(it.qty * it.unitPrice)}</td>
    </tr>`).join("");
  const clientLines = [
    ["Cliente", c.name], ["Contacto", c.id], ["Correo", c.email], ["Teléfono", c.phone], ["Ubicación", c.address],
  ].filter(([, v]) => String(v || "").trim()).map(([k, v]) => `<tr><th>${k}</th><td>${e(v)}</td></tr>`).join("");
  const validUntil = addDays(data.issueDate, data.validDays);
  const notes = String(data.notes || "").trim();
  const terms = String(data.terms || "").trim();
  const discountRow = data.totals.discount > 0
    ? `<tr><th>Descuento</th><td>− ${money(data.totals.discount)}</td></tr>` : "";
  const taxRow = data.taxEnabled
    ? `<tr><th>IVA (${e(data.taxRate)} %)</th><td>${money(data.totals.tax)}</td></tr>`
    : `<tr><th>IVA</th><td>No incluido</td></tr>`;

  return `<!DOCTYPE html><html lang="es"><head><meta charset="utf-8"><title>Cotización ${e(data.quoteNumber)} · ${e(c.name)}</title><style>
    /* margin: 0 hides the browser's own header and footer (URL, date); the page padding lives in .page */
    @page { size: letter; margin: 0; }
    * { box-sizing: border-box; }
    html, body { margin: 0; }
    body { font-family: "Helvetica Neue", Arial, sans-serif; color: #1f2937; font-size: 11pt; line-height: 1.45;
           -webkit-print-color-adjust: exact; print-color-adjust: exact; }
    /* The outer table repeats an empty header and footer on every printed page: that gives
       each page its own top and bottom margin, and room for the fixed footer. */
    table.layout { width: 100%; border-collapse: collapse; }
    table.layout > thead > tr > td { height: 14mm; padding: 0; }
    table.layout > tfoot > tr > td { height: 20mm; padding: 0; }
    table.layout > tbody > tr > td { padding: 0; }
    .page { padding: 0 16mm; }
    .header { display: flex; justify-content: space-between; align-items: flex-start; gap: 16px;
              border-bottom: 3px solid #111; padding-bottom: 12px; }
    .logo { height: 46px; }
    .issuer { font-size: 8.5pt; color: #4b5563; margin-top: 6px; line-height: 1.35; }
    .doc { text-align: right; }
    .doc h1 { margin: 0; font-size: 20pt; letter-spacing: 1px; }
    .doc .number { font-size: 12pt; font-weight: 700; }
    .doc .dates { font-size: 9pt; color: #4b5563; margin-top: 4px; }
    .grid { display: grid; grid-template-columns: 1.3fr 1fr; gap: 12px; margin: 14px 0; }
    .box { border: 1px solid #e5e7eb; border-radius: 6px; padding: 10px 12px; break-inside: avoid; }
    .box h2 { margin: 0 0 6px; font-size: 8.5pt; text-transform: uppercase; letter-spacing: .08em; color: #6b7280; }
    .kv { width: 100%; border-collapse: collapse; }
    .kv th { text-align: left; font-weight: 600; color: #6b7280; width: 30%; padding: 1px 6px 1px 0; vertical-align: top; font-size: 9.5pt; }
    .kv td { padding: 1px 0; font-size: 9.5pt; word-break: break-word; }
    table.items { width: 100%; border-collapse: collapse; margin-top: 6px; }
    table.items thead { display: table-header-group; }  /* repeat the header on every page */
    table.items th { background: #111; color: #fff; text-align: left; font-size: 8.5pt; text-transform: uppercase;
                     letter-spacing: .05em; padding: 7px 8px; }
    table.items td { padding: 8px; border-bottom: 1px solid #e5e7eb; font-size: 10pt; vertical-align: top; }
    table.items tr { break-inside: avoid; page-break-inside: avoid; }  /* never split a row across pages */
    .r { text-align: right; white-space: nowrap; }
    .num { width: 26px; color: #6b7280; }
    .strong { font-weight: 700; }
    .tag { display: inline-block; font-size: 7.5pt; text-transform: uppercase; letter-spacing: .06em; color: #6b7280; }
    .desc { white-space: pre-wrap; word-break: break-word; }
    .keep { break-inside: avoid; page-break-inside: avoid; }
    .summary { display: flex; justify-content: flex-end; margin-top: 10px; }
    .totals { width: 300px; border-collapse: collapse; }
    .totals th { text-align: left; font-weight: 500; color: #4b5563; padding: 4px 0; }
    .totals td { text-align: right; padding: 4px 0; white-space: nowrap; }
    .totals .grand th, .totals .grand td { border-top: 2px solid #111; font-size: 13pt; font-weight: 700; color: #111; padding-top: 8px; }
    .section { margin-top: 16px; }
    .section h2 { font-size: 9pt; text-transform: uppercase; letter-spacing: .08em; color: #6b7280; margin: 0 0 4px; }
    .section p { margin: 0; white-space: pre-wrap; font-size: 9.5pt; }
    .accept { margin-top: 26px; display: grid; grid-template-columns: repeat(3, 1fr); gap: 18px; }
    .accept div { border-top: 1px solid #9ca3af; padding-top: 4px; font-size: 8.5pt; color: #6b7280; }
    .footer { position: fixed; left: 16mm; right: 16mm; bottom: 9mm; border-top: 1px solid #e5e7eb; padding-top: 5px;
              font-size: 8pt; color: #6b7280; display: flex; justify-content: space-between; }
    @media screen { body { background: #f3f4f6; } table.layout { background: #fff; max-width: 216mm; margin: 12px auto; box-shadow: 0 1px 6px rgba(0,0,0,.15); } .footer { position: static; margin: 24px 16mm 0; padding-bottom: 12px; } }
  </style></head><body>
  <table class="layout"><thead><tr><td></td></tr></thead><tfoot><tr><td></td></tr></tfoot><tbody><tr><td><div class="page">
    <div class="header">
      <div>
        <img src="/static/cotizador/LogoTomatoB.png" class="logo" alt="TOMATO">
        <div class="issuer">${ISSUER.name} · Cédula jurídica ${ISSUER.taxId}<br>${ISSUER.address} · ${ISSUER.phone} · ${ISSUER.web}</div>
      </div>
      <div class="doc">
        <h1>COTIZACIÓN</h1>
        <div class="number">${e(data.quoteNumber)}</div>
        <div class="dates">Emitida el ${formatDateCR(data.issueDate)}${validUntil ? `<br>Válida hasta el ${formatDateCR(validUntil)}` : ""}</div>
      </div>
    </div>

    <div class="grid">
      <div class="box"><h2>Cliente</h2><table class="kv">${clientLines}</table></div>
      <div class="box"><h2>Condiciones</h2><table class="kv">
        <tr><th>Servicio</th><td>${e(data.serviceType)}</td></tr>
        <tr><th>Frecuencia</th><td>${e(data.frequency)}</td></tr>
        <tr><th>Moneda</th><td>${e(data.currency)}</td></tr>
        <tr><th>Validez</th><td>${e(data.validDays)} días naturales</td></tr>
      </table></div>
    </div>

    <table class="items">
      <thead><tr><th>#</th><th>Descripción</th><th>Unidad</th><th class="r">Cant.</th><th class="r">Precio unit.</th><th class="r">Total</th></tr></thead>
      <tbody>${rows}</tbody>
    </table>

    <div class="keep">
      <div class="summary"><table class="totals">
        <tr><th>Subtotal</th><td>${money(data.totals.subtotal)}</td></tr>
        ${discountRow}
        ${taxRow}
        <tr class="grand"><th>Total</th><td>${money(data.totals.total)}</td></tr>
      </table></div>
    </div>

    ${notes ? `<div class="section keep"><h2>Alcance y notas</h2><p>${e(notes)}</p></div>` : ""}
    ${terms ? `<div class="section keep"><h2>Términos y condiciones</h2><p>${e(terms)}</p></div>` : ""}

    <div class="keep section">
      <h2>Aceptación del cliente</h2>
      <div class="accept"><div>Nombre</div><div>Firma</div><div>Fecha</div></div>
    </div>

  </div></td></tr></tbody></table>
  <div class="footer"><span>${ISSUER.name} · ${ISSUER.phone} · ${ISSUER.web}</span><span>${e(data.quoteNumber)}</span></div>
  </body></html>`;
}

// --- Inicio ---
async function start() {
  const hasAccess = await checkAccess();
  if (hasAccess) {
    wireListeners();
    init();
  }
}

start();