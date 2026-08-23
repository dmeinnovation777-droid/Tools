"""
Optional screenshot helper for the GUI smoke tests.

Grabbing the X root window needs `xwd` (Debian/Ubuntu: x11-apps). It is a
development convenience, never a test criterion — without it the smoke tests
run exactly the same, they just do not leave a picture behind.
"""

import os
import shutil
import subprocess


def shoot(name: str, out_dir: str = "/tmp") -> str | None:
    """Save the X root window as <out_dir>/shot_<name>.xwd, or return None."""
    if not shutil.which("xwd"):
        return None
    path = os.path.join(out_dir, f"shot_{name}.xwd")
    try:
        subprocess.run(["xwd", "-root", "-silent", "-out", path], check=True)
    except (OSError, subprocess.CalledProcessError):
        return None
    return path
