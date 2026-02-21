from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


def _now_ts() -> float:
    return time.time()


def normalize_template_id(template_id: str) -> str:
    candidate = str(template_id).strip().lower()
    if not candidate:
        raise ValueError("template_id must be a non-empty string.")
    for ch in candidate:
        if ch.isalnum() or ch in {"-", "_"}:
            continue
        raise ValueError("template_id may only contain letters, numbers, '-' or '_'.")
    return candidate


def base_origin_for_url(url: str) -> str:
    parsed = urlparse(str(url).strip())
    if not parsed.scheme or not parsed.netloc:
        raise ValueError("url must be absolute (scheme://host/...)")
    return f"{parsed.scheme}://{parsed.netloc}"


def structured_flows_base_dir() -> Path:
    base = Path(os.path.expanduser("~/.gsd/structured_flows"))
    base.mkdir(parents=True, exist_ok=True)
    return base


def template_dir(template_id: str) -> Path:
    normalized = normalize_template_id(template_id)
    path = structured_flows_base_dir() / normalized
    path.mkdir(parents=True, exist_ok=True)
    return path


def template_manifest_path(template_id: str) -> Path:
    return template_dir(template_id) / "manifest.json"


def template_script_path(template_id: str) -> Path:
    return template_dir(template_id) / "replay.py"


def template_dsl_path(template_id: str) -> Path:
    return template_dir(template_id) / "fallback.dsl.json"


def template_recordings_dir(template_id: str) -> Path:
    path = template_dir(template_id) / "recordings"
    path.mkdir(parents=True, exist_ok=True)
    return path


def sha256_hex(text: str) -> str:
    digest = sha256()
    digest.update(text.encode("utf-8"))
    return digest.hexdigest()


@dataclass(frozen=True)
class TemplateManifest:
    template_id: str
    template_name: str | None
    base_origin: str
    created_at: float
    updated_at: float
    recorded_example_url: str | None
    script_path: str
    dsl_path: str | None
    manifest_path: str
    sha256: str
    uses_llm_at_replay: bool

    @classmethod
    def from_json(cls, payload: dict[str, Any]) -> TemplateManifest:
        return cls(
            template_id=str(payload["template_id"]),
            template_name=(
                str(payload["template_name"]) if payload.get("template_name") else None
            ),
            base_origin=str(payload["base_origin"]),
            created_at=float(payload["created_at"]),
            updated_at=float(payload["updated_at"]),
            recorded_example_url=(
                str(payload["recorded_example_url"])
                if payload.get("recorded_example_url")
                else None
            ),
            script_path=str(payload["script_path"]),
            dsl_path=str(payload["dsl_path"]) if payload.get("dsl_path") else None,
            manifest_path=str(payload["manifest_path"]),
            sha256=str(payload["sha256"]),
            uses_llm_at_replay=bool(payload.get("uses_llm_at_replay", False)),
        )

    def to_json(self) -> dict[str, Any]:
        return {
            "version": "gsd.structured_flow.template.v1",
            "template_id": self.template_id,
            "template_name": self.template_name,
            "base_origin": self.base_origin,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "recorded_example_url": self.recorded_example_url,
            "script_path": self.script_path,
            "dsl_path": self.dsl_path,
            "manifest_path": self.manifest_path,
            "sha256": self.sha256,
            "uses_llm_at_replay": self.uses_llm_at_replay,
        }


def load_manifest(template_id: str) -> TemplateManifest:
    path = template_manifest_path(template_id)
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("manifest.json must be an object")
    return TemplateManifest.from_json(data)


def save_manifest(manifest: TemplateManifest) -> None:
    path = template_manifest_path(manifest.template_id)
    path.write_text(
        json.dumps(manifest.to_json(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def save_template_files(
    *,
    template_id: str,
    template_name: str | None,
    base_origin: str,
    recorded_example_url: str | None,
    script_content: str,
    uses_llm_at_replay: bool,
    dsl_payload: dict[str, Any] | None,
) -> TemplateManifest:
    normalized = normalize_template_id(template_id)
    template_dir(normalized)

    script_path = template_script_path(normalized)
    script_path.write_text(script_content, encoding="utf-8")

    dsl_path: str | None = None
    if dsl_payload is not None:
        dsl_file = template_dsl_path(normalized)
        dsl_file.write_text(
            json.dumps(dsl_payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        dsl_path = str(dsl_file)

    manifest_path = template_manifest_path(normalized)
    created_at: float
    if manifest_path.exists():
        try:
            existing = load_manifest(normalized)
            created_at = existing.created_at
        except Exception:
            created_at = _now_ts()
    else:
        created_at = _now_ts()

    updated_at = _now_ts()
    manifest = TemplateManifest(
        template_id=normalized,
        template_name=template_name,
        base_origin=base_origin,
        created_at=created_at,
        updated_at=updated_at,
        recorded_example_url=recorded_example_url,
        script_path=str(script_path),
        dsl_path=dsl_path,
        manifest_path=str(manifest_path),
        sha256=sha256_hex(script_content),
        uses_llm_at_replay=uses_llm_at_replay,
    )
    save_manifest(manifest)
    return manifest
