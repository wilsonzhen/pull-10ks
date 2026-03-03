from pathlib import Path
from unittest.mock import patch, MagicMock, call

from pull_10ks.cli import main


FILING = {
    "accessionNumber": "0000320193-23-000077",
    "filingDate": "2023-11-03",
    "reportDate": "2023-09-30",
    "primaryDocument": "aapl-20230930.htm",
}


def _mock_client():
    """Return a mock EdgarClient that resolves one ticker with one filing."""
    client = MagicMock()
    client.get_cik.return_value = "320193"
    client.get_10k_filings.return_value = [FILING]
    client.download_10k.return_value = Path("/tmp/AAPL_10K_2023-09-30.htm")
    return client


class TestGroupByTicker:
    @patch("pull_10ks.cli.EdgarClient")
    def test_default_downloads_to_flat_output_dir(self, MockClient, tmp_path):
        MockClient.return_value = _mock_client()
        with patch(
            "sys.argv",
            ["pull-10ks", "--tickers", "AAPL", "--years", "2023", "--output", str(tmp_path)],
        ):
            main()

        _, kwargs = MockClient.return_value.download_10k.call_args
        # output_dir (3rd positional arg) should be the output dir itself
        output_dir = MockClient.return_value.download_10k.call_args[0][2]
        assert output_dir == tmp_path

    @patch("pull_10ks.cli.EdgarClient")
    def test_group_by_ticker_downloads_to_ticker_subdir(self, MockClient, tmp_path):
        MockClient.return_value = _mock_client()
        with patch(
            "sys.argv",
            ["pull-10ks", "--tickers", "AAPL", "--years", "2023",
             "--output", str(tmp_path), "--group-by-ticker"],
        ):
            main()

        output_dir = MockClient.return_value.download_10k.call_args[0][2]
        assert output_dir == tmp_path / "AAPL"

    @patch("pull_10ks.cli.EdgarClient")
    def test_group_by_ticker_multiple_tickers(self, MockClient, tmp_path):
        client = MagicMock()
        client.get_cik.side_effect = ["320193", "789019"]
        client.get_10k_filings.return_value = [FILING]
        client.download_10k.return_value = Path("/tmp/report.htm")
        MockClient.return_value = client

        with patch(
            "sys.argv",
            ["pull-10ks", "--tickers", "AAPL", "MSFT", "--years", "2023",
             "--output", str(tmp_path), "--group-by-ticker"],
        ):
            main()

        dirs = [c[0][2] for c in client.download_10k.call_args_list]
        assert dirs == [tmp_path / "AAPL", tmp_path / "MSFT"]

    @patch("pull_10ks.cli.EdgarClient")
    def test_flat_mode_multiple_tickers_same_dir(self, MockClient, tmp_path):
        client = MagicMock()
        client.get_cik.side_effect = ["320193", "789019"]
        client.get_10k_filings.return_value = [FILING]
        client.download_10k.return_value = Path("/tmp/report.htm")
        MockClient.return_value = client

        with patch(
            "sys.argv",
            ["pull-10ks", "--tickers", "AAPL", "MSFT", "--years", "2023",
             "--output", str(tmp_path)],
        ):
            main()

        dirs = [c[0][2] for c in client.download_10k.call_args_list]
        assert dirs == [tmp_path, tmp_path]
