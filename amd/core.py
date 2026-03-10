from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
from typing import Any

from .templates import render_template

AMD_VERSION = 1
DEFAULT_STALE_AFTER_HOURS = 24
META_MARKER = "<!-- amd:meta"
TIMELINE_START = "<!-- amd:timeline:start -->"
TIMELINE_END = "<!-- amd:timeline:end -->"
HEADING_RE = re.compile(r"^\s*(#{1,6})\s+(.+?)\s*$")
META_RE = re.compile(r"\A<!-- amd:meta\n(?P<meta>.*?)\n-->\n?(?P<body>.*)\Z", re.DOTALL)


@dataclass
class AMDDocument:
    metadata: dict[str, Any]
    body: str


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def isoformat_utc(value: datetime | None = None) -> str:
    value = value or utc_now()
    return value.isoformat().replace("+00:00", "Z")


def parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "artifact"


def artifact_stem(path: Path) -> str:
    name = path.name
    if name.endswith(".amd.md"):
        return name[: -len(".amd.md")]
    return path.stem


def artifact_id_for_path(path: Path) -> str:
    basis = path.as_posix()
    suffix = sha256_text(basis)[:8]
    return f"{slugify(artifact_stem(path))}-{suffix}"


def title_from_path(path: Path) -> str:
    stem = artifact_stem(path)
    return stem.replace("-", " ").replace("_", " ").strip().title() or "Untitled Artifact"


def title_from_body(body: str) -> str | None:
    for line in body.splitlines():
        match = HEADING_RE.match(line)
        if match and len(match.group(1)) == 1:
            return match.group(2).strip()
    return None


def sidecar_path_for(document_path: Path, artifact_id: str) -> Path:
    return document_path.parent / ".amd" / "data" / f"{artifact_id}.jsonl"


def relative_to_document(document_path: Path, target_path: Path) -> str:
    base = document_path.parent.resolve()
    target = target_path.resolve(strict=False)
    return os.path.relpath(target, start=base)


def load_document(path: str | Path) -> AMDDocument:
    path = Path(path)
    text = path.read_text(encoding="utf-8")
    match = META_RE.match(text)
    if not match:
        raise ValueError(f"{path} is not an AMD document")
    metadata = json.loads(match.group("meta"))
    return AMDDocument(metadata=metadata, body=match.group("body"))


def render_document(document: AMDDocument) -> str:
    meta = json.dumps(document.metadata, indent=2, sort_keys=True)
    return f"{META_MARKER}\n{meta}\n-->\n{document.body.rstrip()}\n"


def save_document(path: str | Path, document: AMDDocument) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_document(document), encoding="utf-8")


def sanitize_text(value: str) -> str:
    return " ".join(value.split())


def timeline_event(timestamp: str, agent: str, kind: str, summary: str, details: str | None = None) -> str:
    line = f"- {timestamp} [agent:{sanitize_text(agent)}] [kind:{sanitize_text(kind)}] {sanitize_text(summary)}"
    if details:
        line = f"{line}: {sanitize_text(details)}"
    return line


def append_timeline_event(body: str, entry: str) -> str:
    lines = body.splitlines()
    try:
        end_index = lines.index(TIMELINE_END)
    except ValueError:
        addition = [
            "",
            "## Timeline",
            TIMELINE_START,
            entry,
            TIMELINE_END,
        ]
        return body.rstrip() + "\n" + "\n".join(addition) + "\n"
    lines.insert(end_index, entry)
    return "\n".join(lines).rstrip() + "\n"


def is_timeline_heading(heading: str) -> bool:
    return heading.strip().lower() == "timeline"


def extract_sections(body: str) -> dict[str, dict[str, Any]]:
    sections: dict[str, dict[str, Any]] = {}
    counters: Counter[str] = Counter()
    current_key: str | None = None
    current_lines: list[str] = []
    current_heading = ""
    current_level = 0

    def flush() -> None:
        nonlocal current_key, current_lines, current_heading, current_level
        if not current_key:
            return
        content = "\n".join(current_lines).strip()
        sections[current_key] = {
            "heading": current_heading,
            "level": current_level,
            "line_count": len(current_lines),
            "content": content,
            "fingerprint": sha256_text(content),
        }

    for line in body.splitlines():
        match = HEADING_RE.match(line)
        if match and len(match.group(1)) >= 2:
            flush()
            current_heading = match.group(2).strip()
            current_level = len(match.group(1))
            counters[f"{current_level}:{current_heading}"] += 1
            ordinal = counters[f"{current_level}:{current_heading}"]
            current_key = f"{current_level}:{current_heading}"
            if ordinal > 1:
                current_key = f"{current_key}#{ordinal}"
            current_lines = [line]
            continue
        if current_key is not None:
            current_lines.append(line)

    flush()
    return sections


def summarize_timeseries(path: Path) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "path": str(path),
        "points": 0,
        "latest_at": None,
        "metrics": {},
    }
    if not path.exists():
        return summary

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        if not raw_line.strip():
            continue
        point = json.loads(raw_line)
        summary["points"] += 1
        timestamp = point.get("timestamp")
        metric = point.get("metric")
        if not metric:
            continue
        metric_summary = summary["metrics"].setdefault(
            metric,
            {
                "count": 0,
                "latest_at": None,
                "latest_value": None,
                "unit": point.get("unit"),
                "min_value": None,
                "max_value": None,
            },
        )
        metric_summary["count"] += 1
        metric_summary["unit"] = point.get("unit") or metric_summary["unit"]
        if timestamp and (
            metric_summary["latest_at"] is None
            or parse_timestamp(timestamp) > parse_timestamp(metric_summary["latest_at"])
        ):
            metric_summary["latest_at"] = timestamp
            metric_summary["latest_value"] = point.get("value")
        if timestamp and (
            summary["latest_at"] is None or parse_timestamp(timestamp) > parse_timestamp(summary["latest_at"])
        ):
            summary["latest_at"] = timestamp
        value = point.get("value")
        if isinstance(value, (int, float)):
            metric_summary["min_value"] = value if metric_summary["min_value"] is None else min(metric_summary["min_value"], value)
            metric_summary["max_value"] = value if metric_summary["max_value"] is None else max(metric_summary["max_value"], value)
    return summary


def _default_metadata(
    path: Path,
    title: str,
    kind: str,
    persistence: str,
    stale_after_hours: int,
    manual_priority: int,
    derived_from: list[str] | None = None,
) -> dict[str, Any]:
    artifact_id = artifact_id_for_path(path)
    sidecar_path = sidecar_path_for(path, artifact_id)
    now = isoformat_utc()
    return {
        "agents": {
            "contributors": [],
            "last_actor": None,
        },
        "amd_version": AMD_VERSION,
        "artifact_id": artifact_id,
        "caveats": [],
        "context_refs": derived_from or [],
        "fingerprints": {
            "document": None,
            "sections": {},
        },
        "freshness": {
            "is_stale": False,
            "observed_at": now,
            "stale_after_hours": stale_after_hours,
            "stale_reasons": [],
        },
        "kind": kind,
        "persistence": {
            "expires_after_hours": None,
            "mode": persistence,
        },
        "priority": {
            "computed": manual_priority,
            "manual": manual_priority,
            "reasons": ["manual baseline"],
        },
        "provenance": {
            "derived_from": derived_from or [],
        },
        "status": "active",
        "template": {
            "name": kind,
        },
        "timeseries": {
            "latest_at": None,
            "metrics": {},
            "path": relative_to_document(path, sidecar_path),
            "points": 0,
        },
        "title": title,
        "updated_at": now,
    }


def create_artifact(
    path: str | Path,
    *,
    title: str | None = None,
    kind: str = "task",
    persistence: str = "persistent",
    stale_after_hours: int = DEFAULT_STALE_AFTER_HOURS,
    manual_priority: int = 50,
    agent: str = "system",
    derived_from: list[str] | None = None,
    source_material: dict[str, str] | None = None,
) -> Path:
    path = Path(path)
    title = title or title_from_path(path)
    metadata = _default_metadata(
        path,
        title=title,
        kind=kind,
        persistence=persistence,
        stale_after_hours=stale_after_hours,
        manual_priority=manual_priority,
        derived_from=derived_from,
    )
    derived = derived_from[0] if derived_from else None
    body = render_template(
        title=title,
        kind=kind,
        timeseries_path=metadata["timeseries"]["path"],
        derived_from=derived,
        source_material=source_material,
    )
    save_document(path, AMDDocument(metadata=metadata, body=body))
    refresh_artifact(path, agent=agent, record_changes=False)
    add_event(path, agent=agent, kind="init", summary="artifact initialized")
    return path


def _resolve_timeseries_path(document_path: Path, metadata: dict[str, Any]) -> Path:
    raw_path = metadata.get("timeseries", {}).get("path")
    if not raw_path:
        return sidecar_path_for(document_path, metadata["artifact_id"])
    sidecar = Path(raw_path)
    if sidecar.is_absolute():
        return sidecar
    return document_path.parent.resolve() / sidecar


def _section_stale(updated_at: str | None, stale_after_hours: int, now: datetime) -> bool:
    timestamp = parse_timestamp(updated_at)
    if not timestamp:
        return False
    age_seconds = (now - timestamp).total_seconds()
    return age_seconds > stale_after_hours * 3600


def _active_caveats(caveats: list[dict[str, Any]], now: datetime) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    active: list[dict[str, Any]] = []
    updated: list[dict[str, Any]] = []
    for caveat in caveats:
        item = dict(caveat)
        expires_at = parse_timestamp(item.get("expires_at"))
        status = item.get("status", "active")
        if expires_at and expires_at <= now:
            status = "expired"
        item["status"] = status
        updated.append(item)
        if status == "active":
            active.append(item)
    return active, updated


def refresh_artifact(path: str | Path, *, agent: str = "system", record_changes: bool = True) -> dict[str, Any]:
    path = Path(path)
    document = load_document(path)
    metadata = dict(document.metadata)
    now = utc_now()
    now_iso = isoformat_utc(now)

    initial_sections = extract_sections(document.body)
    old_sections = metadata.get("fingerprints", {}).get("sections", {})
    changed_non_timeline: list[str] = []
    for key, section in initial_sections.items():
        previous_fingerprint = old_sections.get(key, {}).get("fingerprint")
        if previous_fingerprint != section["fingerprint"] and not is_timeline_heading(section["heading"]):
            changed_non_timeline.append(section["heading"])

    if record_changes and changed_non_timeline:
        event = timeline_event(
            now_iso,
            agent=agent,
            kind="fingerprint",
            summary="section fingerprint changed",
            details=", ".join(changed_non_timeline),
        )
        document.body = append_timeline_event(document.body, event)

    sections = extract_sections(document.body)
    observed_at = metadata.get("freshness", {}).get("observed_at")
    if not observed_at or changed_non_timeline:
        observed_at = now_iso

    section_state: dict[str, dict[str, Any]] = {}
    stale_sections: list[str] = []
    default_stale_after = metadata.get("freshness", {}).get("stale_after_hours", DEFAULT_STALE_AFTER_HOURS)
    for key, section in sections.items():
        previous = old_sections.get(key, {})
        fingerprint_changed = previous.get("fingerprint") != section["fingerprint"]
        updated_at = previous.get("updated_at", observed_at)
        if fingerprint_changed:
            updated_at = now_iso
        stale_after_hours = int(previous.get("stale_after_hours", default_stale_after))
        stale = _section_stale(updated_at, stale_after_hours, now)
        if is_timeline_heading(section["heading"]):
            stale = False
        if stale:
            stale_sections.append(section["heading"])
        section_state[key] = {
            "fingerprint": section["fingerprint"],
            "heading": section["heading"],
            "level": section["level"],
            "line_count": section["line_count"],
            "stale": stale,
            "stale_after_hours": stale_after_hours,
            "updated_at": updated_at,
        }

    active_caveats, caveats = _active_caveats(metadata.get("caveats", []), now)
    timeseries_path = _resolve_timeseries_path(path, metadata)
    timeseries_summary = summarize_timeseries(timeseries_path)

    reasons: list[str] = []
    computed_priority = int(metadata.get("priority", {}).get("manual", 50))
    if stale_sections:
        computed_priority += min(20, 5 * len(stale_sections))
        reasons.append(f"stale sections: {', '.join(stale_sections)}")
    if active_caveats:
        computed_priority += min(20, 5 * len(active_caveats))
        reasons.append(f"active caveats: {len(active_caveats)}")
    latest_signal = parse_timestamp(timeseries_summary.get("latest_at"))
    if latest_signal and parse_timestamp(observed_at) and latest_signal > parse_timestamp(observed_at):
        computed_priority += 15
        reasons.append("newer timeseries data exists")
    computed_priority = max(0, min(100, computed_priority))

    title = title_from_body(document.body) or metadata.get("title") or title_from_path(path)
    status = "stale" if stale_sections else "active"

    contributors = list(metadata.get("agents", {}).get("contributors", []))
    if agent and agent not in contributors:
        contributors.append(agent)

    metadata.update(
        {
            "agents": {
                "contributors": contributors,
                "last_actor": agent,
            },
            "caveats": caveats,
            "fingerprints": {
                "document": sha256_text(document.body),
                "sections": section_state,
            },
            "freshness": {
                "is_stale": bool(stale_sections),
                "observed_at": observed_at,
                "stale_after_hours": default_stale_after,
                "stale_reasons": stale_sections,
            },
            "priority": {
                "computed": computed_priority,
                "manual": int(metadata.get("priority", {}).get("manual", 50)),
                "reasons": reasons or ["manual baseline"],
            },
            "status": status,
            "timeseries": {
                "latest_at": timeseries_summary["latest_at"],
                "metrics": timeseries_summary["metrics"],
                "path": relative_to_document(path, timeseries_path),
                "points": timeseries_summary["points"],
            },
            "title": title,
            "updated_at": now_iso,
        }
    )

    save_document(path, AMDDocument(metadata=metadata, body=document.body))
    return {
        "changed_sections": changed_non_timeline,
        "path": str(path),
        "priority": metadata["priority"]["computed"],
        "stale": metadata["freshness"]["is_stale"],
        "title": title,
    }


def add_event(
    path: str | Path,
    *,
    agent: str,
    kind: str,
    summary: str,
    details: str | None = None,
) -> None:
    path = Path(path)
    document = load_document(path)
    entry = timeline_event(isoformat_utc(), agent=agent, kind=kind, summary=summary, details=details)
    document.body = append_timeline_event(document.body, entry)
    save_document(path, document)
    refresh_artifact(path, agent=agent, record_changes=True)


def add_caveat(
    path: str | Path,
    *,
    text: str,
    severity: str = "medium",
    agent: str = "system",
    expires_at: str | None = None,
) -> None:
    path = Path(path)
    document = load_document(path)
    caveat = {
        "created_at": isoformat_utc(),
        "created_by": agent,
        "expires_at": expires_at,
        "severity": severity,
        "status": "active",
        "text": text.strip(),
    }
    document.metadata.setdefault("caveats", []).append(caveat)
    save_document(path, document)
    add_event(
        path,
        agent=agent,
        kind="caveat",
        summary=f"caveat added ({severity})",
        details=text,
    )


def parse_scalar(value: str) -> Any:
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


def add_signal(
    path: str | Path,
    *,
    metric: str,
    value: Any,
    agent: str = "system",
    timestamp: str | None = None,
    unit: str | None = None,
) -> None:
    path = Path(path)
    document = load_document(path)
    sidecar_path = _resolve_timeseries_path(path, document.metadata)
    sidecar_path.parent.mkdir(parents=True, exist_ok=True)
    point = {
        "agent": agent,
        "metric": metric,
        "timestamp": timestamp or isoformat_utc(),
        "unit": unit,
        "value": value,
    }
    with sidecar_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(point, sort_keys=True) + "\n")
    add_event(
        path,
        agent=agent,
        kind="signal",
        summary=f"signal recorded for {metric}",
        details=f"value={value}",
    )


def set_manual_priority(path: str | Path, *, value: int, agent: str = "system") -> None:
    path = Path(path)
    document = load_document(path)
    document.metadata.setdefault("priority", {})["manual"] = int(value)
    save_document(path, document)
    add_event(path, agent=agent, kind="priority", summary=f"manual priority set to {value}")


def _find_section_content(body: str, heading: str) -> str:
    target = heading.strip().lower()
    for section in extract_sections(body).values():
        if section["heading"].strip().lower() != target:
            continue
        lines = section["content"].splitlines()
        if lines:
            lines = lines[1:]
        return "\n".join(lines).strip()
    return ""


def derive_skill_artifact(
    source_path: str | Path,
    output_path: str | Path,
    *,
    title: str | None = None,
    agent: str = "system",
) -> Path:
    source_path = Path(source_path)
    output_path = Path(output_path)
    source_document = load_document(source_path)
    source_material = {
        "Core Concepts": _find_section_content(source_document.body, "Core Concepts"),
        "Decision Rules": _find_section_content(source_document.body, "Decision Rules"),
        "Failure Modes": _find_section_content(source_document.body, "Failure Modes"),
    }
    title = title or f"{source_document.metadata.get('title', title_from_path(source_path))} Skill"
    create_artifact(
        output_path,
        title=title,
        kind="skill-derived",
        persistence=source_document.metadata.get("persistence", {}).get("mode", "persistent"),
        stale_after_hours=source_document.metadata.get("freshness", {}).get("stale_after_hours", DEFAULT_STALE_AFTER_HOURS),
        manual_priority=source_document.metadata.get("priority", {}).get("manual", 50),
        agent=agent,
        derived_from=[str(source_path)],
        source_material=source_material,
    )
    derived_document = load_document(output_path)
    derived_document.metadata["caveats"] = list(source_document.metadata.get("caveats", []))
    save_document(output_path, derived_document)
    refresh_artifact(output_path, agent=agent, record_changes=False)
    add_event(
        output_path,
        agent=agent,
        kind="derive",
        summary="skill artifact derived from source mental model",
        details=str(source_path),
    )
    return output_path


def scan_artifact(path: str | Path) -> dict[str, Any]:
    path = Path(path)
    document = load_document(path)
    metadata = document.metadata
    active_caveats = [item for item in metadata.get("caveats", []) if item.get("status") == "active"]
    return {
        "path": str(path),
        "title": metadata.get("title"),
        "kind": metadata.get("kind"),
        "status": metadata.get("status"),
        "persistence": metadata.get("persistence", {}).get("mode"),
        "priority": metadata.get("priority", {}).get("computed"),
        "priority_reasons": metadata.get("priority", {}).get("reasons", []),
        "stale": metadata.get("freshness", {}).get("is_stale"),
        "stale_reasons": metadata.get("freshness", {}).get("stale_reasons", []),
        "active_caveats": active_caveats,
        "timeseries_points": metadata.get("timeseries", {}).get("points", 0),
        "timeseries_latest_at": metadata.get("timeseries", {}).get("latest_at"),
        "contributors": metadata.get("agents", {}).get("contributors", []),
    }


def iter_artifacts(root: str | Path) -> list[Path]:
    root = Path(root)
    if root.is_file():
        return [root]
    return sorted(root.rglob("*.amd.md"))


def refresh_tree(root: str | Path, *, agent: str = "system") -> list[dict[str, Any]]:
    results = []
    for path in iter_artifacts(root):
        results.append(refresh_artifact(path, agent=agent, record_changes=True))
    return results
