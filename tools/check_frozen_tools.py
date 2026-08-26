"""Does every tool actually start out of the built executable?

The suite is one .exe carrying three programs, reached with --tool <key>.
Nothing imports the tool modules at module level, so PyInstaller only bundles
them because of --hidden-import. Miss that flag and the build succeeds, the
installer succeeds, the launcher opens, and every tool dies on
ModuleNotFoundError the moment somebody clicks it.

That shipped twice. This runs after the build and refuses to let it happen a
third time: start each tool for real, and fail on any traceback.
"""

import subprocess
import sys
import time

sys.path.insert(0, ".")
import dme_suite as suite      # noqa: E402

SETTLE = 8          # seconds a window needs to come up on a cold CI runner
STOP = 20


def check(exe, key):
    """Start `exe --tool key`, let it live, then stop it. True when it survived."""
    process = subprocess.Popen([exe, suite.TOOL_FLAG, key],
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               text=True)
    time.sleep(SETTLE)
    alive = process.poll() is None
    if alive:
        process.terminate()
    try:
        _out, err = process.communicate(timeout=STOP)
    except subprocess.TimeoutExpired:
        process.kill()
        _out, err = process.communicate()
        alive = True
    err = (err or "").strip()
    broke = "Traceback" in err or "ModuleNotFoundError" in err
    if alive and not broke:
        print(f"  ok      --tool {key}")
        return True
    print(f"  FAILED  --tool {key}")
    for line in err.splitlines()[-6:]:
        print(f"          {line}")
    return False


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: check_frozen_tools.py <path to the built executable>",
              file=sys.stderr)
        return 2
    exe = sys.argv[1]
    print(f"Starting every tool out of {exe}")
    results = [check(exe, tool["key"]) for tool in suite.TOOLS]
    if all(results):
        print(f"All {len(results)} tool(s) start.")
        return 0
    print("A tool did not start. The executable is missing its modules: check "
          "the --hidden-import flags on the pyinstaller call.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
