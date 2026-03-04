"""SEC EDGAR API client for downloading 10-K annual reports."""

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
        self._user_agent = user_agent
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": user_agent,
            "Accept-Encoding": "gzip, deflate",
        })
        self._cik_map = None
        self._playwright = None
        self._browser = None

    def _get_browser(self):
        """Lazy-launch headless Chromium, reuse for batch downloads."""
        if self._browser is None:
            from playwright.sync_api import sync_playwright

            self._playwright = sync_playwright().start()
            self._browser = self._playwright.chromium.launch()
        return self._browser

    def close(self):
        """Shut down the browser and Playwright process."""
        if self._browser is not None:
            self._browser.close()
            self._browser = None
        if self._playwright is not None:
            self._playwright.stop()
            self._playwright = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def _download_text(self, url):
        """Download a URL and return the response text."""
        time.sleep(REQUEST_DELAY)
        resp = self.session.get(url)
        resp.raise_for_status()
        return resp.text

    def _route_handler(self, route):
        """Intercept browser requests and proxy through our rate-limited session."""
        try:
            time.sleep(REQUEST_DELAY)
            resp = self.session.get(route.request.url, timeout=10)
            content_type = resp.headers.get("Content-Type", "application/octet-stream")
            route.fulfill(
                status=resp.status_code,
                headers={"Content-Type": content_type},
                body=resp.content,
            )
        except Exception:
            route.abort()

    def _setup_page(self, browser, html, base_url, pdf_path):
        """Load HTML into a page with route interception and render to PDF."""
        # Inject <base> tag so relative URLs resolve to the SEC filing directory
        if "<base " not in html.lower():
            html = html.replace("<head>", f'<head><base href="{base_url}">', 1)
            if "<head>" not in html.lower():
                html = f'<base href="{base_url}">' + html

        page = browser.new_page()
        page.route("**/*", self._route_handler)
        try:
            page.set_content(html, wait_until="networkidle", timeout=120000)
            page.emulate_media(media="screen")
            page.pdf(
                path=str(pdf_path),
                print_background=True,
                margin={"top": "0.4in", "bottom": "0.4in", "left": "0.5in", "right": "0.5in"},
            )
        finally:
            page.close()

    def _render_html_to_pdf(self, html, base_url, pdf_path):
        """Render HTML string to PDF using Playwright. Handles async contexts."""
        try:
            import asyncio
            asyncio.get_running_loop()
        except RuntimeError:
            # No async loop — use reusable browser (CLI path)
            self._setup_page(self._get_browser(), html, base_url, pdf_path)
            return

        # Inside async loop (e.g. Streamlit) — run in a thread
        from concurrent.futures import ThreadPoolExecutor
        from playwright.sync_api import sync_playwright

        def _run():
            with sync_playwright() as p:
                browser = p.chromium.launch()
                try:
                    self._setup_page(browser, html, base_url, pdf_path)
                finally:
                    browser.close()

        with ThreadPoolExecutor(max_workers=1) as pool:
            pool.submit(_run).result()

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
        """Download a single 10-K.  Prefers native PDF; falls back to HTML->PDF."""
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

            # 2) No native PDF — download HTML and convert to PDF locally
            try:
                pdf_path = output_dir / f"{stem}.pdf"
                pdf_path.parent.mkdir(parents=True, exist_ok=True)
                print(f"    Converting {primary} to PDF...")
                html = self._download_text(primary_url)
                self._render_html_to_pdf(html, f"{base_url}/", pdf_path)
                return pdf_path
            except ImportError:
                print("    [playwright not installed — saving as HTML]")
            except Exception as e:
                print(f"    [PDF conversion failed: {e} — saving as HTML]")
                self._browser = None

        # Download raw HTML, inject <base> so images resolve when opened locally
        out = output_dir / f"{stem}.htm"
        print(f"    Downloading: {primary}")
        html = self._download_text(primary_url)
        base_tag = f'<base href="{base_url}/">'
        if "<base " not in html.lower():
            html = html.replace("<head>", f"<head>{base_tag}", 1)
            if "<head>" not in html.lower():
                html = base_tag + html
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(html, encoding="utf-8")
        return out

