#!/usr/bin/env python3
"""Cross-platform test loop harness for Reasoner.

Usage: python scripts/test_loop.py [pytest args...]
"""

import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path


def main():
    project_dir = Path(__file__).parent.parent.resolve()
    log_dir = project_dir / "logs"
    app_log = log_dir / "app.log"
    test_log = log_dir / "test_run.log"

    # Colors (disabled on Windows without colorama)
    if sys.platform != "win32":
        RED, GREEN, YELLOW, BLUE, NC = "\033[31m", "\033[32m", "\033[33m", "\033[34m", "\033[0m"
    else:
        RED = GREEN = YELLOW = BLUE = NC = ""

    print(f"{BLUE}=== Reasoner Test Loop ==={NC}\n")

    # Step 1: Clear logs
    print(f"{YELLOW}Clearing logs...{NC}")
    log_dir.mkdir(exist_ok=True)
    app_log.write_text("")
    test_log.write_text(f"Test run started at {datetime.now().isoformat()}\n")

    # Step 2: Run tests
    print(f"{YELLOW}Running tests...{NC}")
    pytest_args = sys.argv[1:] if len(sys.argv) > 1 else []
    cmd = ["uv", "run", "pytest"] + pytest_args

    result = subprocess.run(
        cmd,
        cwd=project_dir,
        capture_output=False,
    )

    with test_log.open("a") as f:
        f.write(f"\nTest completed at {datetime.now().isoformat()} with exit code {result.returncode}\n")

    # Step 3: Report results
    print()
    if result.returncode == 0:
        print(f"{GREEN}=== ALL TESTS PASSED ==={NC}")
    else:
        print(f"{RED}=== TESTS FAILED ==={NC}\n")

        # Extract errors from app.log
        if app_log.exists() and app_log.stat().st_size > 0:
            print(f"{YELLOW}=== Relevant Log Entries ==={NC}")
            try:
                for line in app_log.read_text().splitlines():
                    try:
                        entry = json.loads(line)
                        if entry.get("level") in ("ERROR", "WARNING"):
                            req_id = entry.get("request_id", "-")
                            req_id_short = req_id[:8] if req_id != "-" else "-"
                            msg = entry.get("message", "")
                            level = entry.get("level", "")
                            print(f"[{req_id_short}] {level}: {msg}")
                            if "error" in entry:
                                err = entry["error"]
                                print(f"         Type: {err.get('type', 'Unknown')}")
                                if err.get("message"):
                                    print(f"         Message: {err.get('message', '')}")
                    except json.JSONDecodeError:
                        pass
            except Exception as e:
                print(f"Could not parse log: {e}")
            print()

        print(f"{YELLOW}Commands for debugging:{NC}")
        print(f"  View app log:     cat {app_log}")
        print(f"  View test log:    cat {test_log}")
        print(f"  Parse log:        python -c \"import json; [print(json.loads(l)) for l in open('{app_log}')]\"")

    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
