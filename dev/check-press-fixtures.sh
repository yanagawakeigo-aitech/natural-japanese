#!/usr/bin/env bash
# Fixture regression check for skills/press-japanese/scripts/factcheck.py:
# verify the checker reports the expected numbers of findings on the checked-in
# fixtures (a faithful draft must have zero unsupported findings; the unfaithful
# draft must keep flagging each deliberately planted fabrication).
#
# NOTE: If you intentionally change factcheck.py or scripts/fixtures/ under
# skills/press-japanese/, update the expected counts below to match.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FC="${REPO_ROOT}/skills/press-japanese/scripts/factcheck.py"
FX="${REPO_ROOT}/skills/press-japanese/scripts/fixtures"

# Expected counts: "<total_findings> <unsupported_total>"
EXPECTED_FAITHFUL="2 0"
EXPECTED_UNFAITHFUL="24 9"

run_counts() {
  local draft="$1" json_out status
  json_out="$(mktemp)"
  local cleanup_json_out="${json_out}"
  trap 'rm -f "${cleanup_json_out}"' RETURN
  set +e
  uv run "${FC}" "${draft}" --source "${FX}/source.md" --json >"${json_out}"
  status=$?
  set -e
  if [ "${status}" -ne 0 ]; then
    echo "error: factcheck run failed (exit=${status}) for ${draft}" >&2
    return 1
  fi
  python3 -c '
import json, sys
d = json.load(sys.stdin)["stats"]
print(d["total_findings"], d["unsupported_total"])
' <"${json_out}"
}

fail=0
check() {
  local label="$1" expected="$2" actual="$3"
  if [ "${actual}" != "${expected}" ]; then
    echo "FAIL: ${label}: expected '${expected}' (total unsupported), got '${actual}'" >&2
    fail=1
  else
    echo "OK: ${label}: ${actual} (total unsupported)"
  fi
}

check "draft-faithful.md" "${EXPECTED_FAITHFUL}" "$(run_counts "${FX}/draft-faithful.md")"
check "draft-unfaithful.md" "${EXPECTED_UNFAITHFUL}" "$(run_counts "${FX}/draft-unfaithful.md")"

if [ "${fail}" -ne 0 ]; then
  echo "press-japanese fixture regression check FAILED." >&2
  exit 1
fi
echo "press-japanese fixture regression check PASSED."
