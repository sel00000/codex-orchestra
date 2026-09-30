"""Read the upstream release number; never download or install executable code."""
import json
from pathlib import Path
import re
from urllib.error import URLError
from urllib.request import Request, urlopen

REPOSITORY = "https://github.com/sel00000/codex-orchestra"
RELEASE_URL = "https://raw.githubusercontent.com/sel00000/codex-orchestra/main/orchestra/release.json"


def version_parts(value):
    if not isinstance(value, str) or re.fullmatch(r"\d+\.\d+\.\d+", value) is None:
        raise ValueError("RELEASE_VERSION_INVALID")
    return tuple(int(part) for part in value.split("."))


def check_update(release_path=None):
    release_path = release_path or Path(__file__).resolve().parents[1] / "release.json"
    result = {"status": "unverified", "installed_version": None, "latest_version": None,
              "repository": REPOSITORY, "source": RELEASE_URL, "automatic_install": False}
    try:
        local = json.loads(release_path.read_text(encoding="utf-8"))
        if not isinstance(local, dict) or local.get("schema_version") != 1:
            raise ValueError("RELEASE_SCHEMA_INVALID")
        installed = version_parts(local.get("version"))
        result["installed_version"] = local["version"]
        request = Request(RELEASE_URL, headers={"Accept": "application/json", "User-Agent": "Orchestra-update-check"})
        with urlopen(request, timeout=4) as response:
            body = response.read(8193)
        if len(body) > 8192:
            raise ValueError("RELEASE_RESPONSE_TOO_LARGE")
        remote = json.loads(body)
        if not isinstance(remote, dict) or remote.get("schema_version") != 1:
            raise ValueError("RELEASE_SCHEMA_INVALID")
        latest = version_parts(remote.get("version"))
        result["latest_version"] = remote["version"]
        result["status"] = "update_available" if latest > installed else "up_to_date" if latest == installed else "local_ahead"
    except (OSError, URLError, ValueError, TypeError) as error:
        result["diagnostic"] = type(error).__name__
    return result
