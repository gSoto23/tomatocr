// CONFIGURACIÓN SUPABASE
const SUB_URL = "https://mojjaegqkphbncklzxxq.supabase.co";
const SUB_KEY = "sb_publishable_9AuuiT9k_9c0cAsOwBEoOw_36ebUzfb";
const supabaseClient = supabase.createClient(SUB_URL, SUB_KEY);

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
    logo.src = "./LogoTomatoW.png";
    localStorage.setItem("tomato_theme", "dark");
  } else {
    document.body.classList.remove("dark-mode");
    logo.src = "./LogoTomatoB.png";
    localStorage.setItem("tomato_theme", "light");
  }
}

// --- 1. Seguridad con PIN desde Supabase Cloud ---
async function checkAccess() {
  const sessionActive = sessionStorage.getItem("tomato_session");
  if (sessionActive) return true;

  const userPin = prompt("🔑 Ingrese el PIN de acceso (Cloud):");
  if (!userPin) return false;

  const { data, error } = await supabaseClient
      .from('config_global')
      .select('valor')
      .eq('clave', 'pin_acceso')
      .single();

  if (data && data.valor === userPin) {
    sessionStorage.setItem("tomato_session", "true");
    return true;
  } else {
    alert("❌ PIN Incorrecto. Acceso denegado.");
    document.body.innerHTML = "<div style='color:white; text-align:center; padding-top:100px; font-family:sans-serif;'><h1>Acceso Protegido</h1><button onclick='location.reload()' style='background:white; color:black; padding:10px 20px; border-radius:10px; border:none; cursor:pointer;'>Reintentar</button></div>";
    return false;
  }
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
  if (!state.client.name.trim()) return alert("⚠️ Ingrese el nombre del cliente antes de guardar.");

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
    items: state.items
  };

  const { error } = await supabaseClient.from('cotizaciones').upsert(record, { onConflict: 'numero_cotizacion' });

  if (error) alert("Error Supabase: " + error.message);
  else {
    alert("✅ Sincronizado en la nube (Supabase)");
    saveCounter(loadCounter() + 1);
    renderRecent();
  }
}

async function renderRecent() {
  const { data, error } = await supabaseClient.from('cotizaciones').select('*').order('created_at', { ascending: false }).limit(20);
  if (error) return;

  $("recentBody").innerHTML = data.map(r => `
    <tr>
      <td class="font-bold">${r.numero_cotizacion}</td>
      <td>${escapeHtml(r.cliente_nombre)}</td>
      <td class="muted">${r.fecha_emision}</td>
      <td class="text-right font-bold">${formatMoney(r.total, r.moneda)}</td>
      <td class="text-right">
        <button class="btn py-1 px-3 text-xs" onclick="loadFromSQL('${r.id}')">Cargar</button>
      </td>
    </tr>
  `).join("") || "<tr><td colspan='5' class='text-center muted'>No hay historial en la nube</td></tr>";
}

window.loadFromSQL = async (id) => {
  const { data, error } = await supabaseClient.from('cotizaciones').select('*').eq('id', id).single();
  if (data) {
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
      taxRate: 13,
      discount: 0
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
    tr.innerHTML = `
      <td><select class="inp" data-f="type">
        <option ${it.type === "Servicio" ? "selected" : ""}>Servicio</option>
        <option ${it.type === "Material" ? "selected" : ""}>Material</option>
      </select></td>
      <td><input class="inp" value="${escapeHtml(it.description)}" data-f="description" /></td>
      <td><input class="inp" value="${escapeHtml(it.unit)}" data-f="unit" /></td>
      <td><input class="inp text-right" type="number" step="0.01" value="${it.qty}" data-f="qty" /></td>
      <td><input class="inp text-right" type="number" step="0.01" value="${it.unitPrice}" data-f="unitPrice" /></td>
      <td class="text-right font-bold">${formatMoney(it.qty * it.unitPrice, state.currency)}</td>
      <td class="text-center"><button class="btn border-none" onclick="removeItem('${it.id}')">✕</button></td>
    `;
    tr.querySelectorAll("[data-f]").forEach(el => el.onchange = (e) => {
      it[el.dataset.f] = (el.type === 'number') ? Number(e.target.value) : e.target.value;
      renderTotals(); renderItems();
    });
    body.appendChild(tr);
  });
}

function renderTotals() {
  const { subtotal, tax, total } = calc();
  $("subtotalView").textContent = formatMoney(subtotal, state.currency);
  $("taxView").textContent = formatMoney(tax, state.currency);
  $("totalView").textContent = formatMoney(total, state.currency);
}

function addItem(type) {
  state.items.push({ id: crypto.randomUUID(), type, description: "", unit: type === "Material" ? "Unidad" : "Visita", qty: 1, unitPrice: 0 });
  renderItems(); renderTotals();
}

function removeItem(id) {
  state.items = state.items.filter(x => x.id !== id);
  renderItems(); renderTotals();
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
  renderItems(); renderTotals(); renderRecent();
}

function loadCounter() { return parseInt(localStorage.getItem(COUNTER_KEY) || "0"); }
function saveCounter(n) { localStorage.setItem(COUNTER_KEY, String(n)); }

function init() {
  const n = loadCounter() + 1;
  state = {
    quoteNumber: `TCR-${new Date().getFullYear()}-${String(n).padStart(4, '0')}`,
    issueDate: new Date().toISOString().split('T')[0],
    validDays: 15, currency: "CRC", serviceType: "Jardinería", frequency: "Por demanda",
    client: { name: "", id: "", email: "", phone: "", address: "" },
    notes: "", terms: "1. Validez: 15 días.\n2. Incluye mano de obra.",
    taxEnabled: true, taxRate: 13, discount: 0,
    items: [{ id: crypto.randomUUID(), type: "Servicio", description: "", unit: "Visita", qty: 1, unitPrice: 0 }]
  };
  bindForm();
}

function wireListeners() {
  initTheme();
  $("btnSave").onclick = saveToSQL;
  $("btnAddService").onclick = () => addItem("Servicio");
  $("btnAddMaterial").onclick = () => addItem("Material");
  $("btnNew").onclick = () => confirm("¿Nueva cotización?") && init();
  $("btnDuplicate").onclick = () => {
    state.quoteNumber = `TCR-${new Date().getFullYear()}-${String(loadCounter() + 1).padStart(4, '0')}`;
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

  const clientInputs = ["clientName", "clientId", "clientEmail", "clientPhone", "clientAddress"];
  clientInputs.forEach(id => {
    $(id).addEventListener("input", (e) => {
      state.client[id.replace("client", "").toLowerCase()] = e.target.value;
    });
  });
}

function escapeHtml(s) { return String(s || "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;"); }

function exportPDF() {
  if (!state.client.name.trim()) return alert("Nombre de cliente requerido.");
  const totals = calc();
  const win = window.open("", "_blank");
  win.document.write(buildPrintableHTML({...state, totals}));
  win.document.close();
  win.onload = () => { win.focus(); win.print(); };
}

function buildPrintableHTML(data) {
  const rows = data.items.map((it, i) => `
    <tr>
      <td>${i + 1}</td>
      <td><strong>${it.type}</strong>: ${escapeHtml(it.description)}</td>
      <td>${escapeHtml(it.unit)}</td>
      <td align="right">${it.qty}</td>
      <td align="right">${formatMoney(it.unitPrice, data.currency)}</td>
      <td align="right"><strong>${formatMoney(it.qty * it.unitPrice, data.currency)}</strong></td>
    </tr>
  `).join("");

  const notesContent = (data.notes || "").trim();
  const notesHtml = notesContent
      ? `<div style="margin-top: 20px"><strong>Notas y Alcance:</strong><br><p style="white-space: pre-wrap; margin-top: 5px;">${escapeHtml(notesContent)}</p></div>`
      : "";

  return `<html><head><title>Cotización ${data.quoteNumber}</title><style>
    body { font-family: sans-serif; padding: 40px; color: #333; line-height: 1.5; }
    .header { display: flex; justify-content: space-between; border-bottom: 2px solid #000; padding-bottom: 20px; align-items: center; }
    .logo { height: 50px; }
    .info-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin: 20px 0; }
    .box { border: 1px solid #eee; padding: 15px; border-radius: 8px; background: #fcfcfc; }
    table { width: 100%; border-collapse: collapse; margin-top: 20px; }
    th { background: #f4f4f4; text-align: left; text-transform: uppercase; font-size: 11px; padding: 12px; }
    td { padding: 12px; border-bottom: 1px solid #eee; font-size: 13px; }
    .totals { margin-left: auto; width: 280px; margin-top: 20px; }
    .total-row { display: flex; justify-content: space-between; padding: 5px 0; }
    .grand-total { border-top: 2px solid #000; padding-top: 10px; font-weight: bold; font-size: 18px; }
    .footer { margin-top: 50px; font-size: 11px; color: #666; text-align: center; border-top: 1px solid #eee; padding-top: 20px; }
    .info-table { width: 100%; border: none; margin-top: 8px; }
    .info-table td { border: none; padding: 2px 0; font-size: 12.5px; vertical-align: top; }
    .info-table td.label { color: #666; font-weight: bold; width: 85px; }
  </style></head><body>
    <div class="header"><img src="./LogoTomatoB.png" class="logo"><div style="text-align: right"><h2 style="margin:0">COTIZACIÓN</h2><div style="font-weight: bold;">${data.quoteNumber}</div></div></div>
    <div class="info-grid">
      <div class="box"><strong>CLIENTE:</strong><table class="info-table">
        <tr><td class="label">Cliente:</td><td>${escapeHtml(data.client.name)}</td></tr>
        <tr><td class="label">Contacto:</td><td>${escapeHtml(data.client.id)}</td></tr>
        <tr><td class="label">Dirección:</td><td>${escapeHtml(data.client.address)}</td></tr>
        <tr><td class="label">Tel:</td><td>${escapeHtml(data.client.phone)}</td></tr>
      </table></div>
      <div class="box"><strong>DETALLES:</strong><table class="info-table">
        <tr><td class="label">Fecha:</td><td>${data.issueDate}</td></tr>
        <tr><td class="label">Servicio:</td><td>${data.serviceType}</td></tr>
        <tr><td class="label">Validez:</td><td>${data.validDays} días naturales</td></tr>
      </table></div>
    </div>
    <table><thead><tr><th>#</th><th>Descripción</th><th>Unidad</th><th align="right">Cant</th><th align="right">Precio</th><th align="right">Total</th></tr></thead><tbody>${rows}</tbody></table>
    <div class="totals">
      <div class="total-row"><span>Subtotal:</span><span>${formatMoney(data.totals.subtotal, data.currency)}</span></div>
      <div class="total-row"><span>IVA (${data.taxRate}%):</span><span>${formatMoney(data.totals.tax, data.currency)}</span></div>
      <div class="total-row grand-total"><span>TOTAL:</span><span>${formatMoney(data.totals.total, data.currency)}</span></div>
    </div>
    ${notesHtml}
    <div style="margin-top: 20px"><strong>Términos y Condiciones:</strong><br><p style="white-space: pre-wrap; margin-top: 5px;">${escapeHtml(data.terms)}</p></div>
    <div class="footer">TOMATO CR - Jardinería · Paisajismo · Mantenimiento<br>WhatsApp: +506 7080 8613 | www.tomatocr.com | Alajuela, Costa Rica</div>
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