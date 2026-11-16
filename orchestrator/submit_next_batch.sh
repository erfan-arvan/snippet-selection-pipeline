#!/bin/bash -l
#SBATCH --job-name=legacy-next-batch
#SBATCH --output=%x.%j.out
#SBATCH --error=%x.%j.err
#SBATCH --account=mjk76
#SBATCH --partition=general
#SBATCH --qos=standard
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=128G
#SBATCH --time=3-00:00:00

# Continues the existing legacy-import auto run like the first run did: same run id, seed and
# batch size, so it picks up the next unprocessed methods of the same shuffled pool
# (slice with Specimin -> package -> check), and keeps taking 1000-method batches until THIS run
# has produced another ADD_TOTAL flagged findings, more than ADD_NON_NULLNESS of them non-nullness
# (the first run's rule: 100 / 50), or the pool runs out.
#
# Submit from orchestrator/:   sbatch submit_next_batch.sh                         (+100 / +50)
#                              ADD_TOTAL=150 ADD_NON_NULLNESS=75 sbatch submit_next_batch.sh
#                              BATCHES=2 sbatch submit_next_batch.sh  (exactly 2 batches, ignore targets)
# Resubmit the same command if it hits the 3-day limit: it resumes; the targets stay relative to
# the counts recorded when the run first started (stats/next_run_targets.json).
# Before running, the current stats/ and batch state are copied to stats/backup-<date>/.

set -uo pipefail
cd "$SLURM_SUBMIT_DIR"

module purge
module load easybuild
module load Java/17.0.15
module load GCCcore/13.3.0
module load Python/3.12.3
source .venv/bin/activate

export GRADLE_USER_HOME=/scratch/mjk76/ea442/.gradle-home
export PYTHONUNBUFFERED=1

RUN=/project/mjk76/ea442/snippet-selection-pipeline-output/legacy-import
BK="$RUN/stats/backup-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$BK"
cp -p "$RUN"/stats/*.jsonl "$RUN"/stats/*.csv "$BK"/ 2>/dev/null
cp -p "$RUN/manifest/auto_batch_state.json" "$BK"/ 2>/dev/null
echo "Backed up current results to $BK"
echo "Batch state before: $(cat "$RUN/manifest/auto_batch_state.json" 2>/dev/null)"

# Targets = counts so far + ADD_*. Stored on first use, so a resubmitted (timed-out) run keeps
# the same targets instead of moving them forward again.
T="$RUN/stats/next_run_targets.json"
if [ ! -f "$T" ]; then
  python3 - "$RUN/stats/auto_batch_results.jsonl" "$T" "${ADD_TOTAL:-100}" "${ADD_NON_NULLNESS:-50}" <<'PY'
import json, sys
src, out, add_t, add_n = sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4])
rows = [json.loads(l) for l in open(src) if l.strip()]
flag = [r for r in rows if r["status"] == "flagged"]
tot, nn = len(flag), sum(1 for r in flag if r["checker_id"] != "nullness")
json.dump({"start_total": tot, "start_non_nullness": nn,
           "min_total": tot + add_t, "min_non_nullness": nn + add_n}, open(out, "w"), indent=2)
PY
fi
echo "Targets: $(cat "$T")"
MIN_T=$(python3 -c "import json;print(json.load(open('$T'))['min_total'])")
MIN_N=$(python3 -c "import json;print(json.load(open('$T'))['min_non_nullness'])")

EXTRA=()
[ -n "${BATCHES:-}" ] && EXTRA=(--max-batches "$BATCHES")
python3 -u -m snippet_pipeline.cli -c ../config/pipeline.yaml --run-id legacy-import \
  --batch-size 1000 --min-total-flagged "$MIN_T" --min-non-nullness-flagged "$MIN_N" --auto-seed 1 \
  ${EXTRA[@]+"${EXTRA[@]}"} \
  auto
rc=$?
# once the targets are reached (not after a timeout), forget them so the next run starts fresh
grep -q "Stop condition met" "${SLURM_JOB_NAME:-legacy-next-batch}.${SLURM_JOB_ID:-x}.out" 2>/dev/null && mv "$T" "$T.done-$(date +%Y%m%d-%H%M%S)"
echo "Batch state after: $(cat "$RUN/manifest/auto_batch_state.json" 2>/dev/null)"
exit $rc
