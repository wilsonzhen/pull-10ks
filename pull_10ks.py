#!/usr/bin/env python
"""Download 10-K annual reports from SEC EDGAR as PDFs.

Usage:
    python pull_10ks.py --tickers AAPL MSFT --years 2022 2023 --output ./reports

SEC requires a User-Agent header identifying you. Override the default with --user-agent.
"""

import argparse
import sys
import time
from pathlib import Path

import requests

COMPANY_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SUBMISSIONS_BASE = "https://data.sec.gov/submissions"
ARCHIVES_BASE = "https://www.sec.gov/Archives/edgar/data"
REQUEST_DELAY = 0.15  # seconds between requests — SEC allows max 10/sec


class EdgarClient:
    """SEC EDGAR API client with rate limiting."""

    def __init__(self, user_agent):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": user_agent,
            "Accept-Encoding": "gzip, deflate",
        })
        self._cik_map = None

    def _get_json(self, url):
        time.sleep(REQUEST_DELAY)
        resp = self.session.get(url)
        resp.raise_for_status()
        return resp.json()

    def _download(self, url, path):
        time.sleep(REQUEST_DELAY)
        resp = self.session.get(url, stream=True)
        resp.raise_for_status()
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)

    # -- Ticker / CIK lookup --------------------------------------------------

    def get_cik(self, ticker):
        """Return CIK string for a ticker, or None."""
        if self._cik_map is None:
            data = self._get_json(COMPANY_TICKERS_URL)
            self._cik_map = {
                v["ticker"].upper(): str(v["cik_str"]) for v in data.values()
            }
        return self._cik_map.get(ticker.upper())

    # -- Filing search ---------------------------------------------------------

    def get_10k_filings(self, cik, years):
        """Return list of 10-K filing dicts whose report-period year is in *years*."""
        padded = str(cik).zfill(10)
        data = self._get_json(f"{SUBMISSIONS_BASE}/CIK{padded}.json")

        filings = []
        self._collect_10ks(data["filings"]["recent"], years, filings)

        # Older filings may be paginated into separate JSON files
        for ref in data["filings"].get("files", []):
            older = self._get_json(f"{SUBMISSIONS_BASE}/{ref['name']}")
            self._collect_10ks(older, years, filings)

        return filings

    def _collect_10ks(self, records, years, out):
        forms = records.get("form", [])
        accessions = records.get("accessionNumber", [])
        filing_dates = records.get("filingDate", [])
        report_dates = records.get("reportDate", [])
        primary_docs = records.get("primaryDocument", [])

        for i, form in enumerate(forms):
            if form != "10-K":
                continue
            if i >= len(accessions) or i >= len(primary_docs):
                continue

            report_date = (
                report_dates[i]
                if i < len(report_dates) and report_dates[i]
                else filing_dates[i] if i < len(filing_dates) else None
            )
            if not report_date:
                continue

            if int(report_date[:4]) in years:
                out.append({
                    "accessionNumber": accessions[i],
                    "filingDate": filing_dates[i] if i < len(filing_dates) else "",
                    "reportDate": report_date,
                    "primaryDocument": primary_docs[i],
                })

    # -- Download --------------------------------------------------------------

    def download_10k(self, cik, filing, output_dir, ticker, convert=True):
        """Download a single 10-K.  Prefers native PDF; falls back to HTML→PDF."""
        accession = filing["accessionNumber"]
        acc_clean = accession.replace("-", "")
        report_date = filing["reportDate"]
        base_url = f"{ARCHIVES_BASE}/{cik}/{acc_clean}"
        stem = f"{ticker}_10K_{report_date}"

        primary = filing["primaryDocument"]
        primary_url = f"{base_url}/{primary}"

        if convert:
            # 1) Check the filing index for an existing PDF
            try:
                index = self._get_json(f"{base_url}/index.json")
                items = index.get("directory", {}).get("item", [])
                pdfs = [
                    it["name"]
                    for it in items
                    if it.get("name", "").lower().endswith(".pdf")
                ]
            except Exception:
                pdfs = []

            if pdfs:
                out = output_dir / f"{stem}.pdf"
                print(f"    Downloading PDF: {pdfs[0]}")
                self._download(f"{base_url}/{pdfs[0]}", out)
                return out

            # 2) No native PDF — convert HTML to PDF
            try:
                from weasyprint import HTML as WeasyHTML

                pdf_path = output_dir / f"{stem}.pdf"
                pdf_path.parent.mkdir(parents=True, exist_ok=True)
                print(f"    Converting {primary} to PDF...")
                WeasyHTML(
                    url=primary_url,
                    url_fetcher=self._make_fetcher(),
                ).write_pdf(str(pdf_path))
                return pdf_path
            except ImportError:
                print("    [weasyprint not installed — saving as HTML]")
            except Exception as e:
                print(f"    [PDF conversion failed: {e} — saving as HTML]")

        # Download raw HTML
        out = output_dir / f"{stem}.htm"
        print(f"    Downloading: {primary}")
        self._download(primary_url, out)
        return out

    def _make_fetcher(self):
        """Return a weasyprint-compatible URL fetcher that sends the SEC User-Agent."""
        session = self.session

        def fetcher(url, timeout=10, ssl_context=None):
            if url.startswith(("http://", "https://")):
                time.sleep(0.1)
                try:
                    resp = session.get(url, timeout=timeout)
                    resp.raise_for_status()
                    result = {
                        "string": resp.content,
                        "redirected_url": resp.url,
                    }
                    content_type = resp.headers.get("Content-Type")
                    if content_type:
                        # weasyprint expects just the mime type, not the full header
                        result["mime_type"] = content_type.split(";")[0].strip()
                    if resp.encoding:
                        result["encoding"] = resp.encoding
                    return result
                except Exception:
                    return {"string": b"", "mime_type": "text/plain"}
            from weasyprint import default_url_fetcher

            return default_url_fetcher(url, timeout=timeout, ssl_context=ssl_context)

        return fetcher


# -- CLI -----------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Download 10-K annual reports from SEC EDGAR",
    )
    parser.add_argument(
        "--tickers", nargs="+", required=True,
        help="Stock ticker symbols (e.g. AAPL MSFT GOOG)",
    )
    parser.add_argument(
        "--years", nargs="+", type=int, required=True,
        help="Fiscal years to download (e.g. 2022 2023)",
    )
    parser.add_argument(
        "--output", required=True,
        help="Root output directory (subfolders created per ticker)",
    )
    parser.add_argument(
        "--format", choices=["pdf", "html"], default="html",
        help="Output file type: html (default) or pdf",
    )
    parser.add_argument(
        "--user-agent",
        default="AnnualReportDownloader admin@example.com",
        help="User-Agent sent to SEC (must include a name and email)",
    )
    args = parser.parse_args()

    client = EdgarClient(args.user_agent)
    output = Path(args.output)
    years = set(args.years)
    convert = args.format == "pdf"

    for ticker in args.tickers:
        ticker = ticker.upper()
        print(f"\n{'=' * 50}")
        print(f"  {ticker}")
        print(f"{'=' * 50}")

        cik = client.get_cik(ticker)
        if not cik:
            print(f"  ERROR: Unknown ticker '{ticker}'")
            continue
        print(f"  CIK: {cik}")

        filings = client.get_10k_filings(cik, years)
        if not filings:
            print(f"  No 10-K filings found for {sorted(years)}")
            continue

        print(f"  Found {len(filings)} filing(s)")
        ticker_dir = output / ticker

        for filing in filings:
            print(
                f"\n  Period ending: {filing['reportDate']}"
                f"  (filed {filing['filingDate']})"
            )
            try:
                path = client.download_10k(
                    cik, filing, ticker_dir, ticker, convert,
                )
                print(f"    Saved: {path}")
            except Exception as e:
                print(f"    ERROR: {e}")

    print(f"\nDone. Reports saved to: {output.resolve()}")


if __name__ == "__main__":
    main()
