"""Soft-failing macOS ad-hoc code signing."""

import platform
import subprocess
from dataclasses import dataclass


@dataclass
class AdhocSignResult:
    signed: bool
    reason: str = None
    detail: str = None


def try_adhoc_sign(binary_path):
    if platform.system() != "Darwin":
        return AdhocSignResult(signed=False, reason="no-codesign", detail="not darwin")

    try:
        result = subprocess.run(
            ["codesign", "--force", "--sign", "-", "--", str(binary_path)],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        return AdhocSignResult(signed=False, reason="no-codesign", detail="codesign binary not found in PATH")
    except OSError as exc:
        return AdhocSignResult(signed=False, reason="failed", detail=str(exc))

    if result.returncode != 0:
        detail = f"codesign exited {result.returncode}"
        stderr = (result.stderr or "").strip()
        if stderr:
            detail += f": {stderr}"
        return AdhocSignResult(signed=False, reason="failed", detail=detail)
    return AdhocSignResult(signed=True)
