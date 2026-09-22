#!/usr/bin/env bash
#
# Manually run Carbon's unit test suite with Twisted Trial.
#
# Usage:
#   ./test.sh                       # run every unit test under carbon.tests
#   ./test.sh storage writer        # run carbon.tests.test_storage + test_writer
#   ./test.sh test_storage.TestCase.test_foo   # passthrough a trial test name
#
# Override the interpreter with PYTHON=/path/to/python if needed.
set -euo pipefail

cd "$(dirname "$0")"

PYTHON="${PYTHON:-python3}"
if ! "$PYTHON" -c "import twisted" >/dev/null 2>&1; then
  for candidate in /opt/homebrew/bin/python3 python3 python; do
    if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c "import twisted" >/dev/null 2>&1; then
      PYTHON="$candidate"
      break
    fi
  done
fi

export GRAPHITE_NO_PREFIX=true
export PYTHONPATH="$(pwd)/lib${PYTHONPATH:+:$PYTHONPATH}"

TARGETS=()
for arg in "$@"; do
  case "$arg" in
    test_*)
      TARGETS+=("carbon.tests.$arg")
      ;;
    *)
      TARGETS+=("carbon.tests.test_$arg")
      ;;
  esac
done

if [ "${#TARGETS[@]}" -eq 0 ]; then
  echo "==> Running all Carbon unit tests with $PYTHON"
  exec "$PYTHON" -m twisted.trial carbon
else
  echo "==> Running: ${TARGETS[*]} with $PYTHON"
  exec "$PYTHON" -m twisted.trial "${TARGETS[@]}"
fi
