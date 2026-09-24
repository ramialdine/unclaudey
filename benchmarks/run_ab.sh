#!/usr/bin/env bash
# A/B: Anthropic's frontend-design skill vs unclaudey on the same briefs, headless Claude Code.
# Each run gets a fresh folder with exactly one design skill installed and the same prompt.
# Usage: benchmarks/run_ab.sh [brief-id ...]      (needs: claude, uv, jq; runs in parallel)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
RUNS="${RUNS:-$ROOT/benchmarks/runs/$(date +%Y%m%d-%H%M)}"
mkdir -p "$RUNS/_skills/frontend-design"
curl -fsSL https://raw.githubusercontent.com/anthropics/skills/main/skills/frontend-design/SKILL.md \
  -o "$RUNS/_skills/frontend-design/SKILL.md"
curl -fsSL https://raw.githubusercontent.com/anthropics/skills/main/skills/frontend-design/LICENSE.txt \
  -o "$RUNS/_skills/frontend-design/LICENSE.txt"

ids=("$@")
if [ ${#ids[@]} -eq 0 ]; then ids=($(jq -r '.[].id' "$ROOT/benchmarks/briefs.json")); fi

run_one() {
  local id="$1" cond="$2" dir="$RUNS/$1/$2"
  mkdir -p "$dir/.claude/skills"
  if [ "$cond" = "baseline" ]; then
    cp -R "$RUNS/_skills/frontend-design" "$dir/.claude/skills/"
  else
    cp -R "$ROOT/skills/unclaudey" "$dir/.claude/skills/"
  fi
  local brief; brief="$(jq -r --arg id "$id" '.[] | select(.id==$id) | .brief' "$ROOT/benchmarks/briefs.json")"
  local prompt="Design and build this as a finished, production-quality single page: index.html in the current folder (inline CSS/JS; Google Fonts allowed). Use your design skill. This is a local preview: work autonomously without asking questions, and if a tool needs an API key that isn't configured, use its preview/draft mode. Brief: $brief"
  ( cd "$dir" && claude -p "$prompt" \
      --permission-mode acceptEdits \
      --allowedTools "Skill" "Read" "Write" "Edit" "Glob" "Grep" "Bash(uv run:*)" "Bash(ls:*)" "Bash(mkdir:*)" "Bash(cat:*)" \
      --output-format json > transcript.json 2> stderr.log ) || echo "run failed: $id/$cond" >&2
  echo "done: $id/$cond"
}

for id in "${ids[@]}"; do
  run_one "$id" baseline &
  run_one "$id" unclaudey &
done
wait
echo "runs in $RUNS"
