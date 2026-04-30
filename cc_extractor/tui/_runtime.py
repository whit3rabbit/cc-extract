"""Runtime utilities used by both the action layer and the helper submodules."""

import contextlib
import io


def run_quiet(func, *args, **kwargs):
    """Call ``func`` with stdout/stderr captured into a single combined string.

    Returns ``(result, captured_text)``.
    """
    stdout = io.StringIO()
    stderr = io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        result = func(*args, **kwargs)
    output = "\n".join(
        part.strip()
        for part in (stdout.getvalue(), stderr.getvalue())
        if part.strip()
    )
    return result, output
