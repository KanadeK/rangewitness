# Contract and acceptance

User: an operator shipping a stable public static asset. Task: detect broken
byte serving before users attempt seek/resume, without downloading the asset.

The complete workflow is install → supply direct URL and optional original file
→ issue bounded probes → inspect check evidence and CI exit. The tool reads only
the reference supplied by the operator; it does not modify local or remote data.
GETs can still appear in access logs and count toward traffic quotas.

Implementation: Python standard library `http.client` with default verified TLS,
no redirect handler or proxy discovery; bounded response samples; strict critical
header cardinality; separate transport and contract errors. Results deliberately
omit response values and URL components. Tests inject failures into a separate
real loopback HTTP server, rather than hardcoding expected audit reports.

Release acceptance:

1. Correct server passes all seven checks with an exact original fixture.
2. Corrupt offset body, ignored Range, wrong intervals, short/oversized body,
   content coding, changed ETag, incorrect 416 and If-Range mismatch all fail.
3. Tiny files and optional missing/weak ETags are handled explicitly.
4. Reference remains byte-for-byte unchanged; input errors do not contact a URL.
5. Output does not include fixture tokens, body bytes, ETags or reference paths.
6. Lint, formatting, coverage gate, distribution build and clean install pass.
7. CI passes and Git owner/author/committer/contributors are independently verified.

No security sandbox or full RFC conformance claim is made. The server may be
malicious or change during a run; errors cause failure, not unsafe recovery.
