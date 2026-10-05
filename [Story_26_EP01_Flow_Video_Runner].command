#!/bin/bash
cd "/Users/litarcopperkaikem/Documents/Repositiry/chrome-automation-web-template"
SCENES="${1:-1-5}"
exec .venv/bin/python scripts/flow_batch_runner.py \
  --story-path "/Users/litarcopperkaikem/Library/CloudStorage/GoogleDrive-cheetah6541@gmail.com/My Drive/Knowledge Vault/Project/AI shorts/Channels/2 - ผักกาดการละคร - ละครไทย/26" \
  --ep 1 \
  --scenes "$SCENES" \
  --aspect-ratio "9:16" \
  --batch-size 3 \
  --force \
  --no-capcut
