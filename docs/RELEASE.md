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

The PyPI `Workflow name` field is the workflow filename only, not the display
name. Use `release.yml`, because the file is
`.github/workflows/release.yml`.

Do not add a PyPI API token or password to GitHub. The publish jobs request
`id-token: write` and use `pypa/gh-action-pypi-publish`, which exchanges the
GitHub OIDC token with PyPI or TestPyPI.

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

From the GitHub UI:

1. Open `Actions`.
2. Select `Release`.
3. Choose `Run workflow`.
4. Set `Package index to publish to` to `testpypi`.
5. Run it from `main`.

From the GitHub CLI:

```bash
gh workflow run release.yml --ref main -f repository=testpypi
gh run list --workflow release.yml --limit 1
gh run watch
```

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

Before publishing to PyPI:

1. Confirm the TestPyPI package installed and ran.
2. Confirm `pyproject.toml` has the intended version.
3. Confirm the tag and GitHub Release point at the intended commit.

For a normal release:

```bash
git tag v0.1.0
git push upstream v0.1.0
```

Then create and publish a GitHub Release for that tag. Publishing the GitHub
Release triggers `.github/workflows/release.yml` and uploads to PyPI after the
`pypi` environment approval gate passes.

After publishing:

```bash
pipx install ccsilo
ccsilo paths
ccsilo --help
```

After publishing, update the README only if the user install command or release
source changes.

## Version Rules

PyPI versions are immutable. If a real PyPI upload succeeds, fails after
creating the project, or partially uploads files for a version, do not retry the
same version blindly. Bump `pyproject.toml`, commit the bump, tag the new
version, and publish again.

TestPyPI is also effectively immutable for a given filename. For repeated
TestPyPI dry runs, bump the version or use a local build and `twine check`
instead.
