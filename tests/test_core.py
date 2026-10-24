import json
from urllib.parse import urlsplit

import pytest

from examples.fixture_server import PAYLOAD, running_server
from rangewitness import core
from rangewitness.cli import main
from rangewitness.core import (
    InputError,
    ProbeError,
    Response,
    audit,
    parse_content_range,
    validate_url,
)


@pytest.fixture(scope="module")
def server():
    with running_server() as base:
        yield base


def test_real_server_reference_flow(server, tmp_path):
    reference = tmp_path / "asset.bin"
    reference.write_bytes(PAYLOAD)
    before = reference.read_bytes()
    report = audit(server + "/ok?token=synthetic-private-value", reference=reference)
    assert report["status"] == "passed"
    assert report["requests"] == 7
    assert report["bytes_read"] == 5 * 64
    assert all(c["status"] == "passed" for c in report["checks"])
    assert reference.read_bytes() == before
    output = json.dumps(report)
    assert "synthetic-private-value" not in output
    assert "fixture-v1" not in output
    assert str(reference) not in output


@pytest.mark.parametrize(
    ("route", "error"),
    [
        ("ignored", "range_ignored_200"),
        ("bad-range", "invalid_content_range"),
        ("wrong-range", "wrong_content_range"),
        ("short", "wrong_body_length"),
        ("oversized", "wrong_body_length"),
        ("encoded", "unexpected_content_encoding"),
        ("duplicate", "duplicate_response_header"),
        ("corrupt", "overlapping_bytes_differ"),
        ("changing", "representation_etag_changed"),
        ("bad-416", "expected_416"),
        ("bad-if-range", "if_range_miss_expected_200"),
        ("redirect", "expected_206"),
    ],
)
def test_real_faults_are_detected(server, route, error):
    report = audit(server + "/" + route)
    assert report["status"] == "failed"
    assert error in [error for check in report["checks"] for error in check.get("errors", [])]
    assert report["bytes_read"] <= report["requests"] * 65


@pytest.mark.parametrize("route", ["tiny", "weak", "no-etag"])
def test_small_and_unvalidated_assets(server, route):
    report = audit(server + "/" + route)
    assert report["status"] == "passed"
    if route != "tiny":
        assert report["requests"] == 5
        assert report["checks"][-1]["status"] == "skipped"


def test_reference_mismatch_and_size(server, tmp_path):
    path = tmp_path / "reference"
    path.write_bytes(b"!" * len(PAYLOAD))
    report = audit(server + "/ok", reference=path)
    assert report["checks"][0]["errors"] == ["reference_bytes_differ"]
    path.write_bytes(b"small")
    report = audit(server + "/ok", reference=path)
    assert report["checks"][0]["errors"] == ["reference_size_differs"]


@pytest.mark.parametrize("value", [0, -1, 4097, True, 1.5])
def test_sample_limits(value):
    with pytest.raises(InputError):
        audit("http://example.invalid", sample_bytes=value)


@pytest.mark.parametrize("value", [0, -1, 61, float("nan"), float("inf"), True])
def test_timeout_limits(value):
    with pytest.raises(InputError):
        audit("http://example.invalid", timeout=value)


@pytest.mark.parametrize(
    "url",
    [
        "",
        "ftp://example.invalid",
        "http://u:p@example.invalid",
        "http://x/#f",
        "http://x/#",
        "http://x:0",
        "http://x:99999",
        "http://[bad",
        "http://x/a\nX",
        "http://x/a b",
        "http://x/中文",
        "http://x/\x7f",
        "http://x\\y",
        "http://" + "a" * 8200,
    ],
)
def test_invalid_urls(url):
    with pytest.raises(InputError):
        validate_url(url)


def test_valid_encoded_url():
    assert validate_url("https://example.invalid/%E4%B8%AD?q=%20").hostname == "example.invalid"


@pytest.mark.parametrize(
    "value",
    [
        "",
        "items 0-1/2",
        "bytes 2-1/3",
        "bytes 0-3/3",
        "bytes 0-1/*",
        "bytes 0-0/0",
        "bytes 0-0/9999999999999999999",
    ],
)
def test_invalid_ranges(value):
    with pytest.raises(ProbeError):
        parse_content_range(value)


def test_valid_range():
    assert parse_content_range(" bytes 0-1/2 ") == (0, 1, 2)


def test_bad_reference(tmp_path):
    empty = tmp_path / "empty"
    empty.touch()
    for path in (empty, tmp_path, tmp_path / "missing"):
        with pytest.raises(InputError):
            audit("http://example.invalid", reference=path)


def test_transport_exception_is_redacted(monkeypatch):
    def explode(*args, **kwargs):
        raise OSError("synthetic-secret")

    monkeypatch.setattr(core.http.client.HTTPConnection, "request", explode)
    result = audit("http://example.invalid")
    assert result["status"] == "failed"
    assert result["checks"][0]["errors"] == ["transport_error_OSError"]
    assert "synthetic-secret" not in json.dumps(result)


def test_more_header_defects(monkeypatch):
    responses = iter(
        [
            Response(206, {"content-range": "bytes 0-1/2", "content-length": "2"}, b"ab"),
            Response(206, {"content-range": "bad", "content-length": "abc"}, b"b"),
            Response(206, {"content-range": "bytes 0-1/2"}, b"ab"),
            Response(206, {"content-range": "bytes 0-1/2"}, b"XY"),
            Response(416, {}, b""),
        ]
    )
    monkeypatch.setattr(core, "exchange", lambda *a, **k: next(responses))
    report = audit("http://example.invalid", sample_bytes=2)
    errors = [e for c in report["checks"] for e in c.get("errors", [])]
    assert "invalid_content_range" in errors
    assert "wrong_content_length" in errors
    assert "suffix_open_ended_bytes_differ" in errors
    assert "wrong_unsatisfied_content_range" in errors


def test_later_transport_errors_continue(monkeypatch):
    calls = 0

    def exchange(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            return Response(206, {"content-range": "bytes 0-0/1", "etag": '"x"'}, b"a")
        raise ProbeError("injected_failure")

    monkeypatch.setattr(core, "exchange", exchange)
    report = audit("http://example.invalid", sample_bytes=1)
    assert report["requests"] == 7
    assert report["status"] == "failed"


@pytest.mark.parametrize("kind", ["long", "ambiguous", "https"])
def test_transport_header_bounds_and_tls(monkeypatch, kind):
    from email.message import Message

    class FakeResponse:
        status = 206
        headers = Message()
        if kind == "long":
            headers["ETag"] = "x" * 4097
        elif kind == "ambiguous":
            headers["Transfer-Encoding"] = "chunked"
            headers["Content-Length"] = "1"

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def read(self, limit):
            return b"x"

    class FakeConnection:
        def __init__(self, *args, **kwargs):
            if kind == "https":
                assert kwargs["context"].verify_mode == core.ssl.CERT_REQUIRED

        def request(self, *args, **kwargs):
            pass

        def getresponse(self):
            return FakeResponse()

        def close(self):
            pass

    monkeypatch.setattr(core.http.client, "HTTPSConnection", FakeConnection)
    if kind == "https":
        assert (
            core.exchange(urlsplit("https://x"), "bytes=0-0", read_limit=1, timeout=1).body == b"x"
        )
    else:
        with pytest.raises(ProbeError):
            core.exchange(urlsplit("https://x"), "bytes=0-0", read_limit=1, timeout=1)


def test_cli_success_failure_input_and_privacy(server, capsys, tmp_path):
    assert main([server + "/ok", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "passed"
    assert main([server + "/corrupt"]) == 1
    assert "FAILED" in capsys.readouterr().out
    assert main(["ftp://secret.invalid/private"]) == 2
    assert "secret.invalid" not in capsys.readouterr().err
    assert main([server, "--reference", str(tmp_path / "missing")]) == 2
    assert "Input error" in capsys.readouterr().err


def test_cli_file_failure_is_generic(monkeypatch, capsys):
    import rangewitness.cli as cli

    def fail(*args, **kwargs):
        raise OSError("private path")

    monkeypatch.setattr(cli, "audit", fail)
    assert main(["http://example.invalid", "--reference", "hidden"]) == 2
    assert "private path" not in capsys.readouterr().err
