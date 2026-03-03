# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Tool for downloading 10-K annual reports from SEC EDGAR. Provides a CLI (`pull_10ks.py`) and a Streamlit web app (`app.py`).

## Commands

```bash
# Run CLI
python pull_10ks.py --tickers AAPL MSFT --years 2022 2023 --output ./reports [--format pdf|html]

# Run Streamlit web app
streamlit run app.py

# Run all tests
pytest test_pull_10ks.py

# Run a specific test class or test
pytest test_pull_10ks.py::TestCollect10Ks
pytest test_pull_10ks.py::TestDownload10k::test_native_pdf

# Install dependencies
pip install -r requirements.txt
```

## Architecture

- **`pull_10ks.py`** — Core module. `EdgarClient` class handles all SEC EDGAR API interaction: ticker→CIK lookup, filing search with pagination, and download with PDF conversion fallback. CLI entry point via `main()`.
- **`app.py`** — Streamlit web UI. Accepts tickers/years/format, uses `EdgarClient` to fetch filings, packages results into a ZIP for download.
- **`test_pull_10ks.py`** — pytest tests using `unittest.mock`. Tests cover filing filtering (`_collect_10ks`), CIK lookup, filing search with pagination, download logic, and the weasyprint URL fetcher.

### SEC API flow

`get_cik(ticker)` → `get_10k_filings(cik, years)` → `download_10k(cik, filing, ...)`. All HTTP requests go through a shared `requests.Session` with rate limiting (`REQUEST_DELAY = 0.15s`) to stay under SEC's 10 req/sec limit.

### PDF conversion

`download_10k` first checks the filing index for a native PDF. If none exists and `convert=True`, it uses weasyprint with a custom URL fetcher (`_make_fetcher`) that injects the SEC User-Agent header. Falls back to raw HTML if weasyprint is unavailable.

## Dependencies

`requests`, `streamlit`, `weasyprint` (optional for PDF conversion). Tests require `pytest` (not in requirements.txt).
