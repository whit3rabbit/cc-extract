# Release Checklist

`ccsilo` is intended to be installed by users with `pipx install ccsilo`
after a PyPI release. Releases are published by `.github/workflows/release.yml`
using PyPI Trusted Publishing, so no PyPI API token should be stored in GitHub.

## One-Time PyPI Setup

Configure Trusted Publishers before the first automated upload.

For TestPyPI:

- Project name: `ccsilo`
- Owner: `whit3rabbit`
- Repository: `ccsilo`
- Workflow: `release.yml`
- Environment: `testpypi`

For PyPI:

- Project name: `ccsilo`
- Owner: `whit3rabbit`
- Repository: `ccsilo`
- Workflow: `release.yml`
- Environment: `pypi`

Create matching GitHub environments named `testpypi` and `pypi`. Require manual
approval on the `pypi` environment before publishing public releases.

## Build And Validate

```bash
.venv/bin/python -m pip install -e '.[dev]'
rm -rf dist build *.egg-info
.venv/bin/python -m pytest -q
.venv/bin/python -m build
.venv/bin/python -m twine check dist/*
```

## TestPyPI

Run the `Release` workflow manually with `repository=testpypi`.

After it publishes, verify from a clean environment:

```bash
python -m venv /tmp/ccsilo-testpypi
/tmp/ccsilo-testpypi/bin/python -m pip install --upgrade pip
/tmp/ccsilo-testpypi/bin/python -m pip install \
  --index-url https://test.pypi.org/simple/ \
  --extra-index-url https://pypi.org/simple/ \
  ccsilo
/tmp/ccsilo-testpypi/bin/ccsilo --help
/tmp/ccsilo-testpypi/bin/ccsilo variant providers --json
```

## PyPI

Publish to PyPI by creating a GitHub Release. The `Release` workflow also has a
manual `repository=pypi` dispatch path for recovery releases; use the protected
`pypi` environment approval gate for that path.

After publishing:

```bash
pipx install ccsilo
ccsilo paths
ccsilo --help
```

After publishing, update the README only if the user install command or release
source changes.
