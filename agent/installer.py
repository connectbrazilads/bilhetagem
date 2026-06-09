from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def main() -> None:
    service_file = Path(__file__).with_name("service.py")
    commands = [
        [sys.executable, str(service_file), "install", "--startup", "auto"],
        [sys.executable, str(service_file), "start"],
    ]
    for command in commands:
        subprocess.run(command, check=True)


if __name__ == "__main__":
    main()
