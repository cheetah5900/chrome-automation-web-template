#!/bin/bash
cd "/Users/litarcopperkaikem/Documents/Repositiry/chrome-automation-web-template"
SCENES="${1:-1-5}"
EXTRA_ARGS="${@:2}"
exec .venv/bin/python scripts/flow_storyboard_runner.py \
  --story-path "/Users/litarcopperkaikem/Library/CloudStorage/GoogleDrive-cheetah6541@gmail.com/My Drive/Knowledge Vault/Project/AI shorts/Channels/2 - ผักกาดการละคร - ละครไทย/27" \
  --ep 2 \
  --scenes "$SCENES" \
  --aspect-ratio "9:16" \
  --force \
  $EXTRA_ARGS
