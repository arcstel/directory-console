(function () {
  "use strict";

  function $(id) { return document.getElementById(id); }

  function show(text, kind) {
    var r = $("result");
    r.style.display = "block";
    r.className = "result " + kind;
    r.textContent = text;
  }

  // If the appliance is already provisioned, go straight to the console.
  fetch("/api/setup/status")
    .then(function (r) { return r.json(); })
    .then(function (s) {
      if (s.provisioned) window.location.replace("/");
    })
    .catch(function () {});

  var progress = null;
  function startChecks() {
    var ids = ["c1", "c2", "c3", "c4"];
    var i = 0;
    $("checks").style.display = "block";
    progress = setInterval(function () {
      if (i > 0) { $(ids[i - 1]).className = "done"; $(ids[i - 1]).textContent = "✓ " + $(ids[i - 1]).textContent.replace(/^[◌✓] /, ""); }
      if (i < ids.length) { $(ids[i]).className = ""; i++; }
    }, 900);
  }
  function finishChecks() {
    clearInterval(progress);
    ["c1", "c2", "c3", "c4"].forEach(function (id) {
      var e = $(id);
      e.className = "done";
      e.textContent = "✓ " + e.textContent.replace(/^[◌✓] /, "");
    });
  }

  $("setupForm").addEventListener("submit", function (ev) {
    ev.preventDefault();
    var payload = {
      domain: $("domain").value.trim(),
      realm: $("realm").value.trim(),
      admin_pass: $("pass").value,
      seed: $("seed").checked,
      dns_forwarder: $("forwarder").value.trim() || "1.1.1.1"
    };
    if (!payload.domain) return show("NetBIOS domain is required.", "err");
    if (!/^[A-Za-z0-9]+$/.test(payload.domain)) return show("NetBIOS domain must be alphanumeric (e.g. EXAMPLE).", "err");
    if (!payload.realm || payload.realm.indexOf(".") < 0) return show("DNS realm must contain a dot (e.g. EXAMPLE.LOCAL).", "err");
    if (payload.admin_pass.length < 8) return show("Administrator password must be at least 8 characters.", "err");
    if (payload.admin_pass !== $("pass2").value) return show("Passwords do not match.", "err");

    $("submitBtn").disabled = true;
    $("submitBtn").innerHTML = '<span class="spin"></span> Provisioning…';
    show("Working… this can take up to a minute.", "ok");
    startChecks();

    fetch("/api/setup/provision", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    })
      .then(function (r) { return r.json().then(function (b) { return { ok: r.ok, body: b }; }); })
      .then(function (res) {
        if (!res.ok) throw new Error(res.body.detail || "Provisioning failed");
        finishChecks();
        var b = res.body;
        show("Domain " + b.domain + " (" + b.realm + ") provisioned\nBase DN: " + b.base_dn +
          "\nSeeded: " + (b.seeded ? "yes" : "no") + "\nRedirecting to the console…", "ok");
        setTimeout(function () { window.location.replace("/"); }, 2200);
      })
      .catch(function (e) {
        clearInterval(progress);
        $("submitBtn").disabled = false;
        $("submitBtn").textContent = "Provision domain";
        show("Error: " + e.message, "err");
      });
  });
})();
