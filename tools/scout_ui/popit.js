/*
 * Scout port Popit surface.
 *
 * The page is a reading of one report file. It never invents a value: a field
 * the tool could not read stays em-dashed and the refusal beside it names the
 * path that was searched.
 */
(function () {
  "use strict";

  var byId = function (id) { return document.getElementById(id); };
  var setText = function (id, value) {
    var node = byId(id);
    if (node) { node.textContent = value === undefined || value === null || value === "" ? "\u2014" : String(value); }
  };
  var setState = function (id, word, kind) {
    var node = byId(id);
    if (!node) { return; }
    node.textContent = word;
    node.classList.remove("pass", "fail", "skip");
    if (kind) { node.classList.add(kind); }
  };
  var kindOf = function (state) {
    return state === "pass" ? "pass" : state === "fail" ? "fail" : state === "skip" ? "skip" : "";
  };

  function renderGame(report) {
    var game = report.game || {};
    var build = game.build ? "build " + game.build : game.state || "unread";
    setText("marker-game", game.version_date ? build + " · " + game.version_date : build);
  }

  function renderMod(report) {
    var mod = report.mod || {};
    var sources = mod.sources || {};
    var table = mod.hero_table || {};
    setText("workspace", report.workspace);
    setText("sources-mesh", sources.smd === undefined ? "" : sources.smd + " SMD" + (sources.qc ? " · " + sources.qc : ""));
    setText("sources-anim", sources.anim_smd === undefined ? "" : sources.anim_smd + " SMD in " + (sources.anim_dirs || []).length + " anim folder(s)");
    setText("hero-count", table.heroes);
    setText("hero-bytes", table.bytes === undefined ? "" : Number(table.bytes).toLocaleString() + " bytes");
    setText("hero-digest", table.blake3 ? String(table.blake3).slice(0, 24) + "\u2026" : "");
    setText("marker-mod", table.heroes ? table.heroes + " hero entries" : (mod.hero_table === undefined ? "unread" : "absent"));
  }

  function renderDrift(report) {
    var drift = report.drift || {};
    var body = byId("drift-table");
    var rows = [];
    (drift.added || []).forEach(function (slug) { rows.push([slug, "\u2014", "in the live build", "added"]); });
    (drift.removed || []).forEach(function (slug) { rows.push([slug, "present in the port", "\u2014", "removed"]); });
    (drift.moved || []).forEach(function (row) { rows.push([row.slug, row.mod, row.live, "moved"]); });
    if (!body) { return; }
    var tbody = body.querySelector("tbody");
    tbody.textContent = "";
    if (!rows.length) {
      var empty = document.createElement("tr");
      var cell = document.createElement("td");
      cell.colSpan = 3;
      cell.textContent = drift.state === "measured"
        ? drift.same + " hero entries match the live roster"
        : "not measured";
      empty.appendChild(cell);
      tbody.appendChild(empty);
    }
    rows.forEach(function (row) {
      var tr = document.createElement("tr");
      tr.className = row[3];
      [row[0], row[1], row[2]].forEach(function (value) {
        var td = document.createElement("td");
        td.textContent = value;
        tr.appendChild(td);
      });
      tbody.appendChild(tr);
    });
    var changed = rows.length;
    setState("drift-state", drift.state === "measured" ? (changed ? changed + " differences" : "in step") : "unmeasured",
      drift.state === "measured" ? (changed ? "fail" : "pass") : "skip");
  }

  function renderGraph(report) {
    // The variation is the bake target: it names one hero, one skeleton and its
    // clips. Fall back to the graph document when no variation was read.
    var variation = report.variation || {};
    if (variation.state === "read") {
      setText("graph-variation", variation.variation);
      setText("graph-skeleton", variation.skeleton);
      setText("graph-nodes", variation.nodes);
      setText("graph-clips", variation.clips === undefined ? "" : (variation.clips || []).length + " references");
      setText("marker-graph", variation.nodes ? variation.nodes + " nodes \u00b7 " + variation.variation : "unread");
      setState("graph-state", "read", "pass");
      return;
    }
    var graph = report.animgraph || {};
    setText("graph-variation", graph.variation);
    setText("graph-skeleton", graph.skeleton);
    setText("graph-nodes", graph.nodes);
    setText("graph-clips", graph.clips === undefined ? "" : (graph.clips || []).length + " references");
    setText("marker-graph", graph.nodes ? graph.nodes + " nodes" : "unread");
    setState("graph-state", graph.state || "unread", graph.state === "read" ? "pass" : "skip");
  }

  function renderSequences(report) {
    var rows = report.sequences || {};
    if (rows.state !== "measured") {
      setText("sequence-coverage", "not measured");
      setText("sequence-unbound", "");
      return;
    }
    setText("sequence-coverage", rows.bound + " of " + rows.graph_sequences + " (" + rows.source_sequences + " source animations)");
    var unbound = rows.unbound || [];
    setText("sequence-unbound", unbound.length ? unbound.slice(0, 6).join(", ") + (unbound.length > 6 ? "\u2026" : "") : "none");
  }

  function renderTools(report) {
    var tools = report.dota_tools || {};
    var state = tools.state || "unavailable";
    var graphs = (tools.graphs || []).length;
    setText("marker-dota", state === "ready" ? graphs + " graphs · compiler" : state);
  }

  function renderRefusals(report) {
    var list = byId("refusals");
    if (!list) { return; }
    list.textContent = "";
    var rows = report.refusals || [];
    setText("refusal-count", rows.length + (rows.length === 1 ? " refusal" : " refusals"));
    if (!rows.length) {
      var empty = document.createElement("li");
      empty.className = "empty";
      empty.textContent = "nothing refused in this reading";
      list.appendChild(empty);
      return;
    }
    rows.forEach(function (row) {
      var li = document.createElement("li");
      var code = document.createElement("code");
      code.textContent = row.code;
      li.appendChild(code);
      if (row.detail) { li.appendChild(document.createTextNode(" \u00b7 " + row.detail)); }
      list.appendChild(li);
    });
  }

  function renderState(report) {
    var checks = report.checks || [];
    var failed = checks.filter(function (row) { return row.state === "fail"; }).length;
    var skipped = checks.filter(function (row) { return row.state === "skip"; }).length;
    var kind = report.result === "pass" ? "pass" : "fail";
    var word = report.result === "pass" ? "in step" : failed + " failed";
    if (skipped && report.result === "pass") { word += " \u00b7 " + skipped + " skipped"; }
    setState("port-state", word, kind);
    setText("bar-meta", "deadlock model forge \u00b7 " + (report.generated || ""));
    setText("generated", report.generated);
  }

  function fail(message) {
    setState("port-state", "report unreadable", "fail");
    var list = byId("refusals");
    if (list) {
      list.textContent = "";
      var li = document.createElement("li");
      li.textContent = message;
      list.appendChild(li);
    }
  }

  fetch("/report.json", { cache: "no-store" })
    .then(function (response) {
      if (!response.ok) { throw new Error("report.json answered " + response.status); }
      return response.json();
    })
    .then(function (report) {
      renderGame(report);
      renderMod(report);
      renderDrift(report);
      renderGraph(report);
      renderSequences(report);
      renderTools(report);
      renderRefusals(report);
      renderState(report);
    })
    .catch(function (error) { fail(String(error && error.message ? error.message : error)); });
}());
