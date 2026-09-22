#!/bin/sh
# Run the full carbon unit test suite.
#
# Usage: ./test.sh [trial args...]
#   ./test.sh                          # run all tests
#   ./test.sh carbon.tests.test_storage  # run a specific module
set -u
cd "$(dirname "$0")"

export GRAPHITE_NO_PREFIX=true
export PYTHONPATH="lib${PYTHONPATH:+:$PYTHONPATH}"

if command -v trial >/dev/null 2>&1; then
  TRIAL="trial"
else
  TRIAL="python -m twisted.trial"
fi

if [ $# -gt 0 ]; then
  exec $TRIAL "$@"
else
  exec $TRIAL carbon
fi
