#!/usr/bin/env python3
"""Create a portable release ZIP for Hidden File Finder.

The script expects that the executable has already been built by PyInstaller.
It is intentionally small and uses only the Python standard library so it can
run on Windows build machines without extra dependencies.
"""

from __future__ import annotations

import argparse
import platform
import zipfile
from pathlib import Path

APP_NAME = "HiddenFileFinder"
VERSION = "1.0.0"


def default_platform_name() -> str:
    """Return a short platform label for release file names."""

    system = platform.system().lower()
    if system == "windows":
        return "Windows"
    if system == "darwin":
        return "macOS"
    if system == "linux":
        return "Linux"
    return system.capitalize() or "Unknown"


def default_executable_path(platform_name: str) -> Path:
    """Return the expected PyInstaller executable path for a platform."""

    suffix = ".exe" if platform_name.lower() == "windows" else ""
    return Path("dist") / f"{APP_NAME}{suffix}"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create a Hidden File Finder release ZIP.")
    parser.add_argument("--version", default=VERSION, help="Release version used in the ZIP filename.")
    parser.add_argument("--platform", default=default_platform_name(), help="Platform label, for example Windows.")
    parser.add_argument("--exe", type=Path, help="Path to the built executable.")
    parser.add_argument("--output", type=Path, help="Output ZIP path.")
    parser.add_argument("--archive-exe-name", help="Executable name to use inside the ZIP.")
    parser.add_argument(
        "--include",
        action="append",
        default=["README.md"],
        help="Additional file to include in the ZIP. Can be passed multiple times.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    executable = args.exe or default_executable_path(args.platform)
    output = args.output or Path("dist") / "release" / f"{APP_NAME}-{args.version}-{args.platform}-Portable.zip"

    if not executable.is_file():
        raise SystemExit(f"Executable not found: {executable}")

    output.parent.mkdir(parents=True, exist_ok=True)
    executable_name = args.archive_exe_name or (
        f"{APP_NAME}.exe" if args.platform.lower() == "windows" else executable.name
    )

    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.write(executable, executable_name)
        for extra in args.include:
            extra_path = Path(extra)
            if extra_path.is_file():
                archive.write(extra_path, extra_path.name)

    print(f"Release ZIP ready: {output}")


if __name__ == "__main__":
    main()
