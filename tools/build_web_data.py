#!/usr/bin/env python3
"""Build lazy-loadable static indexes and assets from VanGioi_Full_Pack.zip."""
import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
import zipfile
import zlib
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / "tools"))
from make_pack import ATLAS as LEGACY_ATLAS, RawZip, fix_png, tex_path

ATLAS_PATHS = (
    LEGACY_ATLAS,
    "assets/" + LEGACY_ATLAS,
    "ia_overlay_modern_atlas/assets/minecraft/atlases/blocks.json",
    "assets/ia_overlay_modern_atlas/assets/minecraft/atlases/blocks.json",
    "ia_overlay_modern_atlas/assets/minecraft/atlases/items.json",
    "assets/ia_overlay_modern_atlas/assets/minecraft/atlases/items.json",
)
AUDIO_EXTS = (".ogg", ".wav", ".mp3", ".flac", ".opus")
MODEL_RE = re.compile(r"^assets/modelengine/models/([^/]+)/(.+)\.json$", re.I)
ITEM_RE = re.compile(r"^assets/modelengine/items/([^/]+)/(.+)\.json$", re.I)


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, separators=(",", ":"))


def safe_id(value):
    if value in (".", "..") or not re.fullmatch(r"[a-zA-Z0-9_.-]+", value):
        raise ValueError("ID không an toàn để tạo đường dẫn: " + value)
    return value


def sound_target(registry, raw):
    if not isinstance(raw, str) or not raw:
        return None
    default_ns = registry[len("assets/"):-len("/sounds.json")]
    namespace, resource = raw.split(":", 1) if ":" in raw else (default_ns, raw)
    if not re.fullmatch(r"[a-zA-Z0-9_.-]+", namespace):
        return None
    if resource.startswith("/") or ".." in Path(resource).parts:
        return None
    if Path(resource).suffix.lower() in AUDIO_EXTS:
        return "assets/{}/sounds/{}".format(namespace, resource)
    return "assets/{}/sounds/{}".format(namespace, resource) + ".ogg"


def atomic_publish(staging, output):
    backup = output.with_name(output.name + ".previous")
    if backup.exists():
        raise RuntimeError("Thư mục backup đã tồn tại; không ghi đè: " + str(backup))
    if output.exists():
        marker = output / "manifest.json"
        if not marker.is_file():
            raise RuntimeError("Output đã tồn tại nhưng không có manifest do generator tạo: " + str(output))
        previous = json.loads(marker.read_text(encoding="utf-8"))
        if previous.get("generator") != "tools/build_web_data.py":
            raise RuntimeError("Không thay thế output không thuộc generator: " + str(output))
        os.replace(output, backup)
    try:
        os.replace(staging, output)
    except Exception:
        if backup.exists() and not output.exists():
            os.replace(backup, output)
        raise
    if backup.exists():
        shutil.rmtree(backup)


def build(source, output):
    source = source.resolve()
    output = output.resolve()
    if not source.is_file():
        raise FileNotFoundError("Không tìm thấy ZIP nguồn: " + str(source))
    if output == ROOT or output in source.parents or source in output.parents:
        raise ValueError("Đường dẫn output không an toàn hoặc chứa ZIP nguồn")

    source_hash = sha256_file(source)
    raw = RawZip(str(source))
    output.parent.mkdir(parents=True, exist_ok=True)
    existing_names = {}
    old_names_path = output / "names.json"
    if old_names_path.is_file():
        try:
            previous = json.loads(old_names_path.read_text(encoding="utf-8"))
            if previous.get("schemaVersion") == 1:
                existing_names = previous
        except Exception as error:
            raise ValueError("Không đọc được names.json đang có; giữ nguyên output: {}".format(error)) from error
    names = sorted(raw.info)
    for name in names:
        if name.startswith("/") or "\\" in name or any(part in ("", ".", "..") for part in name.split("/")):
            raise ValueError("Đường dẫn member ZIP không an toàn: " + name)
    model_files, item_files = defaultdict(list), defaultdict(list)
    sound_files, sound_registries = [], []
    for name in names:
        match = MODEL_RE.match(name)
        if match:
            model_files[safe_id(match.group(1))].append((name, match.group(2)))
            continue
        match = ITEM_RE.match(name)
        if match:
            item_files[safe_id(match.group(1))].append((name, match.group(2)))
            continue
        if name.lower().endswith(AUDIO_EXTS):
            sound_files.append(name)
        if name.startswith("assets/") and name.endswith("/sounds.json"):
            sound_registries.append(name)

    atlas_map = {}
    for atlas_path in ATLAS_PATHS:
        if atlas_path not in raw:
            continue
        try:
            atlas = json.loads(raw.read(atlas_path).decode("utf-8-sig"))
            for entry in atlas.get("sources", []):
                if isinstance(entry, dict) and isinstance(entry.get("sprite"), str) and isinstance(entry.get("resource"), str):
                    atlas_map.setdefault(entry["sprite"], entry["resource"])
        except Exception as error:
            raise ValueError("Không đọc được atlas {}: {}".format(atlas_path, error)) from error

    staging = Path(tempfile.mkdtemp(prefix=".web-data-build-", dir=str(output.parent)))
    source_checks = {}
    def read_source(name):
        data = raw.read(name)
        if name not in source_checks:
            info = raw.info[name]
            source_checks[name] = {
                "bytes": len(data),
                "sizeMismatch": len(data) != info.file_size,
                "crcMismatch": (zlib.crc32(data) & 0xFFFFFFFF) != info.CRC,
            }
        return data

    owned, resource_names = set(), set()
    model_index, model_ids = [], set(model_files)
    item_index, missing_item_models = [], []
    model_sizes = {}
    model_id_stats = {}
    unresolved_textures = set()

    try:
        model_dir = staging / "models"
        for model_id in sorted(model_files):
            parts, resources, model_bytes = [], set(), 0
            for path, part_name in sorted(model_files[model_id]):
                try:
                    data = read_source(path)
                    parsed = json.loads(data.decode("utf-8-sig"))
                except Exception as error:
                    raise ValueError("Model JSON lỗi {}: {}".format(path, error)) from error
                if not isinstance(parsed, dict):
                    raise ValueError("Model JSON không phải object: " + path)
                for value in (parsed.get("textures") or {}).values():
                    if not isinstance(value, str) or value.startswith("#"):
                        continue
                    if value.startswith("ia:"):
                        value = atlas_map.get(value)
                        if not value:
                            unresolved_textures.add(path)
                            continue
                    resources.add(value)
                model_bytes += len(data)
                parts.append({"name": part_name, "path": path, "json": parsed})
                owned.add(path)
            model_sizes[model_id] = {"parts": len(parts), "bytes": model_bytes, "resources": sorted(resources)}
            model_id_stats[model_id] = {"parts": parts, "resources": resources}
            write_json(model_dir / (model_id + ".json"), {"id": model_id, "parts": parts})

        for item_id in sorted(item_files):
            records, exact_matches = [], 0
            for path, part_name in sorted(item_files[item_id]):
                try:
                    data = read_source(path)
                    parsed = json.loads(data.decode("utf-8-sig"))
                except Exception as error:
                    raise ValueError("Item JSON lỗi {}: {}".format(path, error)) from error
                if not isinstance(parsed, dict):
                    raise ValueError("Item JSON không phải object: " + path)
                ref = ((parsed.get("model") or {}).get("model")
                       if isinstance(parsed.get("model"), dict) else None)
                target = None
                if isinstance(ref, str) and ":" in ref:
                    namespace, resource = ref.split(":", 1)
                    if re.fullmatch(r"[a-zA-Z0-9_.-]+", namespace) and ".." not in Path(resource).parts:
                        target = "assets/{}/models/{}.json".format(namespace, resource)
                matched = target in raw.info if target else False
                if matched:
                    exact_matches += 1
                else:
                    missing_item_models.append({"item": path, "modelRef": ref, "target": target})
                target_match = MODEL_RE.match(target or "") if matched else None
                related_model_id = target_match.group(1) if target_match else None
                records.append({"name": part_name, "path": path, "modelRef": ref,
                                "modelPath": target, "modelAvailable": matched,
                                "relatedModelId": related_model_id,
                                "data": parsed})
                owned.add(path)
            write_json(staging / "items" / (item_id + ".json"), {"id": item_id, "items": records})
            item_index.append({"id": item_id, "count": len(records), "matchedModels": exact_matches,
                               "relatedModelId": item_id if item_id in model_ids else None,
                               "parts": [{key: record.get(key) for key in
                                          ("name", "modelRef", "modelPath", "modelAvailable", "relatedModelId")}
                                         for record in records]})

            registry_entries, audio_events, unresolved_sounds = [], defaultdict(list), []
            sound_event_ids = set()
        audio_set = set(sound_files)
        for path in sorted(sound_registries):
            try:
                document = json.loads(read_source(path).decode("utf-8-sig"))
            except Exception as error:
                raise ValueError("Sound registry lỗi {}: {}".format(path, error)) from error
            if not isinstance(document, dict):
                raise ValueError("Sound registry không phải object: " + path)
            registry_entries.append({"path": path, "events": document})
            registry_namespace = path[len("assets/"):-len("/sounds.json")]
            for event_id, definition in document.items():
                sound_event_ids.add(registry_namespace + ":" + event_id)
                entries = definition.get("sounds", []) if isinstance(definition, dict) else []
                for sound in entries:
                    sound_name = sound.get("name") if isinstance(sound, dict) else sound
                    target = sound_target(path, sound_name)
                    if target and target in audio_set:
                        audio_events[target].append({"registry": path, "event": event_id})
                    else:
                        unresolved_sounds.append({"registry": path, "event": event_id,
                                                  "sound": sound_name})
            owned.add(path)

        audio_index = []
        sound_name_ids = set()
        for path in sorted(sound_files):
            data = read_source(path)
            rel = path[len("assets/"):] if path.startswith("assets/") else path
            output_path = "sounds/files/" + rel
            target = staging / output_path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            audio_index.append({"path": path, "url": "pack/data/" + output_path,
                                "bytes": len(data), "sha256": sha256_bytes(data),
                                "events": audio_events.get(path, [])})
            parts = path[len("assets/"):].split("/sounds/", 1)
            if len(parts) == 2:
                namespace, resource = parts
                for extension in AUDIO_EXTS:
                    if resource.lower().endswith(extension):
                        resource = resource[:-len(extension)]
                        break
                sound_name_ids.add(namespace + ":" + resource)
            owned.add(path)

        texture_outputs = {}
        for model_id, stats in model_id_stats.items():
            for resource in stats["resources"]:
                texture_path = tex_path(resource)
                if texture_path not in raw.info:
                    unresolved_textures.add(texture_path)
                    continue
                if texture_path not in texture_outputs:
                    data = fix_png(read_source(texture_path))
                    texture_outputs[texture_path] = data
                    owned.add(texture_path)
                    meta = texture_path + ".mcmeta"
                    if meta in raw.info:
                        texture_outputs[meta] = read_source(meta)
                        owned.add(meta)
                model_sizes[model_id].setdefault("resourceBytes", 0)
                model_sizes[model_id]["resourceBytes"] += len(texture_outputs[texture_path])
                resource_names.add(resource)

        for path, data in texture_outputs.items():
            target = staging / "resources" / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)

        res_list = sorted(resource_names)
        res_index = {resource: index for index, resource in enumerate(res_list)}
        model_rows = []
        for model_id in sorted(model_sizes):
            stats = model_sizes[model_id]
            family = re.split(r"[_-]", model_id)[0] or model_id
            model_rows.append({"id": model_id, "fam": family, "parts": stats["parts"],
                               "mb": stats["bytes"], "res": [res_index[r] for r in stats["resources"] if r in res_index]})
        resources = [{"r": resource, "b": len(texture_outputs.get(tex_path(resource), b""))}
                     for resource in res_list]
        write_json(staging / "models" / "index.json", {
            "version": 1, "ids": model_rows, "res": resources, "amap": atlas_map,
            "missingTextures": sorted(unresolved_textures),
        })
        write_json(staging / "items" / "index.json", {"version": 1, "items": item_index})
        write_json(staging / "sounds" / "index.json", {
            "version": 1, "files": audio_index, "registries": registry_entries,
            "unresolvedReferences": unresolved_sounds,
        })

        names_document = {
            "schemaVersion": 1,
            "models": {model_id: "" for model_id in sorted(model_files)},
            "items": {key: "" for key in sorted(
                set(item_files) |
                {item_id + "/" + part_name for item_id, entries in item_files.items() for _, part_name in entries})},
            "sounds": {key: "" for key in sorted(sound_name_ids)},
            "soundEvents": {key: "" for key in sorted(sound_event_ids)},
        }
        for category in ("models", "items", "sounds", "soundEvents"):
            saved = existing_names.get(category, {})
            if not isinstance(saved, dict):
                continue
            for key in names_document[category]:
                value = saved.get(key)
                if isinstance(value, str) and value.strip():
                    names_document[category][key] = value.strip()
        write_json(staging / "names.json", names_document)

        auxiliary = sorted(set(names) - owned)
        aux_path = staging / "assets" / "auxiliary.zip"
        aux_path.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(aux_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
            for path in auxiliary:
                data = read_source(path)
                archive.writestr(path, data)

        if len(owned) + len(auxiliary) != len(names) or set(names) != owned | set(auxiliary):
            raise RuntimeError("Có tài nguyên nguồn chưa được phân loại hoặc bị lặp")
        extraction_errors = []
        if len(source_checks) != len(names):
            extraction_errors.append("Không đọc qua toàn bộ mục nguồn")
        if extraction_errors:
            raise RuntimeError("; ".join(extraction_errors))

        output_files = []
        for path in sorted(staging.rglob("*")):
            if path.is_file():
                rel = path.relative_to(staging).as_posix()
                output_files.append({"path": rel, "bytes": path.stat().st_size,
                                     "sha256": sha256_file(path)})
        mismatch_sizes = sum(1 for check in source_checks.values() if check["sizeMismatch"])
        mismatch_crcs = sum(1 for check in source_checks.values() if check["crcMismatch"])
        manifest = {
            "schemaVersion": 1,
            "generator": "tools/build_web_data.py",
            "dataBuildId": "",
            "source": {"name": source.name, "bytes": source.stat().st_size,
                       "sha256": source_hash, "entries": len(names),
                       "rawBytesRead": sum(check["bytes"] for check in source_checks.values())},
            "sourceZipMetadata": {"sizeMismatchEntries": mismatch_sizes,
                                  "crcMismatchEntries": mismatch_crcs,
                                  "note": "Pack dùng metadata ZIP giả; payload được giải nén từ raw deflate stream."},
            "counts": {"models": len(model_files), "modelParts": sum(map(len, model_files.values())),
                       "itemGroups": len(item_files), "items": sum(map(len, item_files.values())),
                       "itemModelLinks": sum(row["matchedModels"] for row in item_index),
                       "missingItemModelLinks": len(missing_item_models),
                       "audioFiles": len(sound_files), "linkedAudioFiles": sum(bool(x["events"]) for x in audio_index),
                       "soundRegistries": len(sound_registries), "unresolvedSoundReferences": len(unresolved_sounds),
                       "modelTextures": len(texture_outputs), "auxiliaryFiles": len(auxiliary)},
            "files": output_files,
            "diagnostics": {"missingItemModels": missing_item_models,
                            "unresolvedModelTextures": sorted(unresolved_textures)},
            "optionalBlueprint": "../blueprint.json",
        }
        build_digest = hashlib.sha256(source_hash.encode("ascii"))
        for entry in output_files:
            build_digest.update(entry["path"].encode("utf-8"))
            build_digest.update(entry["sha256"].encode("ascii"))
        build_id = build_digest.hexdigest()
        manifest["dataBuildId"] = build_id
        write_json(staging / "version.json", {"schemaVersion": 1, "buildId": build_id,
                                               "sourceSha256": source_hash, "counts": manifest["counts"]})
        output_files.append({"path": "version.json", "bytes": (staging / "version.json").stat().st_size,
                             "sha256": sha256_file(staging / "version.json")})
        write_json(staging / "manifest.json", manifest)

        for path in staging.rglob("*.json"):
            json.loads(path.read_text(encoding="utf-8"))
        with zipfile.ZipFile(aux_path) as archive:
            if archive.testzip() is not None:
                raise RuntimeError("ZIP auxiliary tạo ra bị lỗi CRC")
        if sha256_file(source) != source_hash:
            raise RuntimeError("ZIP nguồn thay đổi trong lúc build")

        output.parent.mkdir(parents=True, exist_ok=True)
        atomic_publish(staging, output)
        print("Đã tạo:", output)
        print("Models: {} ID / {} parts".format(manifest["counts"]["models"], manifest["counts"]["modelParts"]))
        print("Items: {} nhóm / {} file; {} liên kết model chính xác, {} không khớp".format(
            manifest["counts"]["itemGroups"], manifest["counts"]["items"],
            manifest["counts"]["itemModelLinks"], manifest["counts"]["missingItemModelLinks"]))
        print("Audio: {} file; {} file có event liên kết trực tiếp; {} tham chiếu không khớp".format(
            manifest["counts"]["audioFiles"], manifest["counts"]["linkedAudioFiles"],
            manifest["counts"]["unresolvedSoundReferences"]))
        print("Texture model: {} file; tài nguyên phụ trợ giữ nguyên: {} file".format(
            manifest["counts"]["modelTextures"], manifest["counts"]["auxiliaryFiles"]))
        print("ZIP source metadata không chuẩn: {} size / {} CRC khác central directory; payload giải nén thành công.".format(
            mismatch_sizes, mismatch_crcs))
    except Exception:
        if staging.exists():
            shutil.rmtree(staging)
        raise


def main():
    parser = argparse.ArgumentParser(description="Tách VanGioi_Full_Pack.zip thành dữ liệu tĩnh tải theo tab.")
    parser.add_argument("--source", type=Path, default=ROOT / "VanGioi_Full_Pack.zip")
    parser.add_argument("--out", type=Path, default=ROOT / "pack" / "data")
    args = parser.parse_args()
    try:
        build(args.source, args.out)
    except Exception as error:
        parser.exit(1, "Lỗi build dữ liệu: {}\n".format(error))


if __name__ == "__main__":
    main()