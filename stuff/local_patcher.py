"""Force a local launcher installation to use the current local source.

Builds the launcher from this repository and replaces a local executable with
the result. The existing executable is backed up before replacement.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


APP_EXE_NAME = "WizQLauncher.exe"


def project_root() -> Path:
	"""Return the repository root containing ``build.py``."""
	root = Path(__file__).resolve().parents[1]
	if not (root / "build.py").is_file():
		raise RuntimeError(f"Could not find project root from {__file__}")
	return root


def build_local_executable(root: Path) -> Path:
	"""Build the executable from the local source tree."""
	print(f"Building local source from {root}")
	subprocess.run(
		[sys.executable, "build.py"],
		cwd=root,
		check=True,
	)
	artifact = root / "dist" / APP_EXE_NAME
	if not artifact.is_file():
		raise FileNotFoundError(f"Build completed without creating {artifact}")
	return artifact


def replace_executable(source: Path, target: Path, keep_backup: bool = True) -> Path | None:
	"""Atomically replace *target* with *source* and optionally keep a backup."""
	target = target.resolve()
	source = source.resolve()
	target.parent.mkdir(parents=True, exist_ok=True)

	if source == target:
		print(f"Target already points to build artifact: {target}")
		return None

	backup = target.with_suffix(target.suffix + ".bak")
	if target.exists() and keep_backup:
		shutil.copy2(target, backup)

	fd, temporary_name = tempfile.mkstemp(
		prefix=f".{target.stem}-",
		suffix=target.suffix,
		dir=target.parent,
	)
	os.close(fd)
	temporary = Path(temporary_name)
	try:
		shutil.copy2(source, temporary)
		os.replace(temporary, target)
	except PermissionError as exc:
		raise PermissionError(
			f"Could not replace {target}. Close the running launcher first."
		) from exc
	finally:
		temporary.unlink(missing_ok=True)

	return backup if keep_backup and backup.exists() else None


def parse_args() -> argparse.Namespace:
	parser = argparse.ArgumentParser(
		description="Build the local source and force-update a local WizQLauncher.exe."
	)
	parser.add_argument(
		"--target",
		type=Path,
		help="Executable to replace (default: project root/WizQLauncher.exe).",
	)
	parser.add_argument(
		"--no-build",
		action="store_true",
		help="Use the existing dist/WizQLauncher.exe instead of building.",
	)
	parser.add_argument(
		"--no-backup",
		action="store_true",
		help="Do not keep a .bak copy of the previous executable.",
	)
	parser.add_argument(
		"--dry-run",
		action="store_true",
		help="Show the planned source and target without changing files.",
	)
	return parser.parse_args()


def main() -> int:
	args = parse_args()
	root = project_root()
	artifact = root / "dist" / APP_EXE_NAME
	target = (args.target or root / APP_EXE_NAME).expanduser()
	if not target.is_absolute():
		target = root / target

	print(f"Source: {root}")
	print(f"Target: {target.resolve()}")

	if args.dry_run:
		print("Dry run: no files changed.")
		return 0

	if not args.no_build:
		artifact = build_local_executable(root)
	if not artifact.is_file():
		raise FileNotFoundError(f"Local build artifact not found: {artifact}")

	backup = replace_executable(artifact, target, keep_backup=not args.no_backup)
	print(f"Local launcher updated: {target.resolve()}")
	if backup:
		print(f"Backup created: {backup}")
	return 0


if __name__ == "__main__":
	try:
		raise SystemExit(main())
	except (FileNotFoundError, PermissionError, RuntimeError, subprocess.CalledProcessError) as exc:
		print(f"ERROR: {exc}", file=sys.stderr)
		raise SystemExit(1) from exc