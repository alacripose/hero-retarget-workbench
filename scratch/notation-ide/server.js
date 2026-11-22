#!/usr/bin/env node
// Scratch server for the notation IDE: static files, the live notes channel, and the
// repair pairs the UI records for the Debian judge.
//
//   node server.js            # http://127.0.0.1:5177
//
// Notes are what the agent posts while the owner pastes prose; the page polls them and
// draws them on the selected node. Pairs are the training rows: shorthand in, repair out.

const http = require("http");
const fs = require("fs");
const path = require("path");

// A stray PORT=0 in the environment binds an ephemeral port and the demo cannot be found.
// The IDE owns its own variable, and any value that is not a real port is refused.
const asked = Number(process.env.NOTATION_PORT);
const PORT = Number.isInteger(asked) && asked > 1024 && asked < 65536 ? asked : 5177;
const ROOT = path.join(__dirname, "public");
const DATA = path.join(__dirname, "data");
const NOTES = path.join(DATA, "notes.json");
const PAIRS = path.join(DATA, "pairs.jsonl");

const MIME = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".svg": "image/svg+xml",
  ".png": "image/png",
};

fs.mkdirSync(DATA, { recursive: true });
if (!fs.existsSync(NOTES)) fs.writeFileSync(NOTES, "[]");
if (!fs.existsSync(PAIRS)) fs.writeFileSync(PAIRS, "");

function readNotes() {
  try {
    return JSON.parse(fs.readFileSync(NOTES, "utf8"));
  } catch {
    return [];
  }
}

function send(res, status, body, type = "application/json; charset=utf-8") {
  res.writeHead(status, { "content-type": type, "cache-control": "no-store" });
  res.end(body);
}

function json(res, status, value) {
  send(res, status, JSON.stringify(value));
}

function body(req) {
  return new Promise((resolve, reject) => {
    let raw = "";
    req.on("data", (chunk) => {
      raw += chunk;
      if (raw.length > 2_000_000) reject(new Error("body too large"));
    });
    req.on("end", () => {
      try {
        resolve(raw ? JSON.parse(raw) : {});
      } catch (error) {
        reject(error);
      }
    });
    req.on("error", reject);
  });
}

const server = http.createServer(async (req, res) => {
  const url = new URL(req.url, `http://127.0.0.1:${PORT}`);

  if (url.pathname === "/api/notes" && req.method === "GET") {
    return json(res, 200, { notes: readNotes() });
  }

  if (url.pathname === "/api/notes" && req.method === "POST") {
    try {
      const input = await body(req);
      const notes = readNotes();
      const note = {
        id: `n${Date.now().toString(36)}`,
        at: new Date().toISOString(),
        text: String(input.text || "").slice(0, 2000),
        target: Number.isInteger(input.target) ? input.target : null,
        // note: the agent speaking. comment: the owner speaking from under the prose.
        kind: input.kind === "question" ? "question" : input.kind === "comment" ? "comment" : "note",
      };
      notes.push(note);
      fs.writeFileSync(NOTES, JSON.stringify(notes, null, 2));
      return json(res, 201, note);
    } catch (error) {
      return json(res, 400, { error: String(error.message || error) });
    }
  }

  if (url.pathname === "/api/notes" && req.method === "DELETE") {
    fs.writeFileSync(NOTES, "[]");
    return json(res, 200, { notes: [] });
  }

  if (url.pathname === "/api/pairs" && req.method === "GET") {
    const rows = fs.readFileSync(PAIRS, "utf8").split("\n").filter(Boolean).map((line) => JSON.parse(line));
    return json(res, 200, { count: rows.length, pairs: rows.slice(-50) });
  }

  if (url.pathname === "/api/pairs" && req.method === "POST") {
    try {
      const input = await body(req);
      const row = {
        at: new Date().toISOString(),
        before: String(input.before || "").slice(0, 4000),
        after: String(input.after || "").slice(0, 4000),
        grade: String(input.grade || ""),
        gaps: Array.isArray(input.gaps) ? input.gaps.slice(0, 20) : [],
        source: "notation-ide",
      };
      if (!row.before || !row.after) return json(res, 400, { error: "both before and after are required" });
      fs.appendFileSync(PAIRS, JSON.stringify(row) + "\n");
      return json(res, 201, row);
    } catch (error) {
      return json(res, 400, { error: String(error.message || error) });
    }
  }

  if (url.pathname === "/api/state") {
    return json(res, 200, {
      notes: readNotes().length,
      pairs: fs.readFileSync(PAIRS, "utf8").split("\n").filter(Boolean).length,
      root: ROOT,
    });
  }

  const relative = url.pathname === "/" ? "index.html" : decodeURIComponent(url.pathname.slice(1));
  const file = path.join(ROOT, relative);
  if (!file.startsWith(ROOT)) return send(res, 403, "forbidden", "text/plain");
  fs.readFile(file, (error, bytes) => {
    if (error) return send(res, 404, "not found", "text/plain");
    send(res, 200, bytes, MIME[path.extname(file)] || "application/octet-stream");
  });
});

server.listen(PORT, "127.0.0.1", () => {
  console.log(`notation-ide http://127.0.0.1:${PORT}`);
});
