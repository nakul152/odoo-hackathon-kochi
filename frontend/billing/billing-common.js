/* Shared helpers for the billing pages. Needs /static/js/api.js loaded first. */
const money = (n) => "₹" + Number(n || 0).toLocaleString("en-IN",
  { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const statusBadge = (s) => `<span class="badge ${esc(s)}">${esc(s)}</span>`;

// Today's date in the user's own time zone, as YYYY-MM-DD.
function todayLocal() {
  const d = new Date();
  d.setMinutes(d.getMinutes() - d.getTimezoneOffset());
  return d.toISOString().slice(0, 10);
}

// Turn server errors (plain text, or validation objects) into readable sentences.
function plainMessages(raw) {
  const list = Array.isArray(raw) ? raw : [raw];
  return list.map((m) => {
    if (typeof m === "string") return m;
    if (m && m.msg) return `${(m.loc || []).slice(1).join(" ")}: ${m.msg}`.replace(/^: /, "");
    return "Something went wrong";
  });
}

function say(el, messages, type = "success") {
  showMessage(el, plainMessages(messages).map(esc), type);
  el.scrollIntoView({ behavior: "smooth", block: "nearest" });
}
function sayError(el, err) {
  say(el, err && err.messages ? err.messages : "Something went wrong", "error");
}
function clearMsg(el) { el.className = "msg"; el.innerHTML = ""; }