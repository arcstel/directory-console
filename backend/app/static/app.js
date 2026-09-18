(function () {
  "use strict";

  var state = {
    view: "dashboard",
    page: { users: 1, groups: 1, ous: 1, computers: 1 },
    q: "",
    caches: { ous: null, groups: null, users: null },
    meta: { mode: "", baseDn: "" }
  };

  /* ----------------------------------------------------------------- utils */
  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }
  function $(id) { return document.getElementById(id); }
  function el(html) { var t = document.createElement("template"); t.innerHTML = html.trim(); return t.content.firstElementChild; }

  function toast(msg, type) {
    var t = el('<div class="toast ' + (type || "") + '">' + esc(msg) + "</div>");
    $("toasts").appendChild(t);
    setTimeout(function () { t.style.opacity = "0"; t.style.transition = "opacity .4s"; }, 3200);
    setTimeout(function () { t.remove(); }, 3700);
  }

  async function api(path, opts) {
    var res = await fetch("/api" + path, Object.assign({ headers: { "Content-Type": "application/json" } }, opts || {}));
    var body = null;
    try { body = await res.json(); } catch (e) { body = null; }
    if (!res.ok) {
      var detail = body && body.detail ? body.detail : ("HTTP " + res.status);
      throw new Error(detail);
    }
    return body;
  }

  /* -------------------------------------------------------------- chrome */
  function setMode(mode) {
    var pill = $("modePill");
    pill.className = "pill " + (mode === "ldap" ? "ok" : mode === "mock" ? "mock" : "bad");
    pill.textContent = mode === "ldap" ? "● connected" : mode === "mock" ? "● mock mode" : "● disconnected";
  }

  async function loadMeta() {
    try {
      var h = await api("/health");
      state.meta.mode = h.mode;
      setMode(h.mode);
      var d = await api("/domain");
      state.meta.baseDn = d.base_dn;
      $("baseDn").textContent = d.base_dn;
      $("subtitle").textContent = (d.netbios ? d.netbios + " · " : "") + (h.uri || "");
    } catch (e) {
      setMode("down");
      toast("Cannot reach directory: " + e.message, "err");
    }
  }

  var TITLES = {
    dashboard: ["Dashboard", "Domain overview and identity posture."],
    users: ["Users", "Create, inspect, and manage user accounts."],
    groups: ["Groups", "Security and distribution groups and their membership."],
    ous: ["Organizational Units", "Structure your directory and delegate administration."],
    computers: ["Computers", "Domain-joined computer accounts."],
    governance: ["Governance", "Identity risks, stale access, and privileged accounts."]
  };

  function setView(view) {
    state.view = view;
    state.q = "";
    state.page[view] = state.page[view] || 1;
    Array.prototype.forEach.call($("nav").children, function (b) { b.classList.toggle("active", b.dataset.view === view); });
    $("viewTitle").textContent = TITLES[view][0];
    $("viewSub").textContent = TITLES[view][1];
    $("viewActions").innerHTML = "";
    render();
  }

  function render() {
    var v = $("view");
    if (state.view === "dashboard") return renderDashboard(v);
    if (state.view === "governance") return renderGovernance(v);
    return renderList(v, state.view);
  }

  /* ------------------------------------------------------------ dashboard */
  async function renderDashboard(root) {
    root.innerHTML = '<div class="spinner">Loading domain posture…</div>';
    try {
      var gov = await api("/governance");
      var s = gov.summary;
      root.innerHTML =
        '<div class="grid">' +
        stat(s.users, "Users", "") +
        stat(s.groups, "Groups", "") +
        stat(s.enabled, "Enabled", "ok") +
        stat(s.disabled, "Disabled", "warn") +
        stat(s.privileged, "Privileged", "alert") +
        stat(s.findings, "Findings", "warn") +
        "</div>" +
        '<div class="card"><h3>Top governance findings</h3><div id="dashFindings"></div>' +
        '<div style="margin-top:14px"><button class="btn" id="goGov">Open governance →</button></div></div>';
      var box = $("dashFindings");
      gov.findings.slice(0, 6).forEach(function (f) { box.appendChild(findingRow(f)); });
      if (!gov.findings.length) box.innerHTML = '<div class="empty">No findings. Nice.</div>';
      $("goGov").onclick = function () { setView("governance"); };
    } catch (e) {
      root.innerHTML = '<div class="empty">Failed to load: ' + esc(e.message) + "</div>";
    }
  }
  function stat(value, label, cls) {
    return '<div class="stat ' + cls + '"><b>' + (value == null ? "—" : value) + "</b><span>" + esc(label) + "</span></div>";
  }

  /* ----------------------------------------------------------------- lists */
  async function renderList(root, view) {
    var cfg = {
      users: { path: "/users", cols: ["Name", "Account", "Title", "Department", "Status", "Last logon"], create: "New user" },
      groups: { path: "/groups", cols: ["Group", "Description", "Members", "Type"], create: "New group" },
      ous: { path: "/ous", cols: ["Organizational Unit", "Description"], create: "New OU" },
      computers: { path: "/computers", cols: ["Computer", "OS", "DNS name", "Status", "Last logon"], create: null }
    }[view];

    $("viewActions").innerHTML = cfg.create ? '<button class="btn btn-primary btn-sm" id="createBtn">+ ' + cfg.create + "</button>" : "";
    if (cfg.create) $("createBtn").onclick = function () { openCreate(view); };

    root.innerHTML =
      '<div class="toolbar"><input id="search" type="text" placeholder="Search ' + view + '…" value="' + esc(state.q) + '" /></div>' +
      '<div class="tablewrap" id="tablewrap"><div class="spinner">Loading…</div></div>';

    var search = $("search");
    var timer = null;
    search.oninput = function () {
      state.q = this.value;
      clearTimeout(timer);
      timer = setTimeout(function () { fetchTable(view, cfg); }, 220);
    };
    fetchTable(view, cfg);
  }

  async function fetchTable(view, cfg) {
    var wrap = $("tablewrap");
    if (!wrap) return;
    wrap.innerHTML = '<div class="spinner">Loading…</div>';
    try {
      var page = state.page[view] || 1;
      var data = await api(cfg.path + "?q=" + encodeURIComponent(state.q) + "&page=" + page + "&size=50");
      if (!data.items.length) { wrap.innerHTML = '<div class="empty">No ' + esc(view) + " found" + (state.q ? " for “" + esc(state.q) + "”" : "") + ".</div>"; return; }
      var html = "<table><thead><tr>" + cfg.cols.map(function (c) { return "<th>" + c + "</th>"; }).join("") + "</tr></thead><tbody>";
      data.items.forEach(function (o) { html += rowFor(view, o); });
      html += "</tbody></table>";
      var pages = Math.max(1, Math.ceil(data.total / data.size));
      html += '<div class="pager"><span>' + data.total + " objects · page " + data.page + " / " + pages + "</span>" +
        '<button class="btn btn-sm" id="prevBtn"' + (data.page <= 1 ? " disabled" : "") + ">‹ Prev</button>" +
        '<button class="btn btn-sm" id="nextBtn"' + (data.page >= pages ? " disabled" : "") + ">Next ›</button></div>";
      wrap.innerHTML = html;
      wrap.querySelectorAll("tbody tr").forEach(function (tr) { tr.onclick = function () { openObject(tr.dataset.dn); }; });
      $("prevBtn").onclick = function () { state.page[view] = data.page - 1; fetchTable(view, cfg); };
      $("nextBtn").onclick = function () { state.page[view] = data.page + 1; fetchTable(view, cfg); };
    } catch (e) {
      wrap.innerHTML = '<div class="empty">Failed to load: ' + esc(e.message) + "</div>";
    }
  }

  function rowFor(view, o) {
    var tds = "";
    if (view === "users") {
      tds = "<td><div class='name'>" + esc(o.name || o.sam) + "</div><div class='sub'>" + esc(o.mail || "") + "</div></td>" +
        "<td class='mono'>" + esc(o.sam) + "</td>" +
        "<td>" + esc(o.title || "—") + "</td>" +
        "<td>" + esc(o.department || "—") + "</td>" +
        "<td>" + statusBadge(o) + "</td>" +
        "<td class='mono'>" + logonText(o.lastLogonDays) + "</td>";
    } else if (view === "groups") {
      tds = "<td><div class='name'>" + esc(o.name) + "</div><div class='sub mono'>" + esc(o.sam) + "</div></td>" +
        "<td>" + esc(o.description || "—") + "</td>" +
        "<td class='mono'>" + (o.memberCount || 0) + "</td>" +
        "<td>" + (o.privileged ? "<span class='badge priv'>privileged</span>" : "<span class='badge off'>standard</span>") + "</td>";
    } else if (view === "ous") {
      tds = "<td><div class='name'>" + esc(o.name) + "</div><div class='sub mono'>" + esc(o.dn) + "</div></td>" +
        "<td>" + esc(o.description || "—") + "</td>";
    } else if (view === "computers") {
      tds = "<td><div class='name'>" + esc(o.name) + "</div><div class='sub'>" + esc(o.dns || "") + "</div></td>" +
        "<td>" + esc(o.os || "—") + "</td>" +
        "<td class='mono'>" + esc(o.dns || "—") + "</td>" +
        "<td>" + (o.enabled ? "<span class='badge on'>enabled</span>" : "<span class='badge off'>disabled</span>") + "</td>" +
        "<td class='mono'>" + logonText(o.lastLogonDays) + "</td>";
    }
    return "<tr data-dn='" + esc(o.dn) + "'>" + tds + "</tr>";
  }

  function statusBadge(o) {
    if (!o.enabled) return "<span class='badge off'>disabled</span>";
    if (o.locked) return "<span class='badge locked'>locked</span>";
    return "<span class='badge on'>enabled</span>";
  }
  function logonText(d) {
    if (d == null) return "<span class='dim'>never</span>";
    if (d === 0) return "today";
    return d + "d ago";
  }

  /* ------------------------------------------------------------ governance */
  async function renderGovernance(root) {
    root.innerHTML = '<div class="spinner">Evaluating identity posture…</div>';
    try {
      var gov = await api("/governance");
      var s = gov.summary;
      root.innerHTML = '<div class="grid">' +
        stat(s.critical, "Critical", "alert") + stat(s.high, "High", "warn") +
        stat(s.privileged, "Privileged", "alert") + stat(s.disabled, "Disabled", "warn") +
        stat(s.findings, "Total findings", "") + "</div>" +
        '<div id="govList"></div>';
      var list = $("govList");
      if (!gov.findings.length) list.innerHTML = '<div class="empty">No findings.</div>';
      gov.findings.forEach(function (f) { list.appendChild(findingRow(f)); });
    } catch (e) {
      root.innerHTML = '<div class="empty">Failed to load: ' + esc(e.message) + "</div>";
    }
  }

  function findingRow(f) {
    var r = el('<div class="finding ' + f.severity + '">' +
      '<span class="badge ' + f.severity + '">' + esc(f.severity) + "</span>" +
      "<div><div class='t'>" + esc(f.name) + "</div><div class='d'>" + esc(f.detail) + "</div></div>" +
      '<span class="cat">' + esc(f.category) + "</span></div>");
    r.onclick = function () { openObject(f.dn); };
    return r;
  }

  /* ---------------------------------------------------------------- drawer */
  function closeDrawer() { $("drawerWrap").hidden = true; }

  async function openObject(dn) {
    if (!dn) return;
    $("drawerWrap").hidden = false;
    $("drawer").innerHTML = '<div class="spinner">Loading object…</div>';
    try {
      var o = await api("/object?dn=" + encodeURIComponent(dn));
      renderDrawer(o);
    } catch (e) {
      $("drawer").innerHTML = '<button class="close-x" onclick="void 0">×</button><div class="empty">' + esc(e.message) + "</div>";
      bindClose();
    }
  }

  function renderDrawer(o) {
    var d = $("drawer");
    var typeLabel = { user: "User", group: "Group", ou: "Organizational Unit", computer: "Computer", object: "Object" }[o.type] || "Object";
    var html = '<button class="close-x" id="drawerClose">×</button>';
    html += "<h2>" + esc(o.name) + "</h2><div class='dsub'>" + typeLabel + " · " + esc(o.dn) + "</div>";

    var rows = [];
    if (o.type === "user") {
      rows = [
        ["Account", o.sam], ["UPN", o.upn], ["Email", o.mail], ["Title", o.title],
        ["Department", o.department], ["Status", o.enabled ? "Enabled" : "Disabled"],
        ["Locked", o.locked ? "Yes" : "No"], ["Last logon", o.lastLogonDays == null ? "Never" : o.lastLogonDays + " days ago"],
        ["Pwd last set", o.pwdLastSetDays == null ? "—" : o.pwdLastSetDays + " days ago"],
        ["Never expires", o.passwordNeverExpires ? "Yes" : "No"],
        ["Created", (o.whenCreated || "").slice(0, 10)]
      ];
    } else if (o.type === "group") {
      rows = [["Group", o.sam], ["Description", o.description], ["Members", o.memberCount], ["Security", o.security ? "Yes" : "No"], ["Privileged", o.privileged ? "Yes" : "No"]];
    } else if (o.type === "ou") {
      rows = [["Name", o.name], ["Description", o.description]];
    } else if (o.type === "computer") {
      rows = [["DNS", o.dns], ["OS", o.os], ["Version", o.osVersion], ["Status", o.enabled ? "Enabled" : "Disabled"], ["Last logon", o.lastLogonDays == null ? "Never" : o.lastLogonDays + " days ago"]];
    } else {
      rows = [["DN", o.dn]];
    }
    html += "<dl class='kv'>" + rows.filter(function (r) { return r[1] != null && r[1] !== ""; })
      .map(function (r) { return "<dt>" + esc(r[0]) + "</dt><dd>" + esc(r[1]) + "</dd>"; }).join("") + "</dl>";

    // actions
    html += "<div class='section-label'>Actions</div><div class='actions'>";
    if (o.type === "user") {
      html += '<button class="btn btn-sm" data-act="password">Reset password</button>';
      html += '<button class="btn btn-sm" data-act="' + (o.enabled ? "disable" : "enable") + '">' + (o.enabled ? "Disable" : "Enable") + "</button>";
      html += '<button class="btn btn-sm" data-act="addgroup">Add to group</button>';
      html += '<button class="btn btn-sm" data-act="move">Move OU</button>';
      html += '<button class="btn btn-sm btn-danger" data-act="delete">Delete</button>';
    } else if (o.type === "group") {
      html += '<button class="btn btn-sm" data-act="addmember">Add member</button>';
      html += '<button class="btn btn-sm" data-act="editdesc">Edit description</button>';
      html += '<button class="btn btn-sm btn-danger" data-act="delete">Delete</button>';
    } else if (o.type === "ou") {
      html += '<button class="btn btn-sm btn-danger" data-act="delete">Delete</button>';
    }
    html += "</div>";

    // membership list
    if (o.type === "user" && Array.isArray(o.memberOf) && o.memberOf.length) {
      html += "<div class='section-label'>Member of</div>";
      html += o.memberOf.map(function (g) { return "<span class='chip'>" + esc(g.split(",")[0].replace(/^CN=/, "")) + "</span>"; }).join("");
    }
    if (o.type === "group" && Array.isArray(o.raw && o.raw.member) && o.raw.member.length) {
      html += "<div class='section-label'>Members (" + o.raw.member.length + ")</div>";
      o.raw.member.slice(0, 40).forEach(function (m) {
        html += "<div class='chip' data-member='" + esc(m) + "' style='cursor:pointer'>" + esc(m.split(",")[0].replace(/^CN=/, "")) + "</div>";
      });
    }

    d.innerHTML = html;
    bindClose();
    d.querySelectorAll("[data-member]").forEach(function (c) { c.onclick = function () { openObject(this.dataset.member); }; });
    d.querySelectorAll("[data-act]").forEach(function (b) { b.onclick = function () { doAction(this.dataset.act, o); }; });
  }

  function bindClose() {
    var c = document.getElementById("drawerClose");
    if (c) c.onclick = closeDrawer;
  }

  /* --------------------------------------------------------------- actions */
  function doAction(act, o) {
    if (act === "password") return modalPassword(o);
    if (act === "enable" || act === "disable") return quickAction("/actions/enable", { dn: o.dn, enabled: act === "enable" }, "Account " + (act === "enable" ? "enabled" : "disabled"));
    if (act === "addgroup") return modalAddGroup(o);
    if (act === "addmember") return modalAddMember(o);
    if (act === "move") return modalMove(o);
    if (act === "delete") return confirmDelete(o);
    if (act === "editdesc") return modalEditDesc(o);
  }

  async function quickAction(path, body, okMsg) {
    try {
      await api(path, { method: "POST", body: JSON.stringify(body) });
      toast(okMsg, "ok");
      closeDrawer();
      render();
    } catch (e) { toast(e.message, "err"); }
  }

  function confirmDelete(o) {
    openModal("Delete " + esc(o.name) + " — " + esc(o.type) + "?", "<p class='muted'>This permanently removes <span class='mono'>" + esc(o.dn) + "</span>. This cannot be undone.</p>",
      [{ label: "Cancel", cls: "" }, {
        label: "Delete", cls: "btn-danger", onClick: async function () {
          try { await api("/actions/delete", { method: "POST", body: JSON.stringify({ dn: o.dn }) }); toast("Deleted " + o.name, "ok"); closeModal(); closeDrawer(); render(); }
          catch (e) { toast(e.message, "err"); }
        }
      }]);
  }

  function modalPassword(o) {
    openModal("Reset password", "<p class='muted'>Set a new password for <b>" + esc(o.name) + "</b>.</p>" +
      "<div class='form'><div class='full'><label>New password</label><input id='newpw' type='text' value='ChangeMe!2026' /></div></div>",
      [{ label: "Cancel", cls: "" }, {
        label: "Reset", cls: "btn-primary", onClick: async function () {
          var pw = $("newpw").value;
          try { await api("/actions/password", { method: "POST", body: JSON.stringify({ dn: o.dn, password: pw }) }); toast("Password reset for " + o.name, "ok"); closeModal(); }
          catch (e) { toast(e.message, "err"); }
        }
      }]);
  }

  async function modalAddGroup(o) {
    var groups = await getGroups();
    var opts = groups.map(function (g) { return "<option value='" + esc(g.dn) + "'>" + esc(g.name) + "</option>"; }).join("");
    openModal("Add to group", "<p class='muted'>Add <b>" + esc(o.name) + "</b> to a security group.</p><div class='form'><div class='full'><label>Group</label><select id='grpSel'>" + opts + "</select></div></div>",
      [{ label: "Cancel", cls: "" }, {
        label: "Add", cls: "btn-primary", onClick: async function () {
          try { await api("/actions/member", { method: "POST", body: JSON.stringify({ group_dn: $("grpSel").value, member_dn: o.dn, add: true }) }); toast("Added to group", "ok"); closeModal(); openObject(o.dn); }
          catch (e) { toast(e.message, "err"); }
        }
      }]);
  }

  async function modalAddMember(o) {
    var users = await getUsers();
    var opts = users.map(function (u) { return "<option value='" + esc(u.dn) + "'>" + esc(u.name + " (" + u.sam + ")") + "</option>"; }).join("");
    openModal("Add member to " + esc(o.name), "<div class='form'><div class='full'><label>User</label><select id='usrSel'>" + opts + "</select></div></div>",
      [{ label: "Cancel", cls: "" }, {
        label: "Add", cls: "btn-primary", onClick: async function () {
          try { await api("/actions/member", { method: "POST", body: JSON.stringify({ group_dn: o.dn, member_dn: $("usrSel").value, add: true }) }); toast("Member added", "ok"); closeModal(); openObject(o.dn); }
          catch (e) { toast(e.message, "err"); }
        }
      }]);
  }

  async function modalMove(o) {
    var ous = await getOUs();
    var opts = ous.map(function (u) { return "<option value='" + esc(u.dn) + "'>" + esc(u.name) + "</option>"; }).join("");
    openModal("Move " + esc(o.name), "<p class='muted'>Select the target organizational unit.</p><div class='form'><div class='full'><label>Target OU</label><select id='ouSel'>" + opts + "</select></div></div>",
      [{ label: "Cancel", cls: "" }, {
        label: "Move", cls: "btn-primary", onClick: async function () {
          try { await api("/actions/move", { method: "POST", body: JSON.stringify({ dn: o.dn, target_dn: $("ouSel").value }) }); toast("Object moved", "ok"); closeModal(); closeDrawer(); render(); }
          catch (e) { toast(e.message, "err"); }
        }
      }]);
  }

  function modalEditDesc(o) {
    openModal("Edit description", "<div class='form'><div class='full'><label>Description</label><input id='desc' value='" + esc(o.description || "") + "' /></div></div>",
      [{ label: "Cancel", cls: "" }, { label: "Save", cls: "btn-primary", onClick: function () { toast("Description edit is not wired to LDAP yet", "err"); closeModal(); } }]);
  }

  /* ------------------------------------------------------------ create modals */
  async function openCreate(view) {
    if (view === "users") return createUserModal();
    if (view === "groups") return createGroupModal();
    if (view === "ous") return createOUModal();
  }

  async function createUserModal() {
    var ous = await getOUs();
    var opts = ous.filter(function (u) { return /People|Contractors|ServiceAccounts/i.test(u.name); }).map(function (u) { return "<option value='" + esc(u.dn) + "'>" + esc(u.name) + "</option>"; }).join("");
    openModal("New user",
      "<div class='form'>" +
      fld("givenName", "First name", "") + fld("surname", "Last name", "") +
      fld("sam", "Account name (sAMAccountName)", "") +
      fld("title", "Job title", "") +
      fld("department", "Department", "") + fld("mail", "Email", "") +
      fld("password", "Initial password", "ChangeMe!2026") +
      "<div class='full'><label>Organizational Unit</label><select id='f_ou'>" + opts + "</select></div>" +
      "</div>",
      [{ label: "Cancel", cls: "" }, {
        label: "Create user", cls: "btn-primary", onClick: async function () {
          var payload = collect(["givenName", "surname", "sam", "title", "department", "mail", "password"]);
          payload.ou = $("f_ou").value;
          if (!payload.sam) return toast("Account name is required", "err");
          try { await api("/users", { method: "POST", body: JSON.stringify(payload) }); toast("User " + payload.sam + " created", "ok"); closeModal(); state.caches.users = null; render(); }
          catch (e) { toast(e.message, "err"); }
        }
      }]);
  }

  async function createGroupModal() {
    var ous = await getOUs();
    var grpOU = ous.filter(function (u) { return /Groups/i.test(u.name); })[0];
    openModal("New group",
      "<div class='form'>" + fld("name", "Group name", "") + fld("description", "Description", "") + "</div>",
      [{ label: "Cancel", cls: "" }, {
        label: "Create group", cls: "btn-primary", onClick: async function () {
          var payload = collect(["name", "description"]);
          if (grpOU) payload.ou = grpOU.dn;
          if (!payload.name) return toast("Group name is required", "err");
          try { await api("/groups", { method: "POST", body: JSON.stringify(payload) }); toast("Group created", "ok"); closeModal(); state.caches.groups = null; render(); }
          catch (e) { toast(e.message, "err"); }
        }
      }]);
  }

  async function createOUModal() {
    var ous = await getOUs();
    var opts = [{ dn: state.meta.baseDn || "", name: "(domain root)" }].concat(ous).map(function (u) { return "<option value='" + esc(u.dn) + "'>" + esc(u.name) + "</option>"; }).join("");
    openModal("New organizational unit",
      "<div class='form'>" + fld("name", "OU name", "") + fld("description", "Description", "") +
      "<div class='full'><label>Parent</label><select id='f_parent'>" + opts + "</select></div></div>",
      [{ label: "Cancel", cls: "" }, {
        label: "Create OU", cls: "btn-primary", onClick: async function () {
          var payload = collect(["name", "description"]); payload.parent = $("f_parent").value;
          if (!payload.name) return toast("OU name is required", "err");
          try { await api("/ous", { method: "POST", body: JSON.stringify(payload) }); toast("OU created", "ok"); closeModal(); state.caches.ous = null; render(); }
          catch (e) { toast(e.message, "err"); }
        }
      }]);
  }

  function fld(id, label, value) {
    return "<div><label>" + esc(label) + "</label><input id='f_" + id + "' value='" + esc(value) + "' /></div>";
  }
  function collect(ids) {
    var out = {};
    ids.forEach(function (id) { var e = $("f_" + id); if (e) out[id] = e.value; });
    return out;
  }

  /* ----------------------------------------------------------------- caches */
  async function getOUs() {
    if (!state.caches.ous) state.caches.ous = (await api("/ous?size=1000")).items;
    return state.caches.ous;
  }
  async function getGroups() {
    if (!state.caches.groups) state.caches.groups = (await api("/groups?size=1000")).items;
    return state.caches.groups;
  }
  async function getUsers() {
    if (!state.caches.users) state.caches.users = (await api("/users?size=1000")).items;
    return state.caches.users;
  }

  /* ----------------------------------------------------------------- modal */
  function openModal(title, bodyHtml, buttons) {
    $("modalWrap").hidden = false;
    var m = $("modal");
    m.innerHTML = "<h2>" + title + "</h2>" + bodyHtml + "<div class='foot' id='modalFoot'></div>";
    var foot = $("modalFoot");
    (buttons || []).forEach(function (b) {
      var btn = el("<button class='btn " + (b.cls || "") + "'>" + esc(b.label) + "</button>");
      btn.onclick = b.onClick;
      foot.appendChild(btn);
    });
  }
  function closeModal() { $("modalWrap").hidden = true; }

  /* ------------------------------------------------------------------- init */
  function init() {
    $("nav").addEventListener("click", function (e) {
      var b = e.target.closest("button[data-view]");
      if (b) setView(b.dataset.view);
    });
    $("refreshBtn").onclick = function () {
      state.caches = { ous: null, groups: null, users: null };
      loadMeta();
      render();
    };
    $("drawerBg").onclick = closeDrawer;
    $("modalBg").onclick = closeModal;
    document.addEventListener("keydown", function (e) { if (e.key === "Escape") { closeDrawer(); closeModal(); } });
    loadMeta();
    setView("dashboard");
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
