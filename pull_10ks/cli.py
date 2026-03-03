#!/usr/bin/env python
"""CLI entry point for downloading 10-K annual reports from SEC EDGAR.

Usage:
    python -m pull_10ks.cli --tickers AAPL MSFT --years 2022 2023 --output ./reports
    pull-10ks --tickers AAPL MSFT --years 2022 2023 --output ./reports
"""

import argparse
from pathlib import Path

from .client import EdgarClient


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
        help="Output directory for downloaded reports",
    )
    parser.add_argument(
        "--group-by-ticker", action="store_true",
        help="Create a subfolder per ticker inside the output directory",
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

    output = Path(args.output)
    years = set(args.years)
    convert = args.format == "pdf"

    with EdgarClient(args.user_agent) as client:
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
            ticker_dir = output / ticker if args.group_by_ticker else output

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
