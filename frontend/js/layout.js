const MENU = [
  { href: "dashboard.html",     label: "Dashboard",          roles: ["admin", "staff"] },
  { href: "products.html",      label: "Products & Plans",   roles: ["admin", "staff"] },
  { href: "subscriptions.html", label: "Subscriptions",      roles: ["admin", "staff"] },
  { href: "invoices.html",      label: "Invoices",           roles: ["admin", "staff"] },
  { href: "payments.html",      label: "Payments",           roles: ["admin", "staff"] },
  { href: "discounts.html",     label: "Discounts",          roles: ["admin"] },
  { href: "staff.html",         label: "Staff",              roles: ["admin"] },
  { href: "portal.html",        label: "My Account",         roles: ["customer"] },
];

function initLayout(activeHref) {
  const user = getUser();
  if (!getToken() || !user) { window.location.href = "/static/login.html"; return; }
  const links = MENU.filter(m => m.roles.includes(user.role))
    .map(m => `<a class="nav ${m.href === activeHref ? "active" : ""}" href="/static/${m.href}">${m.label}</a>`)
    .join("");
  document.getElementById("sidebar").className = "sidebar";
  document.getElementById("sidebar").innerHTML = `
    <div class="brand">Brightloop</div>
    ${links}
    <div class="user">${user.name}<br><small>${user.role}</small>
      <button class="btn secondary small" onclick="logout()">Log out</button>
    </div>`;
}