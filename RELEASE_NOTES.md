# v0.1.0

Initial usable release of bounded HTTP byte-serving deployment checks.

- Prefix, nonzero offset, suffix, open-ended and unsatisfied-range probes.
- Strong ETag If-Range match/mismatch checks, with explicit skips when unavailable.
- Optional reference-file byte checks; redacted JSON and stable exit codes.
- At most seven sequential GETs; 1–4096-byte samples and one sentinel byte.
- No runtime dependencies. Wheel, source distribution and SHA-256 checksums.

Validation: 60 tests, 98% branch-aware total coverage, Ruff, isolated build and
clean-wheel CLI smoke against correct, corrupt and Range-ignoring loopback endpoints.
See the release commit's CI for the actual Linux, Windows and macOS matrix result.

Limitations: single ranges over HTTP/1.1; no redirects, auth headers, proxy
configuration, multipart ranges or full remote-file integrity proof. Missing
strong ETags skip conditional checks. Socket timeouts are not a whole-run deadline.
