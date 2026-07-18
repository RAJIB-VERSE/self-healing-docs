#!/bin/sh
# Action entrypoint: derive PR context from the GitHub event, then run the pipeline.
set -e

cd "${GITHUB_WORKSPACE:-/github/workspace}"
git config --global --add safe.directory "$(pwd)"

if [ -z "$GITHUB_EVENT_PATH" ] || [ ! -f "$GITHUB_EVENT_PATH" ]; then
    echo "[dochealer] no event payload; nothing to do"
    exit 0
fi

BASE_REF=$(python -c "import json,os; e=json.load(open(os.environ['GITHUB_EVENT_PATH'])); print(e.get('pull_request',{}).get('base',{}).get('sha',''))")
HEAD_BRANCH=$(python -c "import json,os; e=json.load(open(os.environ['GITHUB_EVENT_PATH'])); print(e.get('pull_request',{}).get('head',{}).get('ref',''))")
PR_NUMBER=$(python -c "import json,os; e=json.load(open(os.environ['GITHUB_EVENT_PATH'])); print(e.get('pull_request',{}).get('number',0))")
LABELS=$(python -c "import json,os; e=json.load(open(os.environ['GITHUB_EVENT_PATH'])); print(','.join(l['name'] for l in e.get('pull_request',{}).get('labels',[])))")

if [ -z "$BASE_REF" ] || [ "$PR_NUMBER" = "0" ]; then
    echo "[dochealer] not a pull_request event; nothing to do"
    exit 0
fi

export DOCHEALER_PR_NUMBER="$PR_NUMBER"
# make sure the base commit exists locally (actions/checkout defaults to depth=1)
git fetch --no-tags --depth=50 origin "$BASE_REF" 2>/dev/null || true

exec dochealer run --base-ref "$BASE_REF" --head-branch "$HEAD_BRANCH" --labels "$LABELS"
