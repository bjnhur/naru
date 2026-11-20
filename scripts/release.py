from __future__ import annotations

import argparse
import runpy
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(module: str, *args: str | Path) -> None:
    subprocess.run(
        [sys.executable, "-m", module, *map(str, args)], cwd=ROOT, check=True
    )


def check_distributions(directory: Path, version: str) -> list[Path]:
    files = [
        directory / f"naru_sitegen-{version}-py3-none-any.whl",
        directory / f"naru_sitegen-{version}.tar.gz",
    ]
    if not all(path.is_file() for path in files):
        raise SystemExit(f"Build both distributions in {directory} first.")
    run("twine", "check", "--strict", *files)
    return files


def main() -> None:
    parser = argparse.ArgumentParser(description="Build or upload a Naru PyPI release.")
    parser.add_argument(
        "action", nargs="?", choices=("build", "upload"), default="build"
    )
    parser.add_argument("version", nargs="?", help="Release version, for example 0.2.2")
    args = parser.parse_args()

    if args.version is None:
        try:
            args.version = input("Release version (e.g. 0.2.2): ").strip()
        except EOFError:
            parser.error("Enter a release version or pass it as an argument.")
    if not args.version:
        parser.error("Release version is required.")

    with (ROOT / "pyproject.toml").open("rb") as config:
        version = tomllib.load(config)["project"]["version"]
    module = runpy.run_path(str(ROOT / "src" / "naru" / "__init__.py"))
    cli_version = module["__version__"]
    if args.version != version or cli_version != version:
        parser.error(
            f"Version mismatch: requested {args.version}, "
            f"pyproject.toml {version}, CLI {cli_version}."
        )

    output = ROOT / "dist" / "manual" / version
    if args.action == "build":
        if output.exists():
            raise SystemExit(f"{output} already exists. Move it before rebuilding.")
        run("ruff", "check", "src", "tests", "scripts")
        run("unittest", "discover", "-s", "tests")
        output.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=output.parent) as temp:
            staging = Path(temp) / "distributions"
            run("build", "--outdir", staging)
            check_distributions(staging, version)
            staging.rename(output)
        print(f"Release files: {output}")
    else:
        files = check_distributions(output, version)
        run(
            "twine",
            "upload",
            "--repository-url",
            "https://upload.pypi.org/legacy/",
            "--username",
            "__token__",
            *files,
        )


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as error:
        raise SystemExit(error.returncode) from None