# rangewitness

Check whether a deployed file really serves the requested HTTP byte ranges.
Useful for download, video, audio and map-asset deployments where a successful
GET or an `Accept-Ranges` header does not establish correct offset handling.

`rangewitness` makes up to **seven sequential GET requests**, samples at most
65 body bytes per request by default, and returns a CI-friendly result. With a
local reference file it checks the actual sampled bytes, including their offsets.
It does not need an account, paid service, browser or runtime dependency.

## Install

Python 3.11 or later:

```sh
git clone https://github.com/KanadeK/rangewitness.git
cd rangewitness
python -m venv .venv
```

Activate with `.venv\Scripts\Activate.ps1` on PowerShell, or
`. .venv/bin/activate` on Linux/macOS, then:

```sh
python -m pip install .
```

Alternatively install the wheel attached to the GitHub release:

```sh
python -m pip install https://github.com/KanadeK/rangewitness/releases/download/v0.1.0/rangewitness-0.1.0-py3-none-any.whl
```

## Try a complete local demonstration

From the source checkout after installation:

```sh
python scripts/smoke.py
```

This starts a disposable loopback server and exercises the installed CLI. The
correct endpoint exits `0`; an endpoint with corrupt offset bytes and an endpoint
that ignores Range each exit `1`. The demo verifies those failures itself and
exits successfully only when all three outcomes are correct. It uses synthetic
bytes, needs no internet access, and shuts down the server and deletes its temp
reference automatically.

## Check your deployment

Replace the example URL with a **direct, stable file URL you operate**:

```sh
rangewitness https://downloads.example.org/asset.bin --reference asset.bin --json
```

Omit `--reference` for header, length and overlapping-sample consistency checks:

```sh
rangewitness https://downloads.example.org/asset.bin --sample-bytes 256 --timeout 5
```

The JSON `checks` contain `name`, `status`, `http_status`, `bytes_read` and stable
error codes such as `wrong_content_range`, `reference_bytes_differ` and
`if_range_miss_expected_200`. No response body, ETag, file path or full URL is
printed. `target_sha256` identifies the URL supplied to this run; it is a
correlation hash, **not encryption of a secret URL**.

| Check | Required behavior |
|---|---|
| Prefix | `206`, exact Content-Range and sampled byte count |
| Offset | Correct nonzero starting offset and overlapping bytes |
| Suffix | Correct `bytes=-N` interval |
| Open ended | Correct `bytes=start-` interval; matches suffix bytes |
| Unsatisfied | `416`, `Content-Range: bytes */length` |
| If-Range match | Matching strong ETag yields the original prefix |
| If-Range mismatch | Different ETag yields `200` without Content-Range |

If no valid strong ETag is supplied, both If-Range checks are explicitly skipped;
five other checks can still pass. A JSON pass therefore means all **performed**
checks passed; inspect skipped checks when conditional resume matters.

Exit `0`: performed contract checks passed. Exit `1`: contract/transport failure.
Exit `2`: invalid arguments or unreadable local reference.

## Scope and operating limits

- The contract is intentionally stricter than generic HTTP compliance. RFC 9110
  allows a server to ignore Range and respond `200`; this tool reports that as
  failure to meet a **byte-serving deployment contract**, not an RFC violation.
- Sample size is 1–4096 bytes. A single sentinel byte detects overlong responses.
  At most seven requests are made. No redirects, retries, environment proxies,
  cookie storage or automatic decompression are used. HTTPS verifies certificates.
- Only HTTP/1.1 single-range requests are tested. Multipart ranges, HTTP/2,
  HTTP-date validators, authentication headers and redirect chains are outside
  v0.1.0. An empty representation cannot satisfy this test's nonempty-file contract.
- Without a local reference, consistency does not prove that the bytes are the
  intended asset. Even with a reference this samples bytes; it does not hash the
  entire remote object. Keep the asset and local reference stable during a run.
- If-Range mismatch and 416 responses are checked from headers without reading
  their bodies. Closing early bounds application reads; a server/network stack
  may already have transmitted or buffered more bytes.
- `--timeout` is a socket-operation timeout, not a whole-run deadline. A server
  that slowly trickles bytes can take longer. Use an external job timeout for a
  hard wall-clock limit. No URL is followed automatically.
- Only the explicitly supplied URL is contacted. Reports omit values but their
  hashes and lengths can still reveal correlations; review reports before sharing.

## Development and release verification

```sh
python -m pip install -e ".[dev]"
python scripts/verify.py
```

The gate runs Ruff lint/format checks, unit and real-loopback integration tests
with branch-aware coverage (minimum 90%), builds wheel and source distribution,
installs the wheel into a clean virtual environment, then exercises the installed
CLI from outside the repository. CI runs the same gate on Linux, Windows and
macOS. See [VALIDATION.md](VALIDATION.md) for recorded release evidence.

To uninstall, run `python -m pip uninstall rangewitness`. To remove the isolated
environment, deactivate and delete the `.venv` directory you created. The tool
keeps no cache or persistent working files; `dist/`, `build/` and test caches are
development outputs and can be deleted from the checkout.

## Why another tool?

[curl](https://curl.se/docs/manpage.html) is excellent for individual requests;
[httprange](https://pypi.org/project/httprange/) provides
protocol parsing/building, and
[RangeHTTPServer](https://github.com/danvk/RangeHTTPServer) serves files.
This project packages bounded live-server probes, reference-byte checks and
machine-readable failures into one deployment gate. Its behavior follows
[RFC 9110 §14](https://www.rfc-editor.org/rfc/rfc9110.html#section-14) and
[If-Range §13.1.5](https://www.rfc-editor.org/rfc/rfc9110.html#section-13.1.5).
The [CPython Range issue](https://github.com/python/cpython/issues/86809)
illustrates the real deployment problem. No implementation code was copied
from those sources.

## 中文说明

rangewitness 检查文件下载服务是否真的按 HTTP Range 返回正确区间，而不是仅检查
`Accept-Ranges` 响应头。提供本地原文件后，会核对采样字节及偏移。可用于发布前验证
下载、视频和地图文件服务。`python scripts/smoke.py` 会启动本地测试服务器，验证
正常服务通过、错误字节和忽略 Range 的服务失败。默认最多七次请求，单次最多读取
65 字节；没有强 ETag 时会明确跳过两个 If-Range 检查。v0.1.0 不验证整个远程文件。

MIT licensed. See [CONTRIBUTING.md](CONTRIBUTING.md) and [SECURITY.md](SECURITY.md).
