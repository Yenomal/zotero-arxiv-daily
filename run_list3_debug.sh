#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

# 启用第三阶段评分
# 打开调试日志
# 缩小初排规模
# 缩小二次重排规模
uv run src/zotero_arxiv_daily/main.py \
  scorer.enabled=true \
  executor.debug=true \
  executor.max_paper_num=3 \
  scorer.final_top_k=3
