## 2026-11-24 — Scout UI assets, and the graph field's observed contract

Scout's icon, card, minimap, vertical and the three UI maps no longer name Frank's assets. The entry now
names three Scout images built by `tools/scout_ui.py` and the game's `default_shop` / `default_team_reveal`
/ `default_postgame_portrait` maps; Frank's portrait prefab and name logos are dropped (14 and 23 shipped
heroes carry no such fields). The addon is 45 files / 20,238,273 B, VPK 45 entries, all read back.

`m_sAG2VariationName` is answered from evidence, not assumption: only `hero_vampirebat` and `hero_necro`
set it among 69 blocks, both as `hero.vnmgraph+<hero>.vnmgraph`; the branch ships 51 such variations and 26
standalone auxiliary graphs that no entry names; both forms decompile as complete graphs, and the binaries
carry no literal to settle loader behaviour. A standalone graph is therefore recorded as unverified
(`ag2-hero-variation-required`), not claimed to load; a real `hero.vnmgraph+scout` would need the shipped
37-node locomotion/ability contract that the port's four clips do not cover.

- Evidence: `data/probes/2026-11-24-scout-ui-and-ag2-binding.md`, `artifacts/receipts/scout-ui.json`,
  `artifacts/receipts/scout-install.json`, `artifacts/receipts/scout-install-probe.json`,
  `artifacts/receipts/scout-port-app-probe.json`, `artifacts/scout-hero/ui-verify/`
- Checks: install probe 7/7, app probe 14/14, `pytest -q` 415 passed, both audits pass.
- Not observed: no session launched; in-game icon rendering, maps, selection and playback remain unobserved.
