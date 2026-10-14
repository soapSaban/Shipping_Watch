"""
Live Terminal Monitor for Shipping Watch
Continuously streams and colorizes logs from:
1. logs/system_monitor.log & output/system_monitor.log
2. Active Docker container runtime logs (stdout/stderr)
3. Return codes, error tracebacks, downloads, and HTTP requests
"""

import os
import sys
import time
import subprocess
from datetime import datetime

# ANSI Color Codes for terminal
RESET = "\033[0m"
BOLD = "\033[1m"
RED = "\033[91m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
MAGENTA = "\033[95m"
CYAN = "\033[96m"
GRAY = "\033[90m"

LOG_FILES = [
    "logs/system_monitor.log",
    "output/system_monitor.log"
]


def colorize_log_line(line: str) -> str:
    """Applies ANSI colors based on log content."""
    line_clean = line.rstrip()

    if "[ERROR  ]" in line or "ERROR" in line or "Failed" in line or "Exception" in line:
        return f"{RED}{BOLD}{line_clean}{RESET}"
    elif "[SUCCESS]" in line or "PASS" in line or "completed successfully" in line:
        return f"{GREEN}{BOLD}{line_clean}{RESET}"
    elif "[WARNING]" in line or "Warning" in line:
        return f"{YELLOW}{line_clean}{RESET}"
    elif "[CONTAINER]" in line:
        return f"{MAGENTA}{line_clean}{RESET}"
    elif "[HOST]" in line:
        return f"{CYAN}{line_clean}{RESET}"
    elif "[INFO   ]" in line:
        return f"{BLUE}{line_clean}{RESET}"
    else:
        return f"{GRAY}{line_clean}{RESET}"


def get_docker_status() -> str:
    """Checks if shipping_watch_assistant container is active."""
    try:
        res = subprocess.run(
            ["docker", "ps", "--filter", "name=shipping_watch_assistant", "--format", "{{.Status}} (Port {{.Ports}})"],
            capture_output=True,
            text=True,
            timeout=2
        )
        output = res.stdout.strip()
        return output if output else "Container not currently running"
    except Exception:
        return "Docker daemon not queried"


def tail_log_files():
    """Tails the system monitor log files with real-time updates."""
    # Find existing log file
    target_file = None
    for f in LOG_FILES:
        if os.path.exists(f):
            target_file = f
            break

    print("=" * 80)
    print(f"{BOLD}{CYAN} 🖥️  SHIPPING WATCH: UNIFIED PROCESS & SYSTEM MONITOR{RESET}")
    print("=" * 80)
    print(f"Monitoring Log File : {target_file or 'Waiting for logs/system_monitor.log...'}")
    print(f"Docker Status       : {get_docker_status()}")
    print("Press Ctrl+C to exit monitor (background tasks continue running)\n" + "-" * 80)

    # Wait for file to exist
    while target_file is None:
        for f in LOG_FILES:
            if os.path.exists(f):
                target_file = f
                break
        time.sleep(1)

    with open(target_file, "r", encoding="utf-8", errors="replace") as fp:
        # Seek to beginning to print initial context
        lines = fp.readlines()
        for line in lines[-40:]:  # Show last 40 lines
            print(colorize_log_line(line))

        # Stream new incoming lines
        while True:
            line = fp.readline()
            if line:
                print(colorize_log_line(line), flush=True)
            else:
                time.sleep(0.4)


if __name__ == "__main__":
    try:
        tail_log_files()
    except KeyboardInterrupt:
        print(f"\n{YELLOW}Monitor stopped. (Processes are still running in background.){RESET}")
        sys.exit(0)
