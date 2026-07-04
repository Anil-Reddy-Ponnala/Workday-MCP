"""
Thin client for pulling data out of Workday Custom Reports exposed as
RAAS (Report-as-a-Service) web services, authenticated via OAuth 2.0
(client credentials, backed by an Integration System User / ISU).

Two modes:
  - MOCK_MODE=true  -> reads JSON fixtures from mock_data/ so you can
                        build and test the whole server before you've
                        wired up a real Workday tenant.
  - MOCK_MODE=false -> calls the real Workday RAAS endpoints.

Each "report" is just a name -> URL mapping declared in config/reports.yaml.
Add a new report there and it is immediately fetchable by name; nothing
in this file needs to change.
"""

import os
import json
import time
import logging
from pathlib import Path
from typing import Any

import httpx
import yaml
from cachetools import TTLCache

logger = logging.getLogger("workday_client")

ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "config"
MOCK_DIR = ROOT / "mock_data"


def _env_bool(name: str, default: bool = False) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return val.strip().lower() in {"1", "true", "yes", "y"}


class WorkdayClient:
    def __init__(self):
        self.mock_mode = _env_bool("MOCK_MODE", True)
        self.base_url = os.getenv("WORKDAY_BASE_URL", "")
        self.token_url = os.getenv("WORKDAY_TOKEN_URL", "")
        self.client_id = os.getenv("WORKDAY_CLIENT_ID", "")
        self.client_secret = os.getenv("WORKDAY_CLIENT_SECRET", "")
        self.refresh_token = os.getenv("WORKDAY_REFRESH_TOKEN", "")

        ttl = int(os.getenv("REPORT_CACHE_TTL_SECONDS", "300"))
        self._report_cache: TTLCache = TTLCache(maxsize=64, ttl=ttl)

        self._access_token: str | None = None
        self._token_expiry: float = 0.0

        self.reports = self._load_reports_config()

    # ------------------------------------------------------------------
    # Config
    # ------------------------------------------------------------------
    def _load_reports_config(self) -> dict[str, Any]:
        path = CONFIG_DIR / "reports.yaml"
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return {r["id"]: r for r in data.get("reports", [])}

    def reload_reports_config(self):
        """Call this to pick up config/reports.yaml edits without restarting,
        if you build a hot-reload path later. Currently used at startup."""
        self.reports = self._load_reports_config()

    # ------------------------------------------------------------------
    # OAuth 2.0 (client credentials / refresh-token grant against Workday)
    # ------------------------------------------------------------------
    def _get_access_token(self) -> str:
        if self._access_token and time.time() < self._token_expiry - 30:
            return self._access_token

        if not self.token_url or not self.client_id or not self.client_secret:
            raise RuntimeError(
                "Workday OAuth is not configured. Set WORKDAY_TOKEN_URL, "
                "WORKDAY_CLIENT_ID and WORKDAY_CLIENT_SECRET (and "
                "WORKDAY_REFRESH_TOKEN if your ISU integration uses the "
                "refresh-token grant, which is Workday's typical pattern)."
            )

        data = {"grant_type": "refresh_token", "refresh_token": self.refresh_token}
        if not self.refresh_token:
            data = {"grant_type": "client_credentials"}

        resp = httpx.post(
            self.token_url,
            data=data,
            auth=(self.client_id, self.client_secret),
            timeout=30,
        )
        resp.raise_for_status()
        payload = resp.json()
        self._access_token = payload["access_token"]
        # Workday tokens are typically short-lived; default to 15 min if
        # expires_in isn't returned.
        self._token_expiry = time.time() + int(payload.get("expires_in", 900))
        return self._access_token

    # ------------------------------------------------------------------
    # Report fetching
    # ------------------------------------------------------------------
    def get_report_rows(self, report_id: str, force_refresh: bool = False) -> list[dict]:
        """Return the report's rows as a list of flat dicts, e.g.:
        [{"Worker": "Jane Doe", "Active_Status": "Active", "Hire_Date": "2021-03-01", ...}, ...]
        """
        if report_id not in self.reports:
            known = ", ".join(sorted(self.reports))
            raise ValueError(f"Unknown report_id '{report_id}'. Known reports: {known}")

        cache_key = report_id
        if not force_refresh and cache_key in self._report_cache:
            return self._report_cache[cache_key]

        if self.mock_mode:
            rows = self._get_mock_rows(report_id)
        else:
            rows = self._get_live_rows(report_id)

        self._report_cache[cache_key] = rows
        return rows

    def _get_mock_rows(self, report_id: str) -> list[dict]:
        report_cfg = self.reports[report_id]
        fixture = report_cfg.get("mock_file")
        if not fixture:
            raise RuntimeError(
                f"Report '{report_id}' has no mock_file configured in "
                f"config/reports.yaml, and MOCK_MODE is on."
            )
        path = MOCK_DIR / fixture
        with open(path, "r", encoding="utf-8") as f:
            payload = json.load(f)
        # Workday RAAS JSON wraps rows in {"Report_Entry": [...]}
        return payload.get("Report_Entry", payload)

    def _get_live_rows(self, report_id: str) -> list[dict]:
        report_cfg = self.reports[report_id]
        rel_url = report_cfg["url"]  # e.g. "/service/customreport2/tenant/ISU/Current_Headcount_RAAS"
        url = rel_url if rel_url.startswith("http") else f"{self.base_url}{rel_url}"

        token = self._get_access_token()
        params = {"format": "json"}
        resp = httpx.get(
            url,
            params=params,
            headers={"Authorization": f"Bearer {token}"},
            timeout=60,
        )
        resp.raise_for_status()
        payload = resp.json()
        return payload.get("Report_Entry", [])
