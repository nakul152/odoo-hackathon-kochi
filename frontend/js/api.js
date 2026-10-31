function getToken() { return localStorage.getItem("token"); }
function getUser() {
  try { return JSON.parse(localStorage.getItem("user")); } catch { return null; }
}
function logout() {
  localStorage.removeItem("token");
  localStorage.removeItem("user");
  window.location.href = "/static/login.html";
}

// Call the backend. Throws { messages: [...] } with friendly messages on error.
async function api(path, method = "GET", body = null) {
  const headers = { "Content-Type": "application/json" };
  if (getToken()) headers["Authorization"] = "Bearer " + getToken();
  let res;
  try {
    res = await fetch(path, { method, headers, body: body ? JSON.stringify(body) : null });
  } catch {
    throw { messages: ["Cannot reach the server. Is it running?"] };
  }
  let data = {};
  try { data = await res.json(); } catch {}
  if (res.status === 401 && !path.startsWith("/auth/login")) { logout(); }
  if (!res.ok) {
    const d = data.detail;
    throw { messages: Array.isArray(d) ? d : [d || "Something went wrong"] };
  }
  return data;
}

function showMessage(el, messages, type) {
  const list = Array.isArray(messages) ? messages : [messages];
  el.className = "msg " + type;
  el.innerHTML = "<ul>" + list.map(m => "<li>" + m + "</li>").join("") + "</ul>";
}