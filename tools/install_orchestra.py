"""Install or package the skill without including runtime records."""
from datetime import datetime, timezone
import hashlib
from pathlib import Path, PurePosixPath
import shutil
import uuid
import zipfile

FILES = (
    "SKILL.md", "agents/openai.yaml", "scripts/native.py", "scripts/policy.py",
    "scripts/state.py", "scripts/orchestra.py", "references/routing.md",
    "references/workflow.md", "references/commands.md", "references/native-compatibility.md",
    "scripts/catalog.py", "scripts/update_check.py", "release.json",
)


def manifest(source):
    result = {}
    for name in FILES:
        path = source / name
        if not path.is_file() or path.is_symlink() or not path.resolve().is_relative_to(source.resolve()):
            raise ValueError("Missing or unsafe package member: " + name)
        result[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def install(source, target):
    expected = manifest(source)
    if target.is_symlink():
        raise ValueError("Refuse a symlink installation target")
    target.parent.mkdir(parents=True, exist_ok=True)
    backup = None
    if target.exists():
        if not target.is_dir():
            raise ValueError("Installation target is not a directory")
        backup = target.with_name(target.name + ".backup-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:8])
        target.rename(backup)
    target.mkdir()
    for name in FILES:
        destination = target / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source / name, destination)
    if manifest(target) != expected:
        raise ValueError("Installation hash mismatch; previous files retained in backup")
    return backup


def validate_zip(archive):
    with zipfile.ZipFile(archive) as bundle:
        if bundle.testzip() is not None:
            raise ValueError("Archive CRC failure")
        names = bundle.namelist()
        for name in names:
            path = PurePosixPath(name)
            if path.is_absolute() or ".." in path.parts or "\\" in name or path.parts[:1] != ("orchestra",):
                raise ValueError("Unsafe archive path")
        if set(names) != {"orchestra/" + name for name in FILES} or len(names) != len(FILES):
            raise ValueError("Unexpected or duplicate package contents")


def build_zip(source, archive):
    expected = manifest(source)
    archive.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        for name in FILES:
            bundle.write(source / name, "orchestra/" + name)
    validate_zip(archive)
    with zipfile.ZipFile(archive) as bundle:
        if any(hashlib.sha256(bundle.read("orchestra/" + name)).hexdigest() != digest for name, digest in expected.items()):
            raise ValueError("Archive hash mismatch")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Install Orchestra, preserving an existing skill in a backup folder")
    parser.add_argument("--target", type=Path, default=Path.home() / ".agents/skills/orchestra")
    parser.add_argument("--zip", dest="archive", type=Path, help="Build a ZIP instead of installing")
    args = parser.parse_args()
    source = Path(__file__).resolve().parents[1] / "orchestra"
    if args.archive:
        build_zip(source, args.archive)
        print("Created:", args.archive)
    else:
        backup = install(source, args.target)
        print("Installed:", args.target)
        if backup:
            print("Previous installation preserved:", backup)
