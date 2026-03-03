"""pull_10ks — download 10-K annual reports from SEC EDGAR."""

from .client import (
    ARCHIVES_BASE,
    COMPANY_TICKERS_URL,
    EdgarClient,
    REQUEST_DELAY,
    SUBMISSIONS_BASE,
)

__all__ = [
    "EdgarClient",
    "COMPANY_TICKERS_URL",
    "SUBMISSIONS_BASE",
    "ARCHIVES_BASE",
    "REQUEST_DELAY",
]
