"""Edit manifest validation: JSON Schema plus the semantic rules JSON Schema can't express.

Rules come from QUALITY_BAR.md and SECURITY_PRIVACY.md:
- every item has 0 <= start < end
- video items reference this project's media and stay inside the source duration
- video items on a track do not overlap
- editorial captions cite existing transcript segments (grounding)
- visual items reference a media/asset id and a known layout
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from functools import lru_cache
from pathlib import Path
from typing import Any

import jsonschema

SCHEMA_FILENAME = "EDIT_MANIFEST.schema.json"


class SchemaNotFoundError(RuntimeError):
    pass


def _candidate_paths() -> list[Path]:
    from app.config import settings

    here = Path(__file__).resolve()
    # backend/app/domain/manifest_rules.py -> backend/ is parents[2], repo root parents[3]
    found = [here.parents[2] / SCHEMA_FILENAME, here.parents[3] / SCHEMA_FILENAME]
    if settings.manifest_schema_path:
        return [Path(settings.manifest_schema_path)]  # explicit config wins, no fallback
    return found


@lru_cache
def load_schema() -> dict[str, Any]:
    """Load the canonical schema. A missing or unreadable schema is an error, never a skip."""
    for path in _candidate_paths():
        if not path.is_file():
            continue
        try:
            schema = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise SchemaNotFoundError(f"{path} is not a readable JSON schema") from exc
        if not isinstance(schema, dict) or "$schema" not in schema:
            raise SchemaNotFoundError(f"{path} does not look like a JSON schema")
        return schema
    raise SchemaNotFoundError(f"{SCHEMA_FILENAME} not found (set MANIFEST_SCHEMA_PATH).")


def validate_schema(manifest: Mapping[str, Any]) -> list[str]:
    validator = jsonschema.Draft202012Validator(load_schema())
    errors = []
    for err in sorted(validator.iter_errors(dict(manifest)), key=lambda e: list(e.absolute_path)):
        path = ".".join(str(p) for p in err.absolute_path) or "(root)"
        errors.append(f"{path}: {err.message}")
    return errors


def validate_semantics(
    manifest: Mapping[str, Any],
    *,
    project_id: str,
    media_durations: Mapping[str, float],
    segment_ids: set[str],
) -> list[str]:
    """Return human-readable semantic errors. Empty list means valid."""
    errors: list[str] = []
    if manifest.get("project_id") != project_id:
        errors.append("project_id: does not match the project in the URL")

    for t_index, track in enumerate(manifest.get("tracks", [])):
        ttype = track.get("type")
        where = f"tracks[{t_index}]({ttype})"
        spans: list[tuple[str, float, float, int]] = []

        for i_index, item in enumerate(track.get("items", [])):
            loc = f"{where}.items[{i_index}]"
            start, end = item.get("start"), item.get("end")
            if not isinstance(start, int | float) or not isinstance(end, int | float):
                continue  # the schema validation already reported this
            if start < 0 or end <= start:
                errors.append(f"{loc}: needs 0 <= start < end (got {start}, {end})")
                continue

            if ttype == "video":
                media_id = item.get("source_media_id")
                if media_id not in media_durations:
                    errors.append(
                        f"{loc}: source_media_id is not a ready media asset of this project"
                    )
                elif end > media_durations[media_id] + 0.05:
                    dur = media_durations[media_id]
                    errors.append(f"{loc}: end {end} is past the source duration {dur:.2f}")
                spans.append((str(media_id), float(start), float(end), i_index))

            if ttype == "editorial_caption":
                cited = item.get("source_segment_ids") or []
                if not cited:
                    errors.append(f"{loc}: editorial captions must cite source_segment_ids")
                unknown = [s for s in cited if s not in segment_ids]
                if unknown:
                    errors.append(f"{loc}: cites unknown transcript segment ids")
                if not (item.get("text") or "").strip():
                    errors.append(f"{loc}: editorial caption text is empty")

            if ttype == "visual":
                if not item.get("asset_id") and not item.get("source_media_id"):
                    errors.append(f"{loc}: visual items need an asset_id or source_media_id")
                if not item.get("layout"):
                    errors.append(f"{loc}: visual items need a layout")

        spans.sort()
        for (m1, _s1, e1, i1), (m2, s2, _e2, i2) in zip(spans, spans[1:], strict=False):
            # Items are ranges of the source; ranges of the same source must not overlap.
            if m1 == m2 and s2 < e1 - 1e-6:
                errors.append(f"{where}: items[{i1}] and items[{i2}] overlap")
    return errors
