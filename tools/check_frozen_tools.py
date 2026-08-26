"""Does every tool actually start out of the built executable?

The suite is one .exe carrying three programs, reached with --tool <key>.
Nothing imports the tool modules at module level, so PyInstaller only bundles
them because of --hidden-import. Miss that flag and the build succeeds, the
installer succeeds, the launcher opens, and every tool dies on
ModuleNotFoundError the moment somebody clicks it.

That shipped twice. This runs after the build and refuses to let it happen a
third time: start each tool for real, and fail on any traceback.

Two things this must not do, both learned the hard way on the Windows runner:

* No pipes. A onefile build starts a child process that inherits the pipe
  handles, so terminating the parent leaves them open and communicate() waits
  for a writer that will never close. Output goes to a file instead.
* No plain terminate(). It reaches the bootloader, not the app it spawned, so
  the whole process tree has to go.
"""

import os
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import dme_suite as suite      # noqa: E402

SETTLE = 8          # seconds a window needs to come up on a cold runner
GRACE = 15          # seconds to wait for the tree to die


def _kill_tree(process):
    if os.name == "nt":
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(process.pid)],
                       capture_output=True)
    else:
        process.kill()
    try:
        process.wait(timeout=GRACE)
    except subprocess.TimeoutExpired:
        pass


def check(exe, key):
    """Start `exe --tool key`, let it live, then stop it. True when it survived."""
    handle, log = tempfile.mkstemp(prefix=f"frozen_{key}_", suffix=".log")
    os.close(handle)
    with open(log, "w", encoding="utf-8", errors="replace") as sink:
        process = subprocess.Popen([exe, suite.TOOL_FLAG, key],
                                   stdout=sink, stderr=subprocess.STDOUT,
                                   stdin=subprocess.DEVNULL)
        time.sleep(SETTLE)
        alive = process.poll() is None
        _kill_tree(process)

    with open(log, encoding="utf-8", errors="replace") as source:
        output = source.read().strip()
    os.unlink(log)

    broke = "Traceback" in output or "ModuleNotFoundError" in output
    if alive and not broke:
        print(f"  ok      --tool {key}", flush=True)
        return True
    print(f"  FAILED  --tool {key}  (still running: {alive})", flush=True)
    for line in output.splitlines()[-8:]:
        print(f"          {line}", flush=True)
    return False


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: check_frozen_tools.py <path to the built executable>",
              file=sys.stderr)
        return 2
    exe = sys.argv[1]
    if not os.path.isfile(exe):
        print(f"no such executable: {exe}", file=sys.stderr)
        return 2
    print(f"Starting every tool out of {exe}", flush=True)
    results = [check(exe, tool["key"]) for tool in suite.TOOLS]
    if all(results):
        print(f"All {len(results)} tool(s) start.", flush=True)
        return 0
    print("A tool did not start. The executable is missing its modules: check "
          "the --hidden-import flags on the pyinstaller call.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
