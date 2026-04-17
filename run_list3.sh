#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

# 启用第三阶段评分
uv run src/zotero_arxiv_daily/main.py scorer.enabled=true
