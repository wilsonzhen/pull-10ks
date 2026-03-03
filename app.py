"""Streamlit web app for downloading 10-K annual reports from SEC EDGAR."""

import io
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path

import streamlit as st

from pull_10ks import EdgarClient

st.set_page_config(page_title="10-K Downloader", page_icon=":page_facing_up:")
st.title("10-K Report Downloader")
st.caption("Download annual reports from SEC EDGAR")

# --- Inputs -------------------------------------------------------------------

tickers_raw = st.text_input(
    "Tickers",
    placeholder="AAPL, MSFT, GOOG",
    help="Comma or space separated stock ticker symbols",
)

col1, col2, col3 = st.columns(3)
current_year = datetime.now().year
start_year = col1.number_input("Start year", min_value=1993, max_value=current_year, value=current_year - 1)
end_year = col2.number_input("End year", min_value=1993, max_value=current_year, value=current_year)
fmt = col3.radio("Format", ["HTML", "PDF"], horizontal=True)
group_by_ticker = st.checkbox("Create a separate folder for each ticker")

# --- Download -----------------------------------------------------------------

if st.button("Download Reports", type="primary"):
    # Parse tickers
    tickers = [t.strip().upper() for t in tickers_raw.replace(",", " ").split() if t.strip()]
    if not tickers:
        st.error("Enter at least one ticker.")
        st.stop()
    if start_year > end_year:
        st.error("Start year must be ≤ end year.")
        st.stop()

    years = set(range(int(start_year), int(end_year) + 1))
    convert = fmt == "PDF"
    client = EdgarClient("AnnualReportDownloader admin@example.com")

    # Count total work units for the progress bar (lookup + filings per ticker).
    # We don't know filing counts upfront, so we estimate: 1 step per ticker for
    # lookup, then 1 step per filing found.
    progress = st.progress(0, text="Starting...")
    status = st.empty()
    downloaded_files: list[Path] = []
    errors: list[str] = []

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)

        # Phase 1: resolve tickers and find filings
        ticker_filings: list[tuple[str, str, list]] = []  # (ticker, cik, filings)
        for i, ticker in enumerate(tickers):
            status.text(f"Looking up {ticker}...")
            cik = client.get_cik(ticker)
            if not cik:
                errors.append(f"Unknown ticker: {ticker}")
                continue
            filings = client.get_10k_filings(cik, years)
            if not filings:
                errors.append(f"{ticker}: no 10-K filings for {sorted(years)}")
                continue
            ticker_filings.append((ticker, cik, filings))

        # Phase 2: download with real progress
        total = sum(len(f) for _, _, f in ticker_filings)
        if total == 0 and not errors:
            errors.append("No filings found for the given tickers and years.")

        for ticker, cik, filings in ticker_filings:
            ticker_dir = tmp / ticker if group_by_ticker else tmp
            for filing in filings:
                done = len(downloaded_files)
                progress.progress(done / total if total else 0, text=f"{ticker} — {filing['reportDate']}")
                try:
                    path = client.download_10k(cik, filing, ticker_dir, ticker, convert)
                    downloaded_files.append(path)
                except Exception as e:
                    errors.append(f"{ticker} {filing['reportDate']}: {e}")

        progress.progress(1.0, text="Done!")

        # Show errors
        for err in errors:
            st.warning(err)

        # Build zip
        if downloaded_files:
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
                for p in downloaded_files:
                    if group_by_ticker:
                        arcname = f"{p.parent.name}/{p.name}"
                    else:
                        arcname = p.name
                    zf.write(p, arcname)
            buf.seek(0)

            st.download_button(
                label=f"Download {len(downloaded_files)} report(s) as ZIP",
                data=buf,
                file_name="10k_reports.zip",
                mime="application/zip",
                type="primary",
            )
        elif not errors:
            st.info("No reports downloaded.")
