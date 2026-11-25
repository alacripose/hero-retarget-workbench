const facts = document.getElementById("counts");
const table = document.querySelector("#step-table tbody");
const superseded = document.getElementById("superseded");
const portState = document.getElementById("port-state");

function fact(value, label) {
  const cell = document.createElement("div");
  const strong = document.createElement("b");
  strong.textContent = value;
  const span = document.createElement("span");
  span.textContent = label;
  cell.append(strong, span);
  return cell;
}

function draw(body) {
  const port = body.port || {};
  portState.textContent = `${port.workspace || "no workspace"} · ${port.qc || "no qc"} · ${body.at}`;

  facts.replaceChildren(
    fact(port.anim_smd ?? 0, "animation SMD"),
    fact(port.smd ?? 0, "model SMD"),
    fact(port.sequences ?? 0, "$sequence names"),
    fact(body.counts?.steps_pass ?? 0, "steps passing"),
    fact(body.counts?.steps_blocked ?? 0, "steps blocked")
  );

  table.replaceChildren();
  for (const step of body.steps || []) {
    const row = document.createElement("tr");
    const label = document.createElement("td");
    label.textContent = step.label;
    const state = document.createElement("td");
    state.className = `state ${step.state}`;
    state.textContent = step.state;
    const detail = document.createElement("td");
    detail.append(document.createTextNode(step.detail));
    if (step.refusal) {
      const small = document.createElement("small");
      small.textContent = ` — ${step.refusal}`;
      detail.append(small);
    }
    row.append(label, state, detail);
    table.append(row);
  }

  superseded.replaceChildren();
  const rows = body.superseded || [];
  if (!rows.length) {
    const item = document.createElement("li");
    item.textContent = "nothing set aside";
    superseded.append(item);
  }
  for (const row of rows) {
    const item = document.createElement("li");
    item.textContent = `${row.path} — ${row.why}`;
    superseded.append(item);
  }
}

async function read() {
  portState.textContent = "reading the port…";
  try {
    const response = await fetch("/api/state", { cache: "no-store" });
    draw(await response.json());
  } catch (error) {
    portState.textContent = `could not read the state: ${error}`;
  }
}

document.getElementById("refresh").addEventListener("click", read);
read();
