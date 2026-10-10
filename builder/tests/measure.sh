#!/bin/bash
# Build with our builder, then measure: 3 reps + 5 styles.
# usage: builder/tests/measure.sh <tag> <brief letter for run_cases, or ALL> <brief files...>   (CASES=<file> for own cases)
cd "$(dirname "$0")/../.."
TAG=$1; B=$2; shift 2
mkdir -p results
python3 -u builder/build.py "$@" > results/$TAG-build.log 2>&1
SLOT=ours-$(basename "${@: -1}" .md)
A=$(python3 -c "import json;print(json.load(open('.freya-agents.json'))['$SLOT']['agent_id'])")
echo "== built $SLOT agent $A"; grep -E "agent done|submitted|done in" results/$TAG-build.log
BR=""; [ "$B" != "ALL" ] && BR="--brief $B"; [ -n "$CASES" ] && BR="$BR --cases $CASES"
python3 -u tools/run_cases.py $A $BR --reps 3 --rerun-if-slow 1 --out results/$TAG-reps3.json > results/$TAG-reps3.log 2>&1
grep -E "^(PASS|FAIL) PUB-[0-9]+ [0-9]/|passed \(" results/$TAG-reps3.log
for s in pieces corrects talkative asks_back in_words; do
  python3 -u tools/run_cases.py $A $BR --style $s --rerun-if-slow 1 --out results/$TAG-style-$s.json > results/$TAG-style-$s.log 2>&1
  echo "== $s: $(tail -1 results/$TAG-style-$s.log | cut -c1-12)"; grep '^FAIL' results/$TAG-style-$s.log
done
