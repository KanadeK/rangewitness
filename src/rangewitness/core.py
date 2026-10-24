"""Small, bounded probes of a single stable HTTP representation."""

from __future__ import annotations

import hashlib
import http.client
import math
import re
import ssl
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import SplitResult, urlsplit

from . import __version__

MAX_SIZE = 2**63 - 1
CONTENT_RANGE = re.compile(r"bytes ([0-9]{1,19})-([0-9]{1,19})/([0-9]{1,19})", re.I)
UNSATISFIED = re.compile(r"bytes \*/([0-9]{1,19})", re.I)
STRONG_ETAG = re.compile(r'"[\x21\x23-\x7e\x80-\xff]*"')


class InputError(ValueError):
    """The requested experiment cannot be formed safely."""


class ProbeError(Exception):
    """Transport or response framing failed, with a value-free diagnostic."""


@dataclass(frozen=True)
class Response:
    status: int
    headers: dict[str, str]
    body: bytes


def validate_url(url: str) -> SplitResult:
    if not url or len(url) > 8192 or not url.isascii() or any(ord(c) <= 32 for c in url):
        raise InputError("URL must be ASCII, percent-encoded, and contain no whitespace")
    try:
        parsed = urlsplit(url)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or "#" in url
            or parsed.port == 0
            or "\\" in url
            or "\x7f" in url
        ):
            raise ValueError
        _ = parsed.port
    except ValueError:
        raise InputError("Use an absolute HTTP(S) URL without credentials or fragments") from None
    return parsed


def parse_content_range(value: str) -> tuple[int, int, int]:
    matched = CONTENT_RANGE.fullmatch(value.strip())
    if not matched:
        raise ProbeError("invalid_content_range")
    start, end, total = map(int, matched.groups())
    if not 0 <= start <= end < total <= MAX_SIZE:
        raise ProbeError("invalid_content_range")
    return start, end, total


def exchange(
    target: SplitResult,
    range_header: str,
    *,
    read_limit: int,
    timeout: float,
    if_range: str | None = None,
) -> Response:
    """No redirects, proxies, cookies, decompression, or retained connections."""
    cls = http.client.HTTPSConnection if target.scheme == "https" else http.client.HTTPConnection
    kwargs = {"context": ssl.create_default_context()} if target.scheme == "https" else {}
    connection = cls(target.hostname, target.port, timeout=timeout, **kwargs)
    headers = {
        "Range": range_header,
        "Accept-Encoding": "identity",
        "User-Agent": f"rangewitness/{__version__}",
        "Connection": "close",
    }
    if if_range is not None:
        headers["If-Range"] = if_range
    path = target.path or "/"
    if target.query:
        path += "?" + target.query
    try:
        connection.request("GET", path, headers=headers)
        with connection.getresponse() as response:
            selected: dict[str, str] = {}
            for name in ("Content-Range", "Content-Length", "Content-Encoding", "ETag"):
                values = response.headers.get_all(name, [])
                if len(values) > 1:
                    raise ProbeError("duplicate_response_header")
                if values:
                    if len(values[0]) > 4096:
                        raise ProbeError("response_header_too_long")
                    selected[name.lower()] = values[0].strip()
            if response.headers.get("Transfer-Encoding") and "content-length" in selected:
                raise ProbeError("ambiguous_response_framing")
            # One sentinel byte detects oversize responses without downloading an ignored range.
            body = response.read(read_limit + 1) if read_limit else b""
            return Response(response.status, selected, body)
    except (OSError, http.client.HTTPException, UnicodeError, ValueError) as exc:
        raise ProbeError("transport_error_" + type(exc).__name__) from None
    finally:
        connection.close()


def _range_errors(
    response: Response,
    expected: tuple[int, int, int],
    reference: bytes | None,
    etag: str | None,
) -> list[str]:
    errors = []
    if response.status != 206:
        return ["range_ignored_200" if response.status == 200 else "expected_206"]
    try:
        if parse_content_range(response.headers.get("content-range", "")) != expected:
            errors.append("wrong_content_range")
    except ProbeError as exc:
        errors.append(str(exc))
    size = expected[1] - expected[0] + 1
    if len(response.body) != size:
        errors.append("wrong_body_length")
    length = response.headers.get("content-length")
    if length is not None and (not length.isascii() or not length.isdigit() or int(length) != size):
        errors.append("wrong_content_length")
    if response.headers.get("content-encoding", "identity").lower() != "identity":
        errors.append("unexpected_content_encoding")
    if reference is not None and response.body != reference:
        errors.append("reference_bytes_differ")
    current_etag = response.headers.get("etag")
    if etag is not None and current_etag is not None and current_etag != etag:
        errors.append("representation_etag_changed")
    return errors


def audit(
    url: str,
    *,
    reference: Path | None = None,
    sample_bytes: int = 64,
    timeout: float = 5.0,
) -> dict:
    """Run at most seven sequential GET requests against one stable asset."""
    target = validate_url(url)
    if type(sample_bytes) is not int or not 1 <= sample_bytes <= 4096:
        raise InputError("sample_bytes must be an integer in 1..4096")
    if isinstance(timeout, bool) or not math.isfinite(timeout) or not 0 < timeout <= 60:
        raise InputError("timeout must be finite and in (0, 60] seconds")
    reference_size = None
    if reference is not None:
        if not reference.is_file():
            raise InputError("reference must be a readable regular file")
        reference_size = reference.stat().st_size
        if not 1 <= reference_size <= MAX_SIZE:
            raise InputError("reference must be nonempty and at most 2^63-1 bytes")

    report = {
        "schema_version": 1,
        "tool_version": __version__,
        "target_sha256": hashlib.sha256(url.encode("ascii")).hexdigest(),
        "reference_checked": reference is not None,
        "sample_bytes": sample_bytes,
        "body_read_limit_per_request": sample_bytes + 1,
        "checks": [],
    }
    checks = report["checks"]

    def receive(name, header, limit=sample_bytes, validator=None):
        check = {"name": name, "request_range": header, "status": "failed", "errors": []}
        checks.append(check)
        try:
            response = exchange(
                target, header, read_limit=limit, timeout=timeout, if_range=validator
            )
        except ProbeError as exc:
            check["errors"] = [str(exc)]
            return check, None
        check.update(http_status=response.status, bytes_read=len(response.body))
        return check, response

    def expected_bytes(start, end):
        if reference is None:
            return None
        with reference.open("rb") as stream:
            stream.seek(start)
            return stream.read(end - start + 1)

    def finish():
        report["status"] = "failed" if any(c["status"] == "failed" for c in checks) else "passed"
        report["requests"] = sum(c["status"] != "skipped" for c in checks)
        report["bytes_read"] = sum(c.get("bytes_read", 0) for c in checks)
        return report

    first, prefix = receive("prefix", f"bytes=0-{sample_bytes - 1}")
    if prefix is None:
        return finish()
    if prefix.status != 206:
        first["errors"] = ["range_ignored_200" if prefix.status == 200 else "expected_206"]
        return finish()
    try:
        _, _, total = parse_content_range(prefix.headers.get("content-range", ""))
    except ProbeError as exc:
        first["errors"] = [str(exc)]
        return finish()
    report["representation_bytes"] = total
    if reference_size is not None and total != reference_size:
        first["errors"] = ["reference_size_differs"]
        return finish()
    prefix_end = min(sample_bytes, total) - 1
    etag = prefix.headers.get("etag")
    first["errors"] = _range_errors(
        prefix, (0, prefix_end, total), expected_bytes(0, prefix_end), None
    )
    first["status"] = "failed" if first["errors"] else "passed"
    if first["errors"]:
        return finish()

    offset = min(sample_bytes // 2, total - 1)
    suffix_start = max(0, total - sample_bytes)
    specs = [
        ("offset", f"bytes={offset}-{min(total - 1, offset + sample_bytes - 1)}", offset),
        ("suffix", f"bytes=-{sample_bytes}", suffix_start),
        ("open_ended", f"bytes={suffix_start}-", suffix_start),
    ]
    suffix = None
    for name, header, start in specs:
        end = min(total - 1, start + sample_bytes - 1)
        check, response = receive(name, header)
        if response is None:
            continue
        check["errors"] = _range_errors(
            response, (start, end, total), expected_bytes(start, end), etag
        )
        if name == "offset":
            overlap = min(len(prefix.body) - start, len(response.body))
            if response.body[:overlap] != prefix.body[start : start + overlap]:
                check["errors"].append("overlapping_bytes_differ")
        if name == "suffix":
            suffix = response.body
        if name == "open_ended" and suffix is not None and response.body != suffix:
            check["errors"].append("suffix_open_ended_bytes_differ")
        check["status"] = "failed" if check["errors"] else "passed"

    check, response = receive("unsatisfied", f"bytes={total}-", limit=0)
    if response is not None:
        match = UNSATISFIED.fullmatch(response.headers.get("content-range", ""))
        if response.status != 416:
            check["errors"].append("expected_416")
        if not match or int(match[1]) != total:
            check["errors"].append("wrong_unsatisfied_content_range")
        check["status"] = "failed" if check["errors"] else "passed"

    if etag is not None and STRONG_ETAG.fullmatch(etag):
        check, response = receive("if_range_match", f"bytes=0-{prefix_end}", validator=etag)
        if response is not None:
            check["errors"] = _range_errors(response, (0, prefix_end, total), prefix.body, etag)
            check["status"] = "failed" if check["errors"] else "passed"
        missing = '"rangewitness-deliberately-different"'
        if missing == etag:
            missing = '"rangewitness-deliberately-different-2"'
        check, response = receive("if_range_miss", "bytes=0-0", limit=0, validator=missing)
        if response is not None:
            if response.status != 200:
                check["errors"].append("if_range_miss_expected_200")
            if "content-range" in response.headers:
                check["errors"].append("if_range_miss_has_content_range")
            check["status"] = "failed" if check["errors"] else "passed"
    else:
        for name in ("if_range_match", "if_range_miss"):
            checks.append({"name": name, "status": "skipped", "reason": "no_strong_etag"})
    return finish()
