# v0.1.0 validation

Recorded locally on 2026-10-24 using Windows and CPython 3.13.16.

- 60 tests passed, including real HTTP loopback integration tests.
- Branch-aware coverage: 98% overall; core module 99%.
- Ruff lint and formatting checks passed.
- Wheel and sdist build succeeded. The release gate installs the wheel into an
  independent virtual environment and runs the actual CLI outside the source tree.
- The smoke workflow requires a correct endpoint to pass and both corrupt-byte
  and Range-ignoring endpoints to fail, using a synthetic local reference file.
- Review fixed a test isolation problem: mocking global `Path.stat` affected the
  test runner. The test now injects the error at the CLI boundary. No production
  behavior was weakened. Source distributions explicitly include scripts/examples.

Self-review covered header ambiguity, body read bounds, URL credentials/control
characters, verified TLS, redaction, reference preservation and documented HTTP
scope. No runtime dependency or copied third-party code is distributed. The CI
matrix is the source of evidence for operating systems not executed locally;
inspect the workflow attached to the release commit for its actual result.

The absence of a discovered problem is not proof of universal protocol
conformance. See README limits, particularly sampling and socket timeouts.
