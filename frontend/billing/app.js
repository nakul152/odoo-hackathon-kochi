const API = "/billing";
let currentView = "invoices";

// ---------- helpers ----------
// Escape text before putting it into the page, so nobody can inject HTML.
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const money = (n) => "₹" + Number(n || 0).toLocaleString("en-IN",
  { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const $ = (id) => document.getElementById(id);
const getToken = () => localStorage.getItem("token") || localStorage.getItem("access_token");

// Today's date in the user's own time zone, as YYYY-MM-DD.
function todayLocal() {
  const d = new Date();
  d.setMinutes(d.getMinutes() - d.getTimezoneOffset());
  return d.toISOString().slice(0, 10);
}

function showMessage(text, kind = "error") {
  const box = $("message");
  if (!text) { box.classList.add("hidden"); return; }
  box.textContent = text;
  box.className = "message " + kind;
  box.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

// Turns the server's error reply into one readable sentence.
function errorText(data, status) {
  if (data && typeof data.detail === "string") return data.detail;
  if (data && Array.isArray(data.detail)) {
    return data.detail.map((d) => typeof d === "string"
      ? d : `${(d.loc || []).slice(1).join(" ")}: ${d.msg}`).join("; ");
  }
  return `Something went wrong (code ${status})`;
}

async function api(path, options = {}) {
  const headers = { "Content-Type": "application/json" };
  const token = getToken();
  if (token) headers["Authorization"] = "Bearer " + token;
  const url = path.startsWith("/auth") ? path : API + path;
  let res;
  try {
    res = await fetch(url, { ...options, headers });
  } catch {
    throw new Error("Cannot reach the server. Is it running?");
  }
  let data = null;
  try { data = await res.json(); } catch { /* empty reply */ }
  if (!res.ok) {
    if (res.status === 401) {          // not logged in, or the session ran out
      localStorage.removeItem("token");
      localStorage.removeItem("access_token");
      showLoggedOut();
    }
    const err = new Error(errorText(data, res.status));
    err.status = res.status;
    throw err;
  }
  return data;
}

// ---------- login state ----------
function showLoggedOut() {
  document.body.dataset.role = "";
  $("app").classList.add("hidden");
  $("userbar").classList.add("hidden");
  $("login-card").classList.remove("hidden");
}

function showLoggedIn(user) {
  document.body.dataset.role = user.role;
  $("user-name").textContent = user.name;
  $("user-role").textContent = user.role;
  $("userbar").classList.remove("hidden");
  $("login-card").classList.add("hidden");
  $("app").classList.remove("hidden");

  // Link back to the team dashboard (skipped if index.html has no such link).
  const home = $("home-link");
  if (home) home.href = user.role === "customer" ? "/static/portal.html" : "/static/dashboard.html";

  const wanted = location.hash.replace("#", "");
  currentView = (user.role !== "customer" && (wanted === "overdue" || wanted === "outstanding"))
    ? wanted : "invoices";
  document.querySelectorAll(".tab").forEach((t) =>
    t.classList.toggle("active", t.dataset.view === currentView));
  loadView();
  if (wanted === "payments" && user.role !== "customer") {
    $("payment-card").scrollIntoView({ behavior: "smooth" });
  }
}

async function startApp() {
  if (!getToken()) { showLoggedOut(); return; }
  try {
    showLoggedIn(await api("/auth/me"));
  } catch (err) {
    showLoggedOut();
    if (err.status !== 401) showMessage(err.message);
  }
}

const badge = (status) => `<span class="badge ${esc(status)}">${esc(status)}</span>`;

// ---------- tables ----------
function renderInvoices(rows) {
  if (!rows.length) return '<p class="empty">No invoices found.</p>';
  const body = rows.map((r) => {
    let actions = "";
    if (r.status === "draft") {
      actions += `<button class="small secondary" data-action="confirm" data-id="${r.id}">Confirm</button>`;
    }
    if (r.status === "confirmed") {
      actions += `<button class="small" data-action="pay" data-id="${r.id}">Pay</button>`;
    }
    if (r.status === "draft" || r.status === "confirmed") {
      actions += `<button class="small danger" data-action="cancel" data-id="${r.id}">Cancel</button>`;
    }
    return `<tr>
      <td>${esc(r.number)}</td><td>${esc(r.customer)}</td>
      <td>${esc(r.issue_date)}</td><td>${esc(r.due_date)}</td>
      <td class="num">${money(r.total)}</td><td>${badge(r.status)}</td>
      <td class="staff-only">${actions}</td></tr>`;
  }).join("");
  return `<table><thead><tr><th>Number</th><th>Customer</th><th>Issued</th><th>Due</th>
    <th class="num">Total</th><th>Status</th><th class="staff-only">Actions</th></tr></thead>
    <tbody>${body}</tbody></table>`;
}

function renderUnpaid(rows) {
  if (!rows.length) return '<p class="empty">Nothing here. Everything is paid up.</p>';
  const body = rows.map((r) => `<tr>
      <td>${esc(r.number)}</td><td>${esc(r.customer)}</td><td>${esc(r.due_date)}</td>
      <td class="num">${money(r.total)}</td><td class="num">${money(r.paid)}</td>
      <td class="num"><strong>${money(r.balance)}</strong></td>
      <td class="${r.days_overdue > 0 ? "late" : ""}">${r.days_overdue > 0 ? r.days_overdue + " days late" : "On time"}</td>
      <td><button class="small" data-action="pay" data-id="${r.id}" data-balance="${r.balance}">Pay</button></td>
    </tr>`).join("");
  return `<table><thead><tr><th>Number</th><th>Customer</th><th>Due</th><th class="num">Total</th>
    <th class="num">Paid</th><th class="num">Balance</th><th>Status</th><th></th></tr></thead>
    <tbody>${body}</tbody></table>`;
}

async function loadView() {
  const area = $("table-area");
  area.innerHTML = '<p class="hint">Loading...</p>';
  $("filter-row").classList.toggle("hidden", currentView !== "invoices");
  try {
    if (currentView === "invoices") {
      const status = $("status-filter").value;
      const query = status ? "?status=" + encodeURIComponent(status) : "";
      area.innerHTML = renderInvoices(await api("/invoices" + query));
    } else {
      const path = currentView === "overdue" ? "/overdue" : "/outstanding";
      area.innerHTML = renderUnpaid(await api(path));
    }
  } catch (err) {
    area.innerHTML = "";
    if (err.status !== 401) showMessage(err.message);
  }
}

// ---------- actions ----------
async function changeStatus(id, action) {
  if (action === "cancel" && !window.confirm("Cancel this invoice? This cannot be undone.")) return;
  showMessage("");
  try {
    const result = await api(`/invoices/${id}/${action}`, { method: "POST" });
    showMessage(`Invoice ${result.number} is now ${result.status}.`, "success");
    loadView();
  } catch (err) {
    showMessage(err.message);
  }
}

function startPayment(id, balance) {
  $("pay-invoice").value = id;
  if (balance) $("pay-amount").value = Number(balance).toFixed(2);
  $("payment-card").scrollIntoView({ behavior: "smooth" });
  $("pay-amount").focus();
}

// ---------- events ----------
document.addEventListener("DOMContentLoaded", () => {
  $("pay-date").max = todayLocal();

  $("login-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    showMessage("");
    try {
      const r = await api("/auth/login", {
        method: "POST",
        body: JSON.stringify({ email: $("login-email").value.trim(),
                               password: $("login-password").value }),
      });
      localStorage.setItem("token", r.access_token);
      localStorage.setItem("user", JSON.stringify(r.user));   // same as the team's login page
      $("login-password").value = "";
      startApp();
    } catch (err) {
      showMessage(err.message);
    }
  });

  $("logout").addEventListener("click", () => {
    localStorage.removeItem("token");
    localStorage.removeItem("access_token");
    localStorage.removeItem("user");
    showMessage("");
    showLoggedOut();
  });

  document.querySelectorAll(".tab").forEach((tab) => {
    tab.addEventListener("click", () => {
      document.querySelectorAll(".tab").forEach((t) => t.classList.remove("active"));
      tab.classList.add("active");
      currentView = tab.dataset.view;
      showMessage("");
      loadView();
    });
  });
  $("status-filter").addEventListener("change", loadView);

  $("table-area").addEventListener("click", (e) => {
    const btn = e.target.closest("button[data-action]");
    if (!btn) return;
    const { action, id, balance } = btn.dataset;
    if (action === "pay") startPayment(id, balance);
    else changeStatus(id, action);
  });

  $("run-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    showMessage("");
    const button = e.target.querySelector("button");
    button.disabled = true;
    try {
      const date = $("run-date").value;
      const r = await api("/run" + (date ? "?today=" + encodeURIComponent(date) : ""), { method: "POST" });
      let html = `<p><strong>${r.invoices_created}</strong> invoice(s) created, ` +
                 `<strong>${r.already_billed}</strong> already billed, ` +
                 `<strong>${r.subscriptions_due}</strong> subscription(s) were due.</p>`;
      if (r.errors.length) {
        html += "<p class='late'>Problems:</p><ul>" +
          r.errors.map((x) => `<li>${esc(x.subscription)}: ${esc(x.error)}</li>`).join("") + "</ul>";
      }
      $("run-result").innerHTML = html;
      loadView();
    } catch (err) {
      showMessage(err.message);
    } finally {
      button.disabled = false;
    }
  });

  $("payment-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    showMessage("");
    const amount = Number($("pay-amount").value);
    if (!(amount > 0)) { showMessage("Enter an amount greater than zero."); return; }
    const body = { method: $("pay-method").value, amount };
    if ($("pay-date").value) body.payment_date = $("pay-date").value;
    if ($("pay-note").value.trim()) body.note = $("pay-note").value.trim();
    const button = e.target.querySelector("button");
    button.disabled = true;
    try {
      const r = await api(`/invoices/${$("pay-invoice").value}/payments`,
                          { method: "POST", body: JSON.stringify(body) });
      showMessage(`Payment saved on ${r.invoice_number}. Invoice is ${r.invoice_status}, ` +
                  `balance remaining ${money(r.balance_remaining)}.`, "success");
      e.target.reset();
      loadView();
    } catch (err) {
      showMessage(err.message);
    } finally {
      button.disabled = false;
    }
  });

  startApp();
});