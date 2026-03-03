# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Tool for downloading 10-K annual reports from SEC EDGAR. Provides a CLI (`pull_10ks/cli.py`), a Python package (`pull_10ks/`), and a Streamlit web app (`app.py`).

## Commands

```bash
# Install in editable mode (with dev dependencies)
pip install -e ".[dev]"

# Run CLI (after install)
pull-10ks --tickers AAPL MSFT --years 2022 2023 --output ./reports [--format pdf|html]

# Run CLI (without install)
python -m pull_10ks.cli --tickers AAPL MSFT --years 2022 2023 --output ./reports [--format pdf|html]

# Run Streamlit web app
streamlit run app.py

# Run all tests
pytest tests/

# Run a specific test class or test
pytest tests/test_client.py::TestCollect10Ks
pytest tests/test_client.py::TestDownload10k::test_downloads_native_pdf_when_available

# Install dependencies (Streamlit Cloud compatibility)
pip install -r requirements.txt
```

## Architecture

- **`pull_10ks/`** — Python package.
  - **`client.py`** — `EdgarClient` class handles all SEC EDGAR API interaction: ticker->CIK lookup, filing search with pagination, and download with PDF conversion fallback. Module constants: `COMPANY_TICKERS_URL`, `SUBMISSIONS_BASE`, `ARCHIVES_BASE`, `REQUEST_DELAY`.
  - **`cli.py`** — CLI entry point via `main()`. Installed as `pull-10ks` console script.
  - **`__init__.py`** — Re-exports `EdgarClient` and constants for convenience (`from pull_10ks import EdgarClient`).
- **`app.py`** — Streamlit web UI. Accepts tickers/years/format, uses `EdgarClient` to fetch filings, packages results into a ZIP for download.
- **`tests/test_client.py`** — pytest tests using `unittest.mock`. Tests cover filing filtering (`_collect_10ks`), CIK lookup, filing search with pagination, download logic, and the weasyprint URL fetcher.
- **`pyproject.toml`** — PEP 621 project metadata, dependencies, and console script entry point.

### SEC API flow

`get_cik(ticker)` -> `get_10k_filings(cik, years)` -> `download_10k(cik, filing, ...)`. All HTTP requests go through a shared `requests.Session` with rate limiting (`REQUEST_DELAY = 0.15s`) to stay under SEC's 10 req/sec limit.

### PDF conversion

`download_10k` first checks the filing index for a native PDF. If none exists and `convert=True`, it uses weasyprint with a custom URL fetcher (`_make_fetcher`) that injects the SEC User-Agent header. Falls back to raw HTML if weasyprint is unavailable.

## Dependencies

`requests`, `weasyprint` (optional for PDF conversion). Optional: `streamlit` (web app), `pytest` (tests). See `pyproject.toml` for full specification.
