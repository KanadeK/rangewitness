# Dependencies and sources

There are no runtime dependencies. The Python interpreter and its standard
library are external prerequisites under their own PSF license.

Development tools are installed separately: pytest (MIT), coverage.py (Apache-2.0),
Ruff (MIT), build (MIT), setuptools (MIT), and their transitive dependencies.
They are not bundled into this project's wheel. GitHub Actions use official
checkout and setup-python actions pinned to verified commit SHAs, with read-only
repository permissions and no automated commits.

RFC 9110 and public issue reports informed the behavior. No RFC code components,
third-party implementation snippets or external datasets are included. Examples
and fixtures are original synthetic data.
