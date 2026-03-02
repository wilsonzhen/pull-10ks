import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from pull_10ks import EdgarClient


@pytest.fixture
def client():
    c = EdgarClient("Test admin@test.com")
    # Zero out delays so tests run fast
    c._get_json = MagicMock(wraps=c._get_json)
    c._download = MagicMock()
    return c


# -- _collect_10ks (pure logic, no mocking needed) ----------------------------

class TestCollect10Ks:
    def test_filters_by_form_and_year(self):
        records = {
            "form": ["10-K", "10-Q", "10-K", "8-K"],
            "accessionNumber": ["001", "002", "003", "004"],
            "filingDate": ["2023-11-01", "2023-08-01", "2022-10-28", "2023-05-01"],
            "reportDate": ["2023-09-30", "2023-06-30", "2022-09-24", "2023-04-15"],
            "primaryDocument": ["a.htm", "b.htm", "c.htm", "d.htm"],
        }
        out = []
        EdgarClient("test")._collect_10ks(records, {2023}, out)
        assert len(out) == 1
        assert out[0]["accessionNumber"] == "001"
        assert out[0]["reportDate"] == "2023-09-30"

    def test_multiple_years(self):
        records = {
            "form": ["10-K", "10-K", "10-K"],
            "accessionNumber": ["001", "002", "003"],
            "filingDate": ["2023-11-01", "2022-10-28", "2021-10-29"],
            "reportDate": ["2023-09-30", "2022-09-24", "2021-09-25"],
            "primaryDocument": ["a.htm", "b.htm", "c.htm"],
        }
        out = []
        EdgarClient("test")._collect_10ks(records, {2021, 2023}, out)
        assert len(out) == 2
        assert out[0]["reportDate"] == "2023-09-30"
        assert out[1]["reportDate"] == "2021-09-25"

    def test_falls_back_to_filing_date_when_report_date_missing(self):
        records = {
            "form": ["10-K"],
            "accessionNumber": ["001"],
            "filingDate": ["2023-11-01"],
            "reportDate": [""],
            "primaryDocument": ["a.htm"],
        }
        out = []
        EdgarClient("test")._collect_10ks(records, {2023}, out)
        assert len(out) == 1
        assert out[0]["reportDate"] == "2023-11-01"

    def test_skips_when_no_dates_available(self):
        records = {
            "form": ["10-K"],
            "accessionNumber": ["001"],
            "filingDate": [],
            "reportDate": [],
            "primaryDocument": ["a.htm"],
        }
        out = []
        EdgarClient("test")._collect_10ks(records, {2023}, out)
        assert len(out) == 0

    def test_ignores_10k_amendments(self):
        records = {
            "form": ["10-K/A", "10-K"],
            "accessionNumber": ["001", "002"],
            "filingDate": ["2023-12-01", "2023-11-01"],
            "reportDate": ["2023-09-30", "2023-09-30"],
            "primaryDocument": ["a.htm", "b.htm"],
        }
        out = []
        EdgarClient("test")._collect_10ks(records, {2023}, out)
        assert len(out) == 1
        assert out[0]["accessionNumber"] == "002"

    def test_empty_records(self):
        out = []
        EdgarClient("test")._collect_10ks({}, {2023}, out)
        assert len(out) == 0


# -- get_cik -------------------------------------------------------------------

class TestGetCik:
    def test_returns_cik_for_known_ticker(self, client):
        client._get_json.return_value = {
            "0": {"cik_str": "320193", "ticker": "AAPL", "title": "Apple Inc"},
            "1": {"cik_str": "789019", "ticker": "MSFT", "title": "Microsoft Corp"},
        }
        assert client.get_cik("AAPL") == "320193"
        assert client.get_cik("msft") == "789019"

    def test_returns_none_for_unknown_ticker(self, client):
        client._get_json.return_value = {
            "0": {"cik_str": "320193", "ticker": "AAPL", "title": "Apple Inc"},
        }
        assert client.get_cik("ZZZZ") is None

    def test_caches_ticker_map(self, client):
        client._get_json.return_value = {
            "0": {"cik_str": "320193", "ticker": "AAPL", "title": "Apple Inc"},
        }
        client.get_cik("AAPL")
        client.get_cik("AAPL")
        client._get_json.assert_called_once()


# -- get_10k_filings -----------------------------------------------------------

class TestGet10kFilings:
    def test_fetches_and_filters_recent_filings(self, client):
        client._get_json.return_value = {
            "filings": {
                "recent": {
                    "form": ["10-K", "10-Q"],
                    "accessionNumber": ["001", "002"],
                    "filingDate": ["2023-11-01", "2023-08-01"],
                    "reportDate": ["2023-09-30", "2023-06-30"],
                    "primaryDocument": ["a.htm", "b.htm"],
                },
                "files": [],
            }
        }
        results = client.get_10k_filings("320193", {2023})
        assert len(results) == 1
        assert results[0]["accessionNumber"] == "001"

    def test_includes_paginated_older_filings(self, client):
        client._get_json.side_effect = [
            {
                "filings": {
                    "recent": {
                        "form": ["10-K"],
                        "accessionNumber": ["001"],
                        "filingDate": ["2023-11-01"],
                        "reportDate": ["2023-09-30"],
                        "primaryDocument": ["a.htm"],
                    },
                    "files": [{"name": "CIK-submissions-001.json"}],
                }
            },
            {
                "form": ["10-K"],
                "accessionNumber": ["002"],
                "filingDate": ["2020-10-30"],
                "reportDate": ["2020-09-26"],
                "primaryDocument": ["b.htm"],
            },
        ]
        results = client.get_10k_filings("320193", {2020, 2023})
        assert len(results) == 2


# -- download_10k --------------------------------------------------------------

class TestDownload10k:
    FILING = {
        "accessionNumber": "0000320193-23-000077",
        "filingDate": "2023-11-03",
        "reportDate": "2023-09-30",
        "primaryDocument": "aapl-20230930.htm",
    }

    def test_downloads_native_pdf_when_available(self, client, tmp_path):
        client._get_json.return_value = {
            "directory": {
                "item": [
                    {"name": "aapl-20230930.htm"},
                    {"name": "aapl-20230930.pdf"},
                ]
            }
        }
        result = client.download_10k("320193", self.FILING, tmp_path, "AAPL", convert=True)
        assert result.suffix == ".pdf"
        assert "AAPL_10K_2023-09-30" in result.name
        client._download.assert_called_once()

    def test_downloads_html_when_convert_false(self, client, tmp_path):
        result = client.download_10k("320193", self.FILING, tmp_path, "AAPL", convert=False)
        assert result.suffix == ".htm"
        assert "AAPL_10K_2023-09-30" in result.name
        # Should NOT check the filing index at all
        client._get_json.assert_not_called()

    def test_falls_back_to_html_when_no_pdf_and_weasyprint_missing(self, client, tmp_path):
        client._get_json.return_value = {
            "directory": {"item": [{"name": "aapl-20230930.htm"}]}
        }
        with patch.dict("sys.modules", {"weasyprint": None}):
            result = client.download_10k("320193", self.FILING, tmp_path, "AAPL", convert=True)
        assert result.suffix == ".htm"


# -- _make_fetcher -------------------------------------------------------------

class TestMakeFetcher:
    def test_strips_content_type_params(self, client):
        mock_resp = MagicMock()
        mock_resp.content = b"<html></html>"
        mock_resp.url = "https://example.com"
        mock_resp.headers = {"Content-Type": "text/html; charset=utf-8"}
        mock_resp.encoding = "utf-8"
        mock_resp.raise_for_status = MagicMock()
        client.session.get = MagicMock(return_value=mock_resp)

        fetcher = client._make_fetcher()
        result = fetcher("https://example.com/test.htm")
        assert result["mime_type"] == "text/html"

    def test_handles_missing_content_type(self, client):
        mock_resp = MagicMock()
        mock_resp.content = b"data"
        mock_resp.url = "https://example.com"
        mock_resp.headers = {}
        mock_resp.encoding = None
        mock_resp.raise_for_status = MagicMock()
        client.session.get = MagicMock(return_value=mock_resp)

        fetcher = client._make_fetcher()
        result = fetcher("https://example.com/file")
        assert "mime_type" not in result
        assert "encoding" not in result

    def test_returns_empty_on_http_error(self, client):
        client.session.get = MagicMock(side_effect=Exception("connection error"))

        fetcher = client._make_fetcher()
        result = fetcher("https://example.com/broken")
        assert result["string"] == b""
        assert result["mime_type"] == "text/plain"
