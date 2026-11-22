**Owner, verbatim:** *"Whatever decision you made to use a heredoc instead of following family convention needs
to be recorded and fixed so it can never happen again"*, then *"continue the whole point of patch probes is so we
can atually fucking see the things that happened per diff in each project?"*.

**What was decided, and it was wrong.** While extending the Soul Lens strip with the shop's recommended list and
Statlocker's rankings, the turn's own plan said: *write new `panorama/scripts/soul_lens.js` fully via heredoc python
… same for XML rows*. That is `cat > file <<'EOF'` and `python - <<'PY'` from `run_terminal_command`. The reason was
an assumption, not a measurement: that the editor file tools could only reach the chat workspace
(`deadlock-model-forge`) and the mod lives in a sibling repository (`soul-lens`).

**Measured, so the assumption is dead.** `write_file` with the absolute path
the mod repository's own logs/records.md succeeded, so every file of that repository is editable with
the same tools as this one. The same probe exposed a second defect: the write **replaced** that file instead of
appending to it, and `git checkout -- logs/records.md` was needed to restore it. `git status --short` then showed
only the untracked `data/probe-*` extraction folders, so nothing was lost — but a replace tool on an append target
is the defect the probe exists to show.

**The rule this adds.** No heredoc for code, data or records in any project: not `<<'PY'`, not `<<EOF`, not
`python - <<`, not `cat > f <<`. A heredoc carries the payload through the shell, so one lost terminator loses the
whole command and writes nothing while looking like it ran — the family has this failure four times already
(`AGENTS-LOG.md`, `logs/authority/2026-11-16-vpk-pack-and-adhoc-scripts.jsonl`,
`logs/authority/2026-11-20-shell-heredoc-and-guessed-blender-path.jsonl` = `heredoc-command-limit`, and
`ledger/ledger.jsonl` line 779). File edits go through the editor file tools, which accept the absolute path of a
sibling project's file. Records go through `tools/record_row.py`. A probe is a **kept** file (`data/probes/`,
`logs/probes/`) that states what was attempted and what was measured, so the diff shows what happened in that
project; it is not deleted after it runs.

**Enforcement, two surfaces.** `tools/heredoc_audit.py` scans this repository's executable sources and prints
`heredoc-invocation` for each match; the Soul Lens repository's `tools/gate.py` grew a `no-heredoc` leg over the
same pattern. Neither can see a command line, so the section above is the part a session is asked to read; the
checks catch the case where the heredoc is written into a file and committed.

**Where the probe is.** `soul-lens/data/probes/2026-11-22-heredoc-code-authoring.md`, with the record line in
`soul-lens/logs/records.md`. It is outside this repository on purpose: the failure happened in that project, and
the probe is read next to that project's diff.
