import pytest
import requests

from company_news import http


class FakeResponse:
    def __init__(self, status_code, payload=None):
        self.status_code = status_code
        self.ok = status_code < 400
        self.text = ""
        self._payload = payload if payload is not None else {"results": []}

    def json(self):
        return self._payload


@pytest.fixture(autouse=True)
def no_backoff(monkeypatch):
    monkeypatch.setattr(http.time, "sleep", lambda seconds: None)


def test_audit_fields_describe_the_last_attempt_not_a_stale_one(monkeypatch):
    # Attempt 1 fails with 503 + body, attempt 2 dies with a connection error:
    # the final audit must not report attempt 1's status or payload.
    responses = [FakeResponse(503, {"error": "overloaded"}), requests.ConnectionError("reset by peer")]
    def fake_request(*args, **kwargs):
        item = responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item
    monkeypatch.setattr(http.requests, "request", fake_request)

    audit = http.request_json("GET", "https://search.example", headers={}, max_attempts=2)

    assert not audit.ok
    assert audit.status_code is None
    assert audit.response is None
    assert audit.error == "ConnectionError: reset by peer"
    assert [attempt.number for attempt in audit.attempts] == [1, 2]
    assert audit.attempts[0].status_code == 503
    assert audit.attempts[1].status_code is None


def test_audit_fields_describe_the_last_attempt_after_recovery(monkeypatch):
    responses = [FakeResponse(503), FakeResponse(200)]
    monkeypatch.setattr(http.requests, "request", lambda *args, **kwargs: responses.pop(0))

    audit = http.request_json("GET", "https://search.example", headers={})

    assert audit.ok
    assert audit.status_code == 200
    assert audit.response == {"results": []}
    assert audit.error == ""
    assert [attempt.status_code for attempt in audit.attempts] == [503, 200]
