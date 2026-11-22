#!/usr/bin/env bash
# Register the name judge with the Debian axis, attest it, and witness the name-judge artifact.
# The axis refuses an unattested driver, so the order matters and every refusal is printed as is.
#
#   bash tools/axis_push.sh <sha256-of-name-judge.json>

set -u
# The family hashes with blake3, so the caller passes the blake3 hex and the receipt records it
# as `expected`. The axis itself still recomputes sha256, so the same bytes are presented under
# both names and the receipt says which is which instead of pretending one is the other.
BLAKE="${1:?the artifact blake3 digest is required}"
case "$BLAKE" in
  blake3:*) ;;
  *) BLAKE="blake3:$BLAKE" ;;
esac
ARTIFACT="${2:-/mnt/c<home>/Documents/deadlock-model-forge/scratch/notation-ide/artifacts/name-judge.json}"
AXIS="http://127.0.0.1:8787"
DRIVER="notation-name-judge"
EXPIRES=$(( $(date +%s) * 1000 + 604800000 ))

post() {
  curl -s -X POST "$AXIS$1" -H "content-type: application/json" -d "$2"
  echo
}

echo "== state before =="
curl -s "$AXIS/api/axis/state" | head -c 220
echo

echo "== register =="
post /api/axis/drivers "{\"id\":\"$DRIVER\",\"kind\":\"cua-node\",\"revision\":\"0.1.0\",\"capabilities\":[\"witness\"]}"

echo "== attest =="
post /api/axis/attest "{\"driver\":\"$DRIVER\",\"verifier\":\"deadlock-model-forge/scratch/notation-ide/tools/name_prose.py\",\"expiresAt\":$EXPIRES}"

echo "== ticket =="
TICKET=$(curl -s -X POST "$AXIS/api/axis/tickets" -H "content-type: application/json" \
  -d "{\"driver\":\"$DRIVER\",\"action\":\"witness\"}")
echo "$TICKET"
ID=$(printf '%s' "$TICKET" | sed -n 's/.*"id":"\([^"]*\)".*/\1/p')

if [ -z "$ID" ]; then
  echo "axis: no ticket id, stopping before the act"
  exit 1
fi

echo "== act with bytes =="
# A receipt that only names a digest records an absence: the axis states `read` only when it
# recomputed the digest from bytes it was handed. The act therefore carries the document.
/usr/local/bin/node -e '
  const fs = require("fs");
  const crypto = require("crypto");
  const bytes = fs.readFileSync(process.argv[1]);
  const hex = crypto.createHash("sha256").update(bytes).digest("hex");
  // The presented digest must carry the axis prefix, or a byte-identical document reads as
  // a mismatch.
  process.stdout.write(JSON.stringify({
    ticket: process.argv[2], action: "witness",
    digest: "sha256:" + hex,
    expected: process.argv[3],
    observed: "sha256:" + hex,
    presenter: "name_prose.py", bytes: bytes.toString("utf8"),
  }));
' "$ARTIFACT" "$ID" "$BLAKE" > /tmp/act.json

curl -s -X POST "$AXIS/api/axis/act" -H "content-type: application/json" --data-binary @/tmp/act.json
printf '\n'

echo "== state after =="
curl -s "$AXIS/api/axis/state" | head -c 400
echo
curl -s "$AXIS/api/axis/review" | head -c 300
echo
