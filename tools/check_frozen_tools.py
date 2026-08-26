"""Does the app actually start out of the built executable, every way in?

There is one .exe and one window, reached three ways: plain, --tool mhd and
--tool autotuner. Nothing imports the area modules at module level, so
PyInstaller only bundles them because of --hidden-import. Miss that flag and
the build succeeds, the installer succeeds, the window opens, and it dies on
ModuleNotFoundError the moment somebody clicks a Start menu entry.

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


def _annotate(message):
    """Say it where it can still be read when the log cannot be.

    A workflow command becomes an annotation on the run, and an annotation
    comes back through the API. The plain log does not, from everywhere.
    """
    if os.environ.get("GITHUB_ACTIONS") != "true":
        return
    flat = message.replace("\r", "").replace("\n", "%0A")[:3000]
    print(f"::error title=frozen app::{flat}", flush=True)


def check(exe, key):
    """Start the app the way `key` names it, let it live, then stop it."""
    command = [exe] if key is None else [exe, suite.TOOL_FLAG, key]
    handle, log = tempfile.mkstemp(prefix=f"frozen_{key or 'plain'}_", suffix=".log")
    os.close(handle)
    started = time.time()
    with open(log, "w", encoding="utf-8", errors="replace") as sink:
        process = subprocess.Popen(command,
                                   stdout=sink, stderr=subprocess.STDOUT,
                                   stdin=subprocess.DEVNULL)
        # Waited out in small steps rather than one sleep, so a window that
        # dies early is caught with its exit code instead of being reported
        # eight seconds later as simply absent.
        deadline = started + SETTLE
        while time.time() < deadline and process.poll() is None:
            time.sleep(0.25)
        code = process.poll()
        alive = code is None
        _kill_tree(process)

    with open(log, encoding="utf-8", errors="replace") as source:
        output = source.read().strip()
    os.unlink(log)

    how = "no flag" if key is None else f"--tool {key}"
    lived = time.time() - started
    broke = "Traceback" in output or "ModuleNotFoundError" in output
    if alive and not broke:
        print(f"  ok      {how}", flush=True)
        return True
    print(f"  FAILED  {how}  (still running: {alive}, exit code: {code}, "
          f"lived {lived:.1f}s)", flush=True)
    for line in output.splitlines()[-12:]:
        print(f"          {line}", flush=True)
    _annotate(f"{how}: exit code {code} after {lived:.1f}s\n"
              + ("\n".join(output.splitlines()[-12:]) or "(it said nothing at all)"))
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
    print(f"Starting the app every way out of {exe}", flush=True)
    ways = [None] + [tool["key"] for tool in suite.TOOLS]
    results = [check(exe, key) for key in ways]
    if all(results):
        print(f"All {len(results)} way(s) in start.", flush=True)
        return 0
    print("The app did not start. The executable is missing its modules: check "
          "the --hidden-import flags on the pyinstaller call.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
