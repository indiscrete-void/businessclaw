#!/usr/bin/env bash
set -x
set -a
source .env
set +a 

if [ -z $OPENCLAW_HOME ]; then
  echo "OPENCLAW_HOME undefined"
  exit 1
fi

OPENCLAW_WORKSPACE="$OPENCLAW_HOME/workspace"
OPENCLAW_CONFIG="$OPENCLAW_HOME/openclaw.json"

function install-to-workspace {
  if [ -z $2 ]; then
    NAME="$1"
    SRC="./$NAME"
    DST="$OPENCLAW_WORKSPACE/$NAME"
  else
    SRC="$1"
    DST="$2"
  fi
  envsubst < "$SRC" > "$DST"
}

function merge-config {
  UPDATE="$1"
  TMP=$(mktemp)
  ./merge_json.py "$OPENCLAW_CONFIG" "$UPDATE" "$TMP"  
  install-to-workspace "$TMP" "$OPENCLAW_CONFIG"
}

install-to-workspace AGENTS.md
install-to-workspace TOOLS.md
merge-config openclaw.commands.json
if [ -n $OPENAI_PROXY ]; then
  merge-config openclaw.providers.json
fi
