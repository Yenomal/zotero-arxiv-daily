#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

# 直接使用默认配置
uv run src/zotero_arxiv_daily/main.py
