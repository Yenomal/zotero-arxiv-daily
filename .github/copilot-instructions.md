# Copilot Instructions

## Project Overview

This project recommends recent arXiv papers based on a user's Zotero library, writes selected papers back to Zotero, saves PDFs locally, and creates Zotero notes with TLDR and LLM-based scoring details.

## Commands

```bash
uv sync
uv run src/zotero_arxiv_daily/main.py
uv run pytest
```

## Architecture

The application is orchestrated by `Executor` in `src/zotero_arxiv_daily/executor.py`.

Main flow:

1. Fetch Zotero corpus
2. Filter corpus by Zotero collection path
3. Retrieve arXiv candidates
4. Filter candidates already present in the output Zotero collection
5. Rerank candidates by embedding similarity
6. Fetch and clean full text for selected papers
7. Score papers with LLM
8. Save PDFs locally
9. Write metadata, notes, and linked attachments to Zotero

## Configuration

Hydra composes:

1. `config/base.yaml`
2. `config/custom.yaml`

Use `config/custom.yaml` or environment interpolation for private values.

## Notes

The project is designed primarily for local execution because local PDF files and Zotero linked attachments depend on the user's filesystem.
