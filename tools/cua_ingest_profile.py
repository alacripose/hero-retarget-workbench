#!/usr/bin/env python3
"""Ingest a staged family-prose profile into the existing CUA corpus without replacing it.

The M2 ingest rewrites the whole corpus from roots it can see. The Debian host cannot see the
Windows drives, so this reader takes a staged tree and appends new documents to the corpus that
is already on the host. A document is identified by `project/relative-path`; an unchanged
sha256 is a duplicate, a changed one replaces the old row, and every row keeps its receipt.

    python tools/cua_ingest_profile.py --profile /path/profile.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))
import cua_corpus as corpus  # noqa: E402

CORPUS = corpus.CORPUS
RECEIPTS = corpus.RECEIPTS
CORPUS_DIR = corpus.CORPUS_DIR
MANIFEST = CORPUS_DIR / "manifest.family-prose.json"
SKIP = {".git", "node_modules", "target", "build", "dist", "obj", "bin", "__pycache__",
        ".cache", ".venv", "venv", "coverage", ".next", "injest", "store"}


def load_jsonl(path: Path) -> dict[str, dict]:
    if not path.is_file():
        return {}
    rows = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            rows[row["doc_id"]] = row
    return rows


def decode_profile_document(raw: bytes) -> tuple[str | None, str]:
    """Preserve UTF-8 that carries an embedded NUL; the M2 binary rule is for unknown encodings."""
    text, encoding = corpus.decode_document(raw)
    if text is not None:
        return text, encoding
    if b"\x00" in raw:
        try:
            return raw.decode("utf-8-sig"), "utf-8-nul"
        except UnicodeDecodeError:
            pass
    return None, encoding


def profile_files(root: Path, suffixes: set[str], ignored: set[str]):
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if any(part in ignored or (part.startswith(".") and part != ".agents")
               for part in path.relative_to(root).parts):
            continue
        if path.suffix.lower() in suffixes and path.stat().st_size:
            yield path


def read_profile(path: Path) -> dict:
    profile = json.loads(path.read_text(encoding="utf-8"))
    if profile.get("schema") != "cua.corpus.ingest-profile/2":
        raise SystemExit("profile-schema: expected cua.corpus.ingest-profile/2")
    if not profile.get("roots"):
        raise SystemExit("profile-roots: no roots")
    return profile


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="append a staged profile to the CUA corpus")
    parser.add_argument("--profile", required=True)
    args = parser.parse_args(argv)
    profile = read_profile(Path(args.profile))
    suffixes = {s.lower() for s in profile.get("include_suffixes", [".md", ".txt"])}
    ignored = SKIP | set(profile.get("skip_dirs", []))
    limit = int(profile.get("max_body_bytes", corpus.BODY_LIMIT))
    roots = [Path(root) for root in profile["roots"]]
    for root in roots:
        if not root.is_dir():
            raise SystemExit(f"profile-root-absent: {root}")

    existing = load_jsonl(CORPUS)
    before = len(existing)
    added = updated = duplicates = 0
    excluded: list[dict] = []
    encodings: dict[str, int] = {}
    source_bytes = 0
    seen_files = 0

    for root in roots:
        for path in profile_files(root, suffixes, ignored):
            seen_files += 1
            relative = path.relative_to(root)
            if len(relative.parts) < 2:
                project, inner = profile.get("root_project", root.name), str(relative)
            else:
                project, inner = relative.parts[0], str(Path(*relative.parts[1:])).replace("\\", "/")
            try:
                raw = path.read_bytes()
            except OSError:
                excluded.append({"project": project, "path": inner, "reason": "unreadable-os"})
                continue
            source_bytes += len(raw)
            text, encoding = decode_profile_document(raw)
            if text is None:
                excluded.append({"project": project, "path": inner, "bytes": len(raw),
                                 "reason": "unreadable-encoding" if encoding == "binary" else encoding})
                continue
            sha = "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()
            doc_id = corpus.document_id(project, inner)
            if doc_id in existing and existing[doc_id].get("sha256") == sha:
                duplicates += 1
                continue
            payload = corpus.admission_payload(project, inner, text, sha, encoding)
            if len(payload) > limit:
                excluded.append({"project": project, "path": inner, "bytes": len(payload),
                                 "reason": "body-limit"})
                continue
            row = {"schema": corpus.SCHEMA, "doc_id": doc_id, "project": project, "path": inner,
                   "sha256": sha, "encoding": encoding, "bytes": len(text.encode("utf-8")),
                   "text": text}
            if doc_id in existing:
                updated += 1
            else:
                added += 1
            existing[doc_id] = row
            encodings[encoding] = encodings.get(encoding, 0) + 1

    rows = [existing[key] for key in sorted(existing)]
    # Receipts are recomputed from the rows that remain, never copied from a possibly nested row.
    receipt_rows = [{"doc_id": row["doc_id"], "sha256": row["sha256"],
                     "receipt": corpus.digest({"schema": corpus.SCHEMA_ID,
                                                "doc_id": row["doc_id"],
                                                "sha256": row["sha256"],
                                                "bytes": row["bytes"]})}
                    for row in rows]
    CORPUS_DIR.mkdir(parents=True, exist_ok=True)
    CORPUS.write_text("".join(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n"
                              for row in rows), encoding="utf-8", newline="\n")
    RECEIPTS.write_text("".join(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n"
                                for row in receipt_rows), encoding="utf-8", newline="\n")
    report = {
        "schema": "cua.corpus.profile-ingest/2",
        "at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "profile": profile.get("name", Path(args.profile).name),
        "profile_digest": "sha256:" + hashlib.sha256(Path(args.profile).read_bytes()).hexdigest(),
        "roots": [str(root) for root in roots],
        "include_suffixes": sorted(suffixes),
        "files_seen": seen_files,
        "documents_before": before,
        "documents": len(rows),
        "added": added,
        "updated": updated,
        "duplicates": duplicates,
        "excluded": excluded,
        "encodings": dict(sorted(encodings.items())),
        "source_bytes": source_bytes,
        "corpus_bytes": CORPUS.stat().st_size,
        "corpus_sha256": "sha256:" + hashlib.sha256(CORPUS.read_bytes()).hexdigest(),
        "receipts": len(receipt_rows),
    }
    MANIFEST.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({key: report[key] for key in
                      ("profile", "documents_before", "documents", "added", "updated",
                       "duplicates", "excluded", "corpus_bytes", "receipts")}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
