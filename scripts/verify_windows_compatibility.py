from __future__ import annotations

import argparse
from pathlib import Path

import pefile


FORBIDDEN_IMPORTS = {
    "PssCaptureSnapshot",
    "PssDuplicateSnapshot",
    "PssFreeSnapshot",
    "PssQuerySnapshot",
    "PssWalkMarkerCreate",
    "PssWalkMarkerFree",
    "PssWalkSnapshot",
}


def imported_symbols(path: Path) -> set[str]:
    try:
        image = pefile.PE(str(path), fast_load=True)
        image.parse_data_directories(
            directories=[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_IMPORT"]]
        )
    except pefile.PEFormatError:
        return set()
    result: set[str] = set()
    for library in getattr(image, "DIRECTORY_ENTRY_IMPORT", []):
        for entry in library.imports:
            if entry.name:
                result.add(entry.name.decode("ascii", errors="replace"))
    image.close()
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit a Windows 7-compatible release folder")
    parser.add_argument("directory", type=Path)
    parser.add_argument("--architecture", choices=("x64", "x86"), required=True)
    args = parser.parse_args()

    directory = args.directory.resolve()
    executable = directory / "TradeQuery.exe"
    if not executable.is_file():
        raise SystemExit(f"Missing packaged executable: {executable}")

    image = pefile.PE(str(executable), fast_load=True)
    expected_machine = 0x8664 if args.architecture == "x64" else 0x14C
    if image.FILE_HEADER.Machine != expected_machine:
        raise SystemExit(
            f"Architecture mismatch: expected {args.architecture}, machine=0x{image.FILE_HEADER.Machine:04x}"
        )
    image.close()

    files = list(directory.rglob("*.exe")) + list(directory.rglob("*.dll"))
    violations: list[str] = []
    for path in files:
        forbidden = sorted(imported_symbols(path) & FORBIDDEN_IMPORTS)
        if forbidden:
            violations.append(f"{path.relative_to(directory)}: {', '.join(forbidden)}")
    if violations:
        raise SystemExit("Windows 8.1-only imports detected:\n" + "\n".join(violations))

    internal = directory / "_internal"
    required = (internal / "python38.dll", internal / "VCRUNTIME140.dll")
    missing = [str(path.relative_to(directory)) for path in required if not path.is_file()]
    if missing:
        raise SystemExit("Missing bundled runtimes: " + ", ".join(missing))

    print(
        f"Compatibility audit passed for {args.architecture}: "
        f"{len(files)} PE files, no Windows 8.1-only process snapshot imports"
    )


if __name__ == "__main__":
    main()
