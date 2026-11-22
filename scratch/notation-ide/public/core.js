// The page side of the scalar ABI: write UTF-8 into the core's static input, ask it to
// classify, then read one row per line. Nothing is allocated and nothing is parsed from JSON.

const GAPS = [
  [1, "short-stub", "too short to carry a rule"],
  [2, "bold-lead-only", "the lead survived, the rule did not"],
  [4, "pointer-instead", "a pointer stands where the reasoning was"],
  [8, "no-verb", "a title posing as a rule"],
  [16, "semicolon-dump", "clauses and counters fused into one line"],
  [32, "unexplained-number", "a number with no unit or subject"],
  [64, "truncated", "the line ends mid-thought"],
  [128, "noun-chain", "six capitalised tokens with no verb between them"],
];

const GRADES = ["whole", "annotated", "lossy", "shorthand"];

export class Core {
  constructor(exports) {
    this.ex = exports;
    this.decoder = new TextDecoder();
    this.encoder = new TextEncoder();
  }

  static async load(base = "/") {
    const response = await fetch(`${base}notation_core.wasm`);
    if (!response.ok) throw new Error(`wasm fetch failed: ${response.status}`);
    const bytes = await response.arrayBuffer();
    const { instance } = await WebAssembly.instantiate(bytes, {});
    return new Core(instance.exports);
  }

  analyse(text) {
    const payload = this.encoder.encode(text);
    const capacity = this.ex.crudity_capacity();
    if (payload.length > capacity) throw new Error(`prose over ${capacity} bytes`);
    new Uint8Array(this.ex.memory.buffer, this.ex.crudity_input(), capacity).set(payload);
    const count = this.ex.crudity_analyse(payload.length);
    // The core reports offsets inside its input buffer, not inside linear memory. Reading from
    // the raw offset read the data segment instead, which decoded to boxes on every label.
    const base = this.ex.crudity_input();
    const memory = new Uint8Array(this.ex.memory.buffer);
    const rows = [];
    for (let index = 0; index < count; index += 1) {
      const start = base + this.ex.crudity_start(index);
      const length = this.ex.crudity_len(index);
      const mask = this.ex.crudity_mask(index);
      rows.push({
        index,
        text: this.decoder.decode(memory.slice(start, start + length)),
        words: this.ex.crudity_words(index),
        grade: GRADES[this.ex.crudity_grade(index)],
        gaps: GAPS.filter(([bit]) => (mask & bit) !== 0).map(([, code, detail]) => ({ code, detail })),
      });
    }
    return rows;
  }
}
