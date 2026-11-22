## 2026-11-22 — a heredoc and a temporary probe are the same refusal, and the ledgers already said so

**Owner instruction, verbatim:** *"heredoc error despite the deadlock model forge already specifying not to use
heredocs or temporary probes record this failure properly"*, then: *"actually the deadlock model forge does have
record of me telling you not to use heredocs in the ledgers"*.

- **The rule lives in the ledgers, so the ledger is where it is looked up.** `logs/authority/2026-11-16-vpk-pack-and-adhoc-scripts.jsonl`
  holds the owner's words: *"How are you allowed to use ephemeral adhoc heredocs when there are refusals for that
  and temp directories?"*. `logs/authority/2026-11-20-shell-heredoc-and-guessed-blender-path.jsonl` holds collision
  `heredoc-command-limit`, a 9 KB rewrite truncated mid-string with `unterminated string literal`. `AGENTS-LOG.md`
  lines 14 and 3179 carry the same lesson from two sessions, and `ledger/ledger.jsonl` line 779 is a `fail` row for
  the inline heredoc that produced a copy rewrite. A grep of `AGENTS.md` alone is not a search for this rule.
- **A long program is written to a file, `ast.parse`d or `compile`d, and then run.** It is never typed inline
  through a shell heredoc, because bash reads JSONL, JSON and Markdown before Python does and can rewrite quotes,
  backslashes and terminators. The failure is silent: a command that wrote nothing looks like a command that ran.
- **A record is appended by `tools/record_row.py`.** It writes a ledger row, a row in any append-only jsonl, or a
  dated section of `AGENTS-LOG.md`, from flags and a body file; it opens with `newline="\n"`, refuses an empty field,
  a missing body and a path outside the repository, and only ever appends.
- **A temporary probe is a deletion, and deletion is the refusal.** A file that exists for one command and is then
  removed leaves nothing to read. Work that needs a script leaves the script, in `tools/` or `artifacts/probes/`,
  where the next session can run it.
- **This was the third occurrence, which makes it `limit-stale`, not an accident.** The record is
  `logs/records/2026-11-22-heredoc-and-temp-probe.md`, the collision row is
  `logs/authority/2026-11-22-heredoc-and-temp-probe.jsonl`, and the ledger carries the `fail` row.
