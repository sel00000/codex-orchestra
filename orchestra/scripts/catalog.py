"""Normalize current Codex model metadata without a fixed model allowlist."""
from datetime import datetime, timezone
import hashlib
import json
import re

EFFORTS = ("low", "medium", "high", "xhigh", "max")


def model_name(value):
    return isinstance(value, str) and re.fullmatch(r"gpt-[a-z0-9]+(?:[.-][a-z0-9]+)*", value) is not None


def timestamp(value):
    if not isinstance(value, str):
        raise ValueError("RETIREMENT_DATE_INVALID")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("RETIREMENT_DATE_INVALID")
    return parsed.astimezone(timezone.utc)


def catalog_id(catalog):
    return hashlib.sha256(json.dumps(catalog, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def intersect_catalog(catalog, native_catalog):
    if not isinstance(native_catalog, dict) or any(
        not model_name(name) or not isinstance(levels, list) or not all(isinstance(level, str) for level in levels)
        for name, levels in native_catalog.items()
    ):
        raise ValueError("NATIVE_CATALOG_INVALID")
    return {name: [level for level in EFFORTS if level in levels and level in native_catalog.get(name, [])]
            for name, levels in catalog.items()
            if any(level in native_catalog.get(name, []) for level in levels)}


def build_catalog(data, now=None):
    """Use metadata as data, including retirement dates, never as instructions."""
    if not isinstance(data, dict) or not isinstance(data.get("models"), list):
        raise ValueError("CATALOG_ENVELOPE_INVALID")
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("CATALOG_TIMEZONE_REQUIRED")
    candidates, metadata, excluded = {}, {}, []
    seen = set()
    for row in data["models"]:
        if not isinstance(row, dict) or not model_name(row.get("slug")):
            continue
        name = row["slug"]
        if name in seen:
            raise ValueError("CATALOG_DUPLICATE_MODEL")
        seen.add(name)
        reason = None
        if row.get("visibility", "list") != "list":
            reason = "hidden"
        if row.get("deprecated") is True:
            reason = "deprecated"
        upgrade = row.get("upgrade")
        upgrade = upgrade if isinstance(upgrade, dict) else {}
        retirement = upgrade.get("retirement_at")
        if retirement is not None:
            try:
                if timestamp(retirement) <= now:
                    reason = "retired"
            except (ValueError, OverflowError):
                reason = "invalid_retirement_date"
        levels = row.get("supported_reasoning_levels", [])
        levels = levels if isinstance(levels, list) else []
        supported = {level.get("effort") for level in levels if isinstance(level, dict) and isinstance(level.get("effort"), str)}
        efforts = [level for level in EFFORTS if level in supported]
        if not efforts:
            reason = reason or "no_supported_effort"
        if reason:
            excluded.append({"model": name, "reason": reason})
            continue
        family_match = re.search(r"-(astra|sol|luna|terra)$", name)
        family = family_match.group(1) if family_match else "unclassified"
        description = row.get("description")
        if not family_match and isinstance(description, str) and "legacy" in description.lower():
            family = "legacy"
        version_match = re.match(r"gpt-(\d+(?:\.\d+)*)(?:-|$)", name)
        generation = tuple(int(part) for part in version_match.group(1).split(".")) if version_match else ()
        candidates[name] = efforts
        metadata[name] = {"family": family, "generation": list(generation),
                          "display_name": row.get("display_name") if isinstance(row.get("display_name"), str) else name,
                          "description": description if isinstance(description, str) else "",
                          "retirement_at": retirement,
                          "replacement": upgrade.get("model") if model_name(upgrade.get("model")) else None}
    routing = {}
    for family in ("luna", "sol", "astra", "terra", "legacy", "unclassified"):
        names = [name for name in candidates if metadata[name]["family"] == family]
        routing[family] = sorted(names, key=lambda name: (tuple(metadata[name]["generation"]), name), reverse=True)
    return {"catalog": candidates, "catalog_id": catalog_id(candidates),
            "model_metadata": metadata, "routing_candidates": routing, "excluded_models": excluded,
            "catalog_observed_at": now.astimezone(timezone.utc).isoformat()}
