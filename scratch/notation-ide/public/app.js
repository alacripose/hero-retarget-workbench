import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { Core } from "/core.js";

const COLORS = { whole: 0x7ee0a3, annotated: 0xe6c86e, lossy: 0xe08a5a, shorthand: 0xe0533f };

const host = document.getElementById("scene");
const statusEl = document.getElementById("status");
const detailEl = document.getElementById("detail");
const repairEl = document.getElementById("repair");
const fixedEl = document.getElementById("fixed");
const notesEl = document.getElementById("notes");
const pairsEl = document.getElementById("pairs");
const proseEl = document.getElementById("prose");

const SAMPLE = `- **A live compile can actually be stopped.**
- **The Release Compile button asks first.** \`DMF_OT_compile.invoke\` calls \`invoke_confirm\`.
- **Not checked.** The actual GUI click through the confirmation dialog.
Not checked: the owner's .blend was not reopened here.
- **Relevant.** See above; 4 counters; 2 flags
0.22.4 accuracy continuous halo
- see docs/history for the rest.
The dock reserves its strip before it paints, so no frame is drawn over a work area it does not own.`;

const scene = new THREE.Scene();
scene.background = new THREE.Color(0x101216);
scene.fog = new THREE.Fog(0x101216, 26, 90);

const camera = new THREE.PerspectiveCamera(46, 1, 0.1, 400);
const renderer = new THREE.WebGLRenderer({ antialias: true });
renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
host.appendChild(renderer.domElement);

const controls = new OrbitControls(camera, renderer.domElement);
controls.enableDamping = true;
controls.dampingFactor = 0.08;
controls.maxPolarAngle = Math.PI * 0.5;

scene.add(new THREE.AmbientLight(0xffffff, 0.9));
const key = new THREE.DirectionalLight(0xffffff, 1.7);
key.position.set(5, 11, 9);
scene.add(key);
const rim = new THREE.DirectionalLight(0x6f8cff, 0.6);
rim.position.set(-7, -4, -8);
scene.add(rim);

const grid = new THREE.GridHelper(120, 60, 0x232833, 0x1a1e25);
grid.position.y = -2.6;
scene.add(grid);

const world = new THREE.Group();
scene.add(world);

let core = null;
let rows = [];
let nodes = [];
let selected = -1;
let noteTargets = new Set();
let pairsCount = 0;
let layout = { cols: 1, lines: 1, stepX: 3.6, stepZ: 3.1 };
const raycaster = new THREE.Raycaster();
const pointer = new THREE.Vector2();

function labelSprite(text, color) {
  const canvas = document.createElement("canvas");
  canvas.width = 1024;
  canvas.height = 128;
  const ctx = canvas.getContext("2d");
  ctx.fillStyle = "rgba(16,18,22,0.85)";
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  ctx.font = "42px 'Cascadia Mono', monospace";
  ctx.fillStyle = color;
  ctx.textBaseline = "middle";
  ctx.fillText(text.length > 34 ? text.slice(0, 33) + "…" : text, 16, canvas.height / 2);
  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  const sprite = new THREE.Sprite(new THREE.SpriteMaterial({ map: texture, transparent: true, depthTest: false }));
  sprite.scale.set(3.9, 0.49, 1);
  sprite.center.set(0.5, 0);
  return sprite;
}

function dispose(group) {
  group.traverse((object) => {
    if (object.geometry) object.geometry.dispose();
    if (object.material) {
      if (object.material.map) object.material.map.dispose();
      object.material.dispose();
    }
  });
  group.clear();
}

function build(analysed) {
  rows = analysed;
  nodes = [];
  dispose(world);
  noteTargets = new Set();

  // A bounded grid keeps a long file inside the frame instead of running off the spine.
  const cols = Math.min(Math.max(1, rows.length), 5);
  const lineCount = Math.max(1, Math.ceil(rows.length / cols));
  const stepX = 3.9;
  const stepZ = 3.3;
  layout = { cols, lines: lineCount, stepX, stepZ };
  const offsetX = ((cols - 1) * stepX) / 2;
  const offsetZ = ((lineCount - 1) * stepZ) / 2;

  rows.forEach((row, index) => {
    const x = (index % cols) * stepX - offsetX;
    const z = Math.floor(index / cols) * stepZ - offsetZ;
    const color = COLORS[row.grade] ?? COLORS.whole;
    const height = Math.max(0.55, Math.min(3.0, row.words * 0.09));

    const group = new THREE.Group();
    group.position.set(x, 0, z);

    const node = new THREE.Mesh(
      new THREE.SphereGeometry(0.3, 24, 18),
      new THREE.MeshStandardMaterial({ color, roughness: 0.35, metalness: 0.1 })
    );
    node.userData.index = index;
    group.add(node);
    nodes.push(node);

    const bar = new THREE.Mesh(
      new THREE.BoxGeometry(0.14, height, 0.14),
      new THREE.MeshStandardMaterial({ color, roughness: 0.5 })
    );
    bar.position.y = height / 2 + 0.4;
    group.add(bar);

    const label = labelSprite(row.text, `#${color.toString(16).padStart(6, "0")}`);
    label.position.set(0, height + 0.85 + (index % 2) * 0.55, 0);
    group.add(label);

    row.gaps.forEach((_, marker) => {
      const shard = new THREE.Mesh(
        new THREE.OctahedronGeometry(0.09),
        new THREE.MeshStandardMaterial({ color: 0xe0533f, emissive: 0x511208, roughness: 0.4 })
      );
      const angle = (marker / Math.max(1, row.gaps.length)) * Math.PI * 2;
      shard.position.set(Math.cos(angle) * 0.56, Math.sin(angle) * 0.56, 0.14);
      group.add(shard);
    });

    const ring = new THREE.Mesh(
      new THREE.TorusGeometry(0.5, 0.022, 8, 48),
      new THREE.MeshBasicMaterial({ color: 0xffffff })
    );
    ring.rotation.x = Math.PI / 2;
    ring.visible = false;
    ring.name = "selection";
    group.add(ring);

    const noteRing = new THREE.Mesh(
      new THREE.TorusGeometry(0.72, 0.018, 8, 48),
      new THREE.MeshBasicMaterial({ color: 0x9a7bff })
    );
    noteRing.rotation.x = Math.PI / 2;
    noteRing.visible = false;
    noteRing.name = "note";
    group.add(noteRing);

    world.add(group);
  });

  if (rows.length > 1) {
    const points = rows.map((_, index) => {
      const x = (index % cols) * stepX - offsetX;
      const z = Math.floor(index / cols) * stepZ - offsetZ;
      return new THREE.Vector3(x, 0, z);
    });
    world.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints(points), new THREE.LineBasicMaterial({ color: 0x2a2f39 })));
  }

  if (selected >= rows.length) selected = -1;
  paint();
  frame();
}

function frame() {
  const halfX = ((layout.cols - 1) * layout.stepX) / 2 + 2.4;
  const halfZ = ((layout.lines - 1) * layout.stepZ) / 2 + 2.4;
  const vertical = THREE.MathUtils.degToRad(camera.fov);
  const horizontal = 2 * Math.atan(Math.tan(vertical / 2) * Math.max(camera.aspect, 0.2));
  const distance = Math.max(12, halfX / Math.tan(horizontal / 2), (halfZ / Math.tan(vertical / 2)) * 1.35);
  camera.position.set(0, distance * 0.66, distance * 0.8);
  controls.target.set(0, 0.4, 0);
  controls.update();
  scene.fog.near = distance * 0.85;
  scene.fog.far = distance * 3.4;
}

function paint() {
  world.children.forEach((group) => {
    const node = group.children[0];
    if (!node || typeof node.userData.index !== "number") return;
    const index = node.userData.index;
    const ring = group.getObjectByName("selection");
    if (ring) ring.visible = index === selected;
    const noteRing = group.getObjectByName("note");
    if (noteRing) noteRing.visible = index === selected || noteTargets.has(index);
  });
}

function showDetail(index) {
  const row = rows[index];
  if (!row) {
    detailEl.innerHTML = '<p class="muted">No line selected.</p>';
    repairEl.hidden = true;
    return;
  }
  const colour = `#${(COLORS[row.grade] ?? COLORS.whole).toString(16).padStart(6, "0")}`;
  const gaps = row.gaps.length
    ? `<ul class="gaps">${row.gaps.map((gap) => `<li><code>${gap.code}</code> — ${gap.detail}</li>`).join("")}</ul>`
    : '<p class="muted">No gap on this line.</p>';
  detailEl.innerHTML = `
    <p class="muted small">line ${index + 1} · ${row.words} words · <span style="color:${colour}">${row.grade}</span></p>
    <div class="line-text">${row.text.replace(/</g, "&lt;")}</div>
    ${gaps}`;
  repairEl.hidden = false;
  fixedEl.value = row.text;
}

function select(index) {
  selected = index;
  paint();
  showDetail(index);
}

function analyseNow() {
  if (!core) {
    statusEl.textContent = "core not loaded";
    return;
  }
  const analysed = core.analyse(proseEl.value);
  build(analysed);
  const shorthand = analysed.filter((row) => row.grade === "shorthand").length;
  const lossy = analysed.filter((row) => row.grade === "lossy").length;
  statusEl.textContent = `${analysed.length} lines · ${shorthand} shorthand · ${lossy} lossy`;
  if (analysed.length) select(0);
}

renderer.domElement.addEventListener("pointerdown", (event) => {
  const rect = renderer.domElement.getBoundingClientRect();
  pointer.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
  pointer.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;
  raycaster.setFromCamera(pointer, camera);
  const hit = raycaster.intersectObjects(nodes, false)[0];
  if (hit) select(hit.object.userData.index);
});

document.getElementById("analyse").addEventListener("click", analyseNow);
document.getElementById("sample").addEventListener("click", () => {
  proseEl.value = SAMPLE;
  analyseNow();
});
document.getElementById("clear").addEventListener("click", () => {
  proseEl.value = "";
  build([]);
  statusEl.textContent = "ready";
});

document.getElementById("save").addEventListener("click", async () => {
  const row = rows[selected];
  if (!row) return;
  const response = await fetch("/api/pairs", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ before: row.text, after: fixedEl.value, grade: row.grade, gaps: row.gaps.map((gap) => gap.code) }),
  });
  if (response.ok) {
    pairsCount += 1;
    pairsEl.textContent = `${pairsCount} pairs`;
    statusEl.textContent = `pair saved · line ${selected + 1} repaired`;
  }
});

// The owner writes here instead of in a chat turn: the comment travels to the same notes channel
// the agent reads, and it names the selected line so the answer can point at it.
document.getElementById("send").addEventListener("click", async () => {
  const box = document.getElementById("comment");
  const text = box.value.trim();
  if (!text) return;
  const response = await fetch("/api/notes", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ text, kind: "comment", target: selected >= 0 ? selected : null }),
  });
  if (response.ok) {
    box.value = "";
    document.getElementById("sent").textContent = selected >= 0 ? `sent, on line ${selected + 1}` : "sent";
    pollNotes();
  }
});

async function pollNotes() {
  try {
    const [notes, pairs] = await Promise.all([
      fetch("/api/notes").then((r) => r.json()),
      fetch("/api/pairs").then((r) => r.json()),
    ]);
    noteTargets = new Set(notes.notes.filter((note) => note.target !== null).map((note) => note.target));
    notesEl.innerHTML = notes.notes
      .slice(-8)
      .reverse()
      .map(
        (note) =>
          `<li class="${note.kind}">${note.text.replace(/</g, "&lt;")}${
            note.target === null ? "" : `<em> · line ${note.target + 1}</em>`
          }<time>${new Date(note.at).toLocaleTimeString()}</time></li>`
      )
      .join("");
    pairsCount = pairs.count;
    pairsEl.textContent = `${pairs.count} pairs`;
    paint();
  } catch {
    statusEl.textContent = "server not answering";
  }
}

function resize() {
  const width = host.clientWidth || 900;
  const height = host.clientHeight || 700;
  renderer.setSize(width, height, false);
  camera.aspect = width / height;
  camera.updateProjectionMatrix();
  frame();
}
new ResizeObserver(resize).observe(host);
resize();

function animate() {
  requestAnimationFrame(animate);
  controls.update();
  renderer.render(scene, camera);
}
animate();

window.__ide = {
  setProse(text) {
    proseEl.value = text;
    analyseNow();
  },
  select,
  get rows() {
    return rows;
  },
};

document.getElementById("comment").addEventListener("keydown", (event) => {
  if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) {
    event.preventDefault();
    document.getElementById("send").click();
  }
});

Core.load("/")
  .then((loaded) => {
    core = loaded;
    statusEl.textContent = `core v${core.ex.crudity_version()} · ready`;
    // A window that is already holding prose should show it on the spine, not wait for a click.
    if (proseEl.value.trim()) analyseNow();
    setInterval(pollNotes, 1500);
    pollNotes();
  })
  .catch((error) => {
    statusEl.textContent = `core failed: ${error.message}`;
  });
