"""Network-free tests for source clients and preflight health checks."""

from types import SimpleNamespace

import pandas as pd
import pytest

from saat.panel import HDXCKANClient, HAPIClient
from saat.sources import ICPACClient, SourceHealthChecker


class FakeResponse:
    def __init__(self, payload=None, status_code=200, content=b""):
        self._payload = payload
        self.status_code = status_code
        self.ok = status_code < 400
        self.reason = "OK" if self.ok else "Bad Request"
        self.content = content

    def raise_for_status(self):
        if not self.ok:
            raise RuntimeError(self.reason)

    def json(self):
        return self._payload


def test_ckan_fetches_dataset_and_resource(monkeypatch):
    calls = []

    def fake_get(url, **kwargs):
        calls.append((url, kwargs))
        if url.endswith("package_show"):
            return FakeResponse({"success": True, "result": {"resources": [{"id": "csv-url"}]}})
        return FakeResponse(content=b"date,flow\n2026-01-01,10\n")

    monkeypatch.setattr("saat.panel.requests.get", fake_get)
    client = HDXCKANClient()
    assert client.list_resources("demo")[0]["id"] == "csv-url"
    frame = client.fetch_resource("csv-url")
    assert frame.loc[0, "flow"] == 10
    assert calls[0][1]["params"] == {"id": "demo"}


def test_hapi_paginates_until_short_page(monkeypatch):
    calls = []

    def fake_get(url, **kwargs):
        calls.append(kwargs["params"]["offset"])
        offset = kwargs["params"]["offset"]
        rows = [{"id": offset + index} for index in range(2 if offset == 0 else 1)]
        return FakeResponse({"data": rows})

    monkeypatch.setattr("saat.panel.requests.get", fake_get)
    frame = HAPIClient(app_identifier="test-app").paginate_idp_statistics("idp", page_size=2)
    assert frame["id"].tolist() == [0, 1, 2]
    assert calls == [0, 2]


def test_hapi_rejects_page_larger_than_api_cap():
    with pytest.raises(ValueError, match="10000"):
        HAPIClient().paginate_idp_statistics("idp", page_size=10001)


def test_hapi_requires_real_app_identifier():
    with pytest.raises(ValueError, match="HAPI_APP_IDENTIFIER"):
        HAPIClient().fetch_idp_statistics("idp", limit=1)


def test_hapi_identifier_uses_documented_base64_format():
    identifier = HAPIClient.make_app_identifier("SAAT tests", "test@example.org")
    assert identifier == "U0FBVCB0ZXN0czp0ZXN0QGV4YW1wbGUub3Jn"


def test_icpac_extracts_and_validates_tercile_probability():
    assert ICPACClient.extract_tercile_probability({"above_probability": 0.6}) == pytest.approx(0.6)
    with pytest.raises(ValueError, match="below, normal, or above"):
        ICPACClient.extract_tercile_probability({"above": 0.6}, "invalid")


def test_source_health_preserves_proxy_or_network_error(monkeypatch):
    def fake_get(url, timeout):
        raise ConnectionError("proxy denied")

    monkeypatch.setattr("saat.sources.requests.get", fake_get)
    result = SourceHealthChecker.check_all_sources(timeout=1)
    assert len(result) == len(SourceHealthChecker.SOURCES)
    assert all(not status["is_reachable"] for status in result.values())
    assert all("proxy denied" in status["error_message"] for status in result.values())


def test_source_health_distinguishes_http_error_from_unreachable_host(monkeypatch):
    monkeypatch.setattr("saat.sources.requests.get", lambda url, timeout: FakeResponse(status_code=403))
    result = SourceHealthChecker.check_all_sources(timeout=1)
    assert all(status["is_reachable"] for status in result.values())
    assert all(not status["http_ok"] for status in result.values())
