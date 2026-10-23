#!/usr/bin/env python3
"""Build lazy-loadable static indexes and assets from VanGioi_Full_Pack.zip."""
import argparse
import hashlib
import json
import os
import re
import shutil
import stat
import sys
import tempfile
import zipfile
import zlib
from collections import defaultdict
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / "tools"))
from make_pack import ATLAS as LEGACY_ATLAS, RawZip, fix_png, tex_path
from protect_web import protect_html

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
ITEM_MODEL_RE = re.compile(r"^assets/([a-zA-Z0-9_.-]+)/models/(item|items)/(.+)\.json$", re.I)
NAMES_PATH = ROOT / "model_names.json"
DEFAULT_FULL_RSP = ROOT / "VanGioi_Full_Pack.zip"
DEFAULT_ITEM_RSP = ROOT / "VanGioi_Item_Only.zip"
DEFAULT_DATA = ROOT / "pack" / "data"
DEFAULT_DEPLOY_ZIP = ROOT / "dist" / "VanGioi_Web_SRC.zip"


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


def safe_member_name(name):
    path = PurePosixPath(name)
    return (bool(name) and not name.startswith("/") and "\\" not in name
            and not re.match(r"^[a-zA-Z]:", name)
            and all(part not in ("", ".", "..") for part in name.split("/"))
            and not path.is_absolute())


def open_source(path):
    path = Path(path).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError("Không tìm thấy RSP: " + str(path))
    seen, folded = set(), set()
    with zipfile.ZipFile(path) as archive:
        for info in archive.infolist():
            if info.is_dir():
                continue
            if not safe_member_name(info.filename):
                raise ValueError("Đường dẫn không an toàn trong ZIP: " + info.filename)
            if info.filename in seen or info.filename.casefold() in folded:
                raise ValueError("Tên file trùng trong ZIP: " + info.filename)
            if stat.S_ISLNK(info.external_attr >> 16):
                raise ValueError("ZIP có symbolic link không được hỗ trợ: " + info.filename)
            seen.add(info.filename)
            folded.add(info.filename.casefold())
    return RawZip(str(path))


def empty_names():
    return {"models": [], "items": [], "sounds": []}


def validate_names(document):
    if not isinstance(document, dict) or list(document) != ["models", "items", "sounds"]:
        raise ValueError("model_names.json phải có đúng ba phần theo thứ tự: models, items, sounds")
    for section in ("models", "items", "sounds"):
        rows = document[section]
        if not isinstance(rows, list):
            raise ValueError("Phần {} trong model_names.json phải là danh sách".format(section))
        seen = set()
        for row in rows:
            if (not isinstance(row, dict) or not isinstance(row.get("id"), str)
                    or not row["id"].strip() or not isinstance(row.get("name"), str)):
                raise ValueError("Mỗi mục {} phải có id và name dạng chuỗi".format(section))
            if row["id"] in seen:
                raise ValueError("ID trùng trong phần {}: {}".format(section, row["id"]))
            seen.add(row["id"])
    return document


def migrate_legacy_names(path):
    legacy = ROOT / "pack" / "data" / "names.json"
    if not legacy.is_file():
        return empty_names()
    try:
        source = json.loads(legacy.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return empty_names()
    result = empty_names()
    for section in result:
        values = source.get(section, {}) if isinstance(source, dict) else {}
        if isinstance(values, dict):
            result[section] = [{"id": key, "name": value or key}
                               for key, value in sorted(values.items())
                               if isinstance(key, str) and isinstance(value, str)]
    events = source.get("soundEvents", {}) if isinstance(source, dict) else {}
    if isinstance(events, dict):
        result["sounds"].extend({"id": "event:" + key, "name": value or key}
                                for key, value in sorted(events.items())
                                if isinstance(key, str) and isinstance(value, str))
    return result


def load_names(path=NAMES_PATH):
    path = Path(path)
    if not path.exists():
        return migrate_legacy_names(path)
    try:
        return validate_names(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError, ValueError) as error:
        raise ValueError("Không đọc được {}: {}".format(path, error)) from error


def merge_names(existing, identifiers):
    previous = {row["id"]: row for row in existing}
    result = []
    for identifier in sorted(set(identifiers)):
        old = previous.get(identifier, {})
        name = old.get("name")
        row = dict(old)
        row.update({"id": identifier, "name": name.strip() if isinstance(name, str) and name.strip() else identifier})
        result.append(row)
    return result


def write_names_atomic(path, document):
    path = Path(path).expanduser().resolve()
    validate_names(document)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", newline="\n",
                                         dir=path.parent, prefix=".model_names-", suffix=".tmp",
                                         delete=False) as stream:
            temp_path = Path(stream.name)
            json.dump(document, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        os.replace(temp_path, path)
    finally:
        if temp_path and temp_path.exists():
            temp_path.unlink()


def discover_full_ids(source):
    raw = open_source(source)
    identifiers = {safe_id(match.group(1)) for name in raw.info
                   if (match := MODEL_RE.match(name))}
    if not identifiers:
        raise ValueError("Full RSP không có model trong assets/modelengine/models/")
    return identifiers


def model_resource_id(namespace, resource):
    if not isinstance(resource, str) or not resource:
        return None
    if ":" in resource:
        namespace, resource = resource.split(":", 1)
    if not re.fullmatch(r"[a-zA-Z0-9_.-]+", namespace):
        return None
    if resource.endswith(".json"):
        resource = resource[:-5]
    if (not resource or resource.startswith("/") or "\\" in resource
            or any(part in ("", ".", "..") for part in resource.split("/"))):
        return None
    return namespace + ":" + resource


def item_model_paths(raw):
    paths = {}
    candidates = set()
    for name in raw.info:
        if not name.startswith("assets/") or "/models/" not in name or not name.lower().endswith(".json"):
            continue
        namespace, resource = name[len("assets/"):].split("/models/", 1)
        resource = resource[:-5]
        identifier = model_resource_id(namespace, resource)
        if identifier:
            paths[identifier] = name
            if ITEM_MODEL_RE.match(name):
                candidates.add(identifier)
    return paths, candidates


def item_model_references(raw, paths):
    references = set()
    for name in raw.info:
        if not name.startswith("assets/") or not name.lower().endswith(".json"):
            continue
        if "/models/" in name:
            match = ITEM_MODEL_RE.match(name)
            if not match:
                continue
            try:
                document = json.loads(raw.read(name).decode("utf-8-sig"))
            except (ValueError, UnicodeError, zlib.error) as error:
                raise ValueError("JSON model item lỗi {}: {}".format(name, error)) from error
            namespace = match.group(1)
            for override in document.get("overrides", []) if isinstance(document, dict) else []:
                if isinstance(override, dict):
                    identifier = model_resource_id(namespace, override.get("model"))
                    if identifier in paths:
                        references.add(identifier)
        elif re.match(r"^assets/[^/]+/items/", name):
            try:
                document = json.loads(raw.read(name).decode("utf-8-sig"))
            except (ValueError, UnicodeError, zlib.error) as error:
                raise ValueError("JSON item lỗi {}: {}".format(name, error)) from error
            namespace = name[len("assets/"):].split("/", 1)[0]
            stack = [document]
            while stack:
                value = stack.pop()
                if isinstance(value, dict):
                    model = value.get("model")
                    identifier = model_resource_id(namespace, model)
                    if identifier in paths:
                        references.add(identifier)
                    stack.extend(value.values())
                elif isinstance(value, list):
                    stack.extend(value)
    return references


def discover_item_ids(source):
    raw = open_source(source)
    paths, identifiers = item_model_paths(raw)
    identifiers.update(item_model_references(raw, paths))
    if not identifiers:
        raise ValueError("Item RSP không có model trong assets/<namespace>/models/item(s)/")
    return identifiers


def import_section(section, source, names_path=NAMES_PATH):
    identifiers = discover_full_ids(source) if section == "models" else discover_item_ids(source)
    document = load_names(names_path)
    document[section] = merge_names(document[section], identifiers)
    write_names_atomic(names_path, document)
    print("Đã nhập {} ID vào {}.".format(len(identifiers), section))
    print("Mở file này để chỉnh tên: {}".format(Path(names_path).resolve()))


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


def resolve_item_model(raw, model_paths, identifier, atlas_map, read_item, cache, active):
    if identifier in cache:
        return cache[identifier]
    path = model_paths.get(identifier)
    if not path:
        return None
    if identifier in active:
        raise ValueError("Vòng lặp parent model item tại: " + identifier)
    active.add(identifier)
    try:
        try:
            document = json.loads(read_item(path).decode("utf-8-sig"))
        except Exception as error:
            raise ValueError("JSON model item lỗi {}: {}".format(path, error)) from error
        if not isinstance(document, dict):
            raise ValueError("Model item không phải JSON object: " + path)

        parent = document.get("parent")
        parent_data = None
        builtin_parent = ""
        if isinstance(parent, str):
            parent_id = model_resource_id(identifier.split(":", 1)[0], parent)
            if parent_id in model_paths:
                parent_data = resolve_item_model(raw, model_paths, parent_id, atlas_map,
                                                 read_item, cache, active)
            else:
                builtin_parent = parent.split(":", 1)[-1]

        textures = dict(parent_data.get("textures", {})) if parent_data else {}
        if isinstance(document.get("textures"), dict):
            textures.update(document["textures"])
        elements = document.get("elements")
        if not isinstance(elements, list) or not elements:
            elements = list(parent_data.get("elements", [])) if parent_data else []
        display = dict(parent_data.get("display", {})) if parent_data else {}
        if isinstance(document.get("display"), dict):
            display.update(document["display"])

        parent_leaf = builtin_parent.rsplit("/", 1)[-1]
        if not elements and parent_leaf in ("generated", "handheld"):
            texture_key = "layer0" if "layer0" in textures else next(iter(textures), None)
            if texture_key:
                face = {"uv": [0, 0, 16, 16], "texture": "#" + texture_key}
                elements = [{"from": [0, 0, 7.5], "to": [16, 16, 8.5],
                             "faces": {direction: face for direction in
                                       ("north", "south", "east", "west", "up", "down")}}]
        elif not elements and parent_leaf == "cube_all" and textures:
            texture_key = "all" if "all" in textures else next(iter(textures))
            face = {"uv": [0, 0, 16, 16], "texture": "#" + texture_key}
            elements = [{"from": [0, 0, 0], "to": [16, 16, 16],
                         "faces": {direction: face for direction in
                                   ("north", "south", "east", "west", "up", "down")}}]

        for key, value in list(textures.items()):
            if isinstance(value, str) and not value.startswith("#") and value.startswith("ia:"):
                textures[key] = atlas_map.get(value, value)
        result = {"textures": textures, "elements": elements, "display": display}
        cache[identifier] = result
        return result
    finally:
        active.remove(identifier)


def build_item_catalog(raw, staging, atlas_map, read_item):
    model_paths, item_ids = item_model_paths(raw)
    item_ids.update(item_model_references(raw, model_paths))
    grouped = defaultdict(list)
    texture_resources = set()
    unresolved = set()
    cache = {}
    for identifier in sorted(item_ids):
        namespace, resource = identifier.split(":", 1)
        group_id = "itemrsp_" + safe_id(namespace)
        model_path = model_paths[identifier]
        model_data = resolve_item_model(raw, model_paths, identifier, atlas_map,
                                        read_item, cache, set())
        textures = model_data.get("textures", {}) if model_data else {}
        for value in textures.values():
            if not isinstance(value, str) or value.startswith("#"):
                continue
            if value.startswith("ia:"):
                value = atlas_map.get(value)
                if not value:
                    unresolved.add(model_path)
                    continue
            texture_resources.add(value)
        grouped[namespace].append({
            "name": resource,
            "nameId": identifier,
            "path": model_path,
            "modelRef": identifier,
            "modelPath": model_path,
            "modelAvailable": bool(model_data and model_data.get("elements")),
            "relatedModelId": group_id,
            "itemModelData": model_data or {"textures": {}, "elements": [], "display": {}},
        })

    item_index = []
    for namespace in sorted(grouped):
        group_id = "itemrsp_" + safe_id(namespace)
        records = grouped[namespace]
        write_json(staging / "items" / (group_id + ".json"), {"id": group_id, "items": records})
        item_index.append({
            "id": group_id,
            "nameId": "namespace:" + namespace,
            "count": len(records),
            "matchedModels": sum(record["modelAvailable"] for record in records),
            "relatedModelId": None,
            "parts": [{key: record[key] for key in
                       ("name", "nameId", "modelRef", "modelPath", "modelAvailable", "relatedModelId")}
                      for record in records],
        })
    return item_index, texture_resources, unresolved, len(item_ids)


def load_atlas(raw, read_source):
    atlas_map = {}
    paths = set(ATLAS_PATHS)
    paths.update(name for name in raw.info
                 if "/atlases/" in name.lower()
                 and Path(name).name.lower() in ("blocks.json", "items.json"))
    for atlas_path in sorted(paths):
        if atlas_path not in raw:
            continue
        try:
            atlas = json.loads(read_source(atlas_path).decode("utf-8-sig"))
            for entry in atlas.get("sources", []):
                if (isinstance(entry, dict) and isinstance(entry.get("sprite"), str)
                        and isinstance(entry.get("resource"), str)):
                    atlas_map.setdefault(entry["sprite"], entry["resource"])
        except Exception as error:
            raise ValueError("Không đọc được atlas {}: {}".format(atlas_path, error)) from error
    return atlas_map


def build(source, output, item_source=None, names_path=NAMES_PATH):
    source = Path(source).expanduser().resolve()
    output = Path(output).expanduser().resolve()
    names_path = Path(names_path).expanduser().resolve()
    if output == ROOT or output in source.parents or output == source:
        raise ValueError("Đường dẫn output không an toàn hoặc trùng ZIP nguồn")
    if item_source is not None:
        item_source = Path(item_source).expanduser().resolve()
        if output in item_source.parents or output == item_source:
            raise ValueError("Đường dẫn output không an toàn hoặc trùng Item RSP")

    shared_names = load_names(names_path)
    source_hash = sha256_file(source)
    raw = open_source(source)
    item_hash = sha256_file(item_source) if item_source else None
    item_raw = open_source(item_source) if item_source else None
    output.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".web-data-build-", dir=str(output.parent)))
    source_checks = {}
    item_checks = {}

    def checked_read(archive, checks, name):
        data = archive.read(name)
        if name not in checks:
            info = archive.info[name]
            checks[name] = {"bytes": len(data),
                            "sizeMismatch": len(data) != info.file_size,
                            "crcMismatch": (zlib.crc32(data) & 0xFFFFFFFF) != info.CRC}
        return data

    def read_source(name):
        return checked_read(raw, source_checks, name)

    def read_item(name):
        if item_raw is None:
            raise ValueError("Thiếu Item RSP để đọc: " + name)
        return checked_read(item_raw, item_checks, name)

    try:
        archive_names = sorted(raw.info)
        model_files = defaultdict(list)
        sound_files, sound_registries = [], []
        for name in archive_names:
            match = MODEL_RE.match(name)
            if match:
                model_files[safe_id(match.group(1))].append((name, match.group(2)))
            if name.lower().endswith(AUDIO_EXTS):
                sound_files.append(name)
            if name.startswith("assets/") and name.endswith("/sounds.json"):
                sound_registries.append(name)
        if not model_files:
            raise ValueError("Full RSP không có model trong assets/modelengine/models/")

        model_atlas = load_atlas(raw, read_source)
        item_atlas = load_atlas(item_raw, read_item) if item_raw is not None else {}

        owned = set()
        resource_names = set()
        model_sizes = {}
        model_id_stats = {}
        unresolved_textures = set()
        for model_id in sorted(model_files):
            resources, model_bytes, part_count = set(), 0, 0
            parts = []
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
                        value = model_atlas.get(value)
                        if not value:
                            unresolved_textures.add(path)
                            continue
                    resources.add(value)
                model_bytes += len(data)
                part_count += 1
                parts.append({"name": part_name, "path": path, "json": parsed})
                owned.add(path)
            model_sizes[model_id] = {"parts": part_count, "bytes": model_bytes,
                                     "resources": sorted(resources)}
            model_id_stats[model_id] = {"resources": resources}
            write_json(staging / "models" / (model_id + ".json"), {"id": model_id, "parts": parts})

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

        if not sound_files and not sound_registries and (output / "sounds" / "index.json").is_file():
            shutil.copytree(output / "sounds", staging / "sounds", dirs_exist_ok=True)
            previous_sounds = json.loads((staging / "sounds" / "index.json").read_text(encoding="utf-8"))
            audio_index = previous_sounds.get("files", [])
            registry_entries = previous_sounds.get("registries", [])
            unresolved_sounds = previous_sounds.get("unresolvedReferences", [])
            for entry in audio_index:
                parts = entry.get("path", "").removeprefix("assets/").split("/sounds/", 1)
                if len(parts) == 2:
                    namespace, resource = parts
                    for extension in AUDIO_EXTS:
                        if resource.lower().endswith(extension):
                            resource = resource[:-len(extension)]
                            break
                    sound_name_ids.add(namespace + ":" + resource)
            for registry in registry_entries:
                path = registry.get("path", "")
                namespace = path[len("assets/"):-len("/sounds.json")] if path.startswith("assets/") and path.endswith("/sounds.json") else ""
                sound_event_ids.update(namespace + ":" + event_id for event_id in registry.get("events", {}))

        texture_sizes, written_textures = {}, set()

        def write_texture(texture_path):
            if texture_path in written_textures:
                return
            archive = raw if texture_path in raw.info else item_raw
            reader = read_source if archive is raw else read_item
            if archive is None or texture_path not in archive.info:
                raise FileNotFoundError(texture_path)
            data = fix_png(reader(texture_path))
            target = staging / "resources" / texture_path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            texture_sizes[texture_path] = len(data)
            written_textures.add(texture_path)
            meta = texture_path + ".mcmeta"
            meta_archive = raw if meta in raw.info else item_raw
            if meta_archive is not None and meta in meta_archive.info:
                meta_reader = read_source if meta_archive is raw else read_item
                (staging / "resources" / meta).write_bytes(meta_reader(meta))
                texture_sizes[meta] = meta_archive.info[meta].file_size

        for model_id, stats in model_id_stats.items():
            for resource in stats["resources"]:
                texture_path = tex_path(resource)
                if not safe_member_name(texture_path):
                    raise ValueError("Texture path không an toàn: " + texture_path)
                try:
                    write_texture(texture_path)
                except FileNotFoundError:
                    unresolved_textures.add(texture_path)
                    continue
                resource_names.add(resource)
                model_sizes[model_id].setdefault("resourceBytes", 0)
                model_sizes[model_id]["resourceBytes"] += texture_sizes[texture_path]

        item_index, item_resource_names, unresolved_item_textures, item_count = [], set(), set(), 0
        if item_raw is not None:
            item_index, item_resource_names, unresolved_item_textures, item_count = build_item_catalog(
                item_raw, staging, item_atlas, read_item)
            for resource in sorted(item_resource_names):
                texture_path = tex_path(resource)
                if not safe_member_name(texture_path):
                    raise ValueError("Item texture path không an toàn: " + texture_path)
                try:
                    write_texture(texture_path)
                except FileNotFoundError:
                    unresolved_item_textures.add(texture_path)
            if item_count == 0 and (output / "items" / "index.json").is_file():
                shutil.rmtree(staging / "items", ignore_errors=True)
                shutil.copytree(output / "items", staging / "items")
                item_index = json.loads((staging / "items" / "index.json").read_text(encoding="utf-8"))["items"]
                item_count = sum(group.get("count", 0) for group in item_index)
        else:
            item_index = []
            write_json(staging / "items" / "index.json", {"version": 1, "items": item_index})

        res_list = sorted(resource_names)
        res_index = {resource: index for index, resource in enumerate(res_list)}
        model_rows = []
        for model_id in sorted(model_sizes):
            stats = model_sizes[model_id]
            family = re.split(r"[_-]", model_id)[0] or model_id
            model_rows.append({"id": model_id, "fam": family, "parts": stats["parts"],
                               "mb": stats["bytes"], "res": [res_index[r] for r in stats["resources"] if r in res_index]})
        resources = [{"r": resource, "b": texture_sizes.get(tex_path(resource), 0)}
                     for resource in res_list]
        write_json(staging / "models" / "index.json", {
            "version": 1, "ids": model_rows, "res": resources, "amap": model_atlas,
            "missingTextures": sorted(unresolved_textures),
        })
        write_json(staging / "items" / "index.json", {"version": 1, "items": item_index, "amap": item_atlas})
        write_json(staging / "sounds" / "index.json", {
            "version": 1, "files": audio_index, "registries": registry_entries,
            "unresolvedReferences": unresolved_sounds,
        })

        discovered_models = set(model_files)
        discovered_items = {identifier for entry in item_index for identifier in
                            (part.get("nameId") for part in entry.get("parts", [])) if identifier}
        discovered_sounds = sound_name_ids | {"event:" + identifier for identifier in sound_event_ids}
        final_names = {
            "models": merge_names(shared_names["models"], discovered_models) if discovered_models else shared_names["models"],
            "items": merge_names(shared_names["items"], discovered_items) if discovered_items else shared_names["items"],
            "sounds": merge_names(shared_names["sounds"], discovered_sounds) if discovered_sounds else shared_names["sounds"],
        }
        validate_names(final_names)
        write_json(staging / "model_names.json", final_names)

        output_files = []
        for path in sorted(staging.rglob("*")):
            if path.is_file():
                rel = path.relative_to(staging).as_posix()
                output_files.append({"path": rel, "bytes": path.stat().st_size,
                                     "sha256": sha256_file(path)})
        full_mismatch_sizes = sum(check["sizeMismatch"] for check in source_checks.values())
        full_mismatch_crcs = sum(check["crcMismatch"] for check in source_checks.values())
        item_mismatch_sizes = sum(check["sizeMismatch"] for check in item_checks.values())
        item_mismatch_crcs = sum(check["crcMismatch"] for check in item_checks.values())
        counts = {"models": len(model_files), "modelParts": sum(map(len, model_files.values())),
                  "itemGroups": len(item_index), "items": item_count,
                  "itemModelLinks": sum(group.get("matchedModels", 0) for group in item_index),
                  "missingItemModelLinks": sum(not part.get("modelAvailable", False)
                                                for group in item_index for part in group.get("parts", [])),
                  "audioFiles": len(sound_files), "linkedAudioFiles": sum(bool(x["events"]) for x in audio_index),
                  "soundRegistries": len(sound_registries), "unresolvedSoundReferences": len(unresolved_sounds),
                  "modelTextures": len(texture_sizes), "auxiliaryFiles": 0}
        manifest = {
            "schemaVersion": 2, "generator": "tools/build_web_data.py", "dataBuildId": "",
            "source": {"name": source.name, "bytes": source.stat().st_size,
                       "sha256": source_hash, "entries": len(raw.info),
                       "rawBytesRead": sum(check["bytes"] for check in source_checks.values())},
            "itemSource": ({"name": item_source.name, "bytes": item_source.stat().st_size,
                            "sha256": item_hash, "entries": len(item_raw.info),
                            "rawBytesRead": sum(check["bytes"] for check in item_checks.values())}
                           if item_source else None),
            "sourceZipMetadata": {"fullSizeMismatchEntries": full_mismatch_sizes,
                                  "fullCrcMismatchEntries": full_mismatch_crcs,
                                  "itemSizeMismatchEntries": item_mismatch_sizes,
                                  "itemCrcMismatchEntries": item_mismatch_crcs},
            "counts": counts, "files": output_files,
            "diagnostics": {"unresolvedModelTextures": sorted(unresolved_textures),
                            "unresolvedItemTextures": sorted(unresolved_item_textures)},
            "optionalBlueprint": "../blueprint.json",
        }
        build_digest = hashlib.sha256(source_hash.encode("ascii"))
        if item_hash:
            build_digest.update(item_hash.encode("ascii"))
        for entry in output_files:
            build_digest.update(entry["path"].encode("utf-8"))
            build_digest.update(entry["sha256"].encode("ascii"))
        manifest["dataBuildId"] = build_digest.hexdigest()
        write_json(staging / "version.json", {"schemaVersion": 1, "buildId": manifest["dataBuildId"],
                                               "sourceSha256": source_hash, "counts": counts})
        manifest["files"].append({"path": "version.json", "bytes": (staging / "version.json").stat().st_size,
                                   "sha256": sha256_file(staging / "version.json")})
        write_json(staging / "manifest.json", manifest)

        for path in staging.rglob("*.json"):
            json.loads(path.read_text(encoding="utf-8"))
        if sha256_file(source) != source_hash or (item_source and sha256_file(item_source) != item_hash):
            raise RuntimeError("RSP nguồn thay đổi trong lúc build")

        atomic_publish(staging, output)
        write_names_atomic(names_path, final_names)
        print("Đã tạo dữ liệu web:", output)
        print("Models: {} ID / {} parts".format(counts["models"], counts["modelParts"]))
        print("Items: {} nhóm / {} model item".format(counts["itemGroups"], counts["items"]))
        print("Audio: {} file; {} event tham chiếu chưa khớp".format(counts["audioFiles"], counts["unresolvedSoundReferences"]))
        print("Texture chưa tìm thấy: model {}, item {}".format(len(unresolved_textures), len(unresolved_item_textures)))
        print("ZIP metadata size/CRC lệch: Full {}/{}, Item {}/{}".format(
            full_mismatch_sizes, full_mismatch_crcs, item_mismatch_sizes, item_mismatch_crcs))
        return final_names
    except Exception:
        if staging.exists():
            shutil.rmtree(staging)
        raise


def create_deploy_zip(data_dir=DEFAULT_DATA, output=DEFAULT_DEPLOY_ZIP):
    data_dir = Path(data_dir).resolve()
    output = Path(output).resolve()
    if data_dir == output or data_dir in output.parents or output in data_dir.parents:
        raise ValueError("Đường dẫn ZIP deploy không an toàn")
    required = [ROOT / "index.html", ROOT / "lib" / "three.min.js", ROOT / "lib" / "fflate.min.js"]
    if any(not path.is_file() for path in required):
        raise FileNotFoundError("Thiếu index.html hoặc thư viện lib cần để chạy website")
    if not (data_dir / "version.json").is_file():
        raise FileNotFoundError("Chưa có pack/data/version.json; hãy build dữ liệu trước")
    members = [(path, path.relative_to(ROOT).as_posix()) for path in required]
    # index.html's hosted loader requests these split model-pack files directly.
    # They are runtime assets, not build inputs, so include them in the deploy ZIP.
    hosted_parts = sorted((ROOT / "pack").glob("mobs.zip.[0-9][0-9][0-9]"))
    if not hosted_parts:
        raise FileNotFoundError("Thiếu pack/mobs.zip.001...; website không thể tự tải dữ liệu model")
    members.extend((path, path.relative_to(ROOT).as_posix()) for path in hosted_parts)
    for optional in (ROOT / ".nojekyll", ROOT / "names.json", ROOT / "pack" / "blueprint.json"):
        if optional.is_file():
            members.append((optional, optional.relative_to(ROOT).as_posix()))
    # Optional shared Blockbench blueprints. Files are kept outside pack/data and
    # served from /blueprints/; the browser silently skips this folder when empty.
    hosted_blueprints = ROOT / "blueprints"
    if hosted_blueprints.is_dir():
        for path in sorted(hosted_blueprints.rglob("*")):
            if not path.is_file():
                continue
            if path.is_symlink() or not path.resolve().is_relative_to(hosted_blueprints.resolve()):
                raise ValueError("Symlink hoặc đường dẫn ngoài blueprints không được đưa vào ZIP: " + str(path))
            members.append((path, path.relative_to(ROOT).as_posix()))
    for path in sorted(data_dir.rglob("*")):
        if not path.is_file() or path.name == "manifest.json":
            continue
        if path.is_symlink() or not path.resolve().is_relative_to(data_dir):
            raise ValueError("Symlink hoặc đường dẫn ngoài pack/data không được đưa vào ZIP: " + str(path))
        relative = path.relative_to(data_dir).as_posix()
        if relative != "assets/auxiliary.zip":
            members.append((path, "pack/data/" + relative))
    for path in members:
        source_path, _ = path
        if source_path.is_symlink():
            raise ValueError("Asset deploy không an toàn: " + str(source_path))
    for source_path, archive_path in members:
        if not safe_member_name(archive_path):
            raise ValueError("Đường dẫn trong ZIP deploy không an toàn: " + archive_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    temp_path = output.with_name("." + output.name + ".tmp")
    try:
        with zipfile.ZipFile(temp_path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            for path, archive_path in members:
                if archive_path == "index.html":
                    protected = protect_html(path.read_text(encoding="utf-8"))
                    archive.writestr(archive_path, protected.encode("utf-8"))
                else:
                    archive.write(path, archive_path)
        with zipfile.ZipFile(temp_path) as archive:
            bad = archive.testzip()
            if bad:
                raise RuntimeError("ZIP deploy lỗi CRC tại: " + bad)
            names = set(archive.namelist())
            required = {"index.html", "lib/three.min.js", "lib/fflate.min.js",
                        "pack/data/version.json", "pack/data/model_names.json"}
            required.update(path.relative_to(ROOT).as_posix() for path in hosted_parts)
            source_archives = {DEFAULT_FULL_RSP.name, DEFAULT_ITEM_RSP.name, "VanGioi_Item_Pack.zip"}
            forbidden = any(name in source_archives or PurePosixPath(name).parts[0] in ("tools", "__pycache__")
                            or name.endswith(".pyc") for name in names)
            if not required.issubset(names):
                raise RuntimeError("ZIP deploy thiếu file website cần thiết")
            if forbidden:
                raise RuntimeError("ZIP deploy có chứa nguồn hoặc công cụ build")
            deployed_html = archive.read("index.html").decode("utf-8")
            if 'id="vg-web-guard"' not in deployed_html:
                raise RuntimeError("ZIP deploy thiếu lớp cản phím tắt cơ bản")
            if "sourceMappingURL=" in deployed_html:
                raise RuntimeError("ZIP deploy còn tham chiếu source map")
        os.replace(temp_path, output)
    finally:
        if temp_path.exists():
            temp_path.unlink()
    print("Đã tạo ZIP triển khai:", output)
    return output


def build_web_source(full_source, item_source, output=DEFAULT_DATA,
                     deploy_zip=DEFAULT_DEPLOY_ZIP, names_path=NAMES_PATH):
    build(full_source, output, item_source, names_path)
    return create_deploy_zip(output, deploy_zip)


def prompt_path(label, default):
    value = input("{} [{}]: ".format(label, default)).strip()
    return Path(value).expanduser() if value else Path(default)


def print_help():
    print("""
Quy trình sử dụng:
1. Import Full RSP để cập nhật danh sách model; giữ nguyên items và sounds.
2. Import Item RSP để cập nhật model item; giữ nguyên models và sounds.
   Sau mỗi lần nhập, mở model_names.json để chỉnh trường name.
3. Build Web SRC đọc lại model_names.json, dựng pack/data và tạo dist/VanGioi_Web_SRC.zip.
4. Hướng dẫn.
5. Thoát.

Mặc định dùng VanGioi_Full_Pack.zip và VanGioi_Item_Only.zip ở thư mục dự án.
ZIP triển khai không chứa RSP nguồn, cache hoặc công cụ build.
""".strip())


def run_menu():
    while True:
        print("\n=== VanGioi Web SRC ===")
        print("1. Import Full RSP — dữ liệu tab Model")
        print("2. Import Item RSP — dữ liệu tab Item")
        print("3. Build Web SRC — cập nhật dữ liệu và tạo ZIP triển khai")
        print("4. Hướng dẫn")
        print("5. Thoát")
        choice = input("Chọn 1-5: ").strip()
        try:
            if choice == "1":
                import_section("models", prompt_path("Đường dẫn Full RSP", DEFAULT_FULL_RSP))
            elif choice == "2":
                import_section("items", prompt_path("Đường dẫn Item RSP", DEFAULT_ITEM_RSP))
            elif choice == "3":
                full = prompt_path("Đường dẫn Full RSP", DEFAULT_FULL_RSP)
                items = prompt_path("Đường dẫn Item RSP", DEFAULT_ITEM_RSP)
                build_web_source(full, items)
            elif choice == "4":
                print_help()
            elif choice == "5":
                return
            else:
                print("Vui lòng chọn từ 1 đến 5.")
        except (OSError, ValueError, RuntimeError, zipfile.BadZipFile) as error:
            print("Lỗi: {}".format(error), file=sys.stderr)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Import RSP và build VanGioi Web SRC.")
    parser.add_argument("--import-full", type=Path, help="Chỉ nhập ID model từ Full RSP")
    parser.add_argument("--import-items", type=Path, help="Chỉ nhập ID model item từ Item RSP")
    parser.add_argument("--build", action="store_true", help="Build data và ZIP triển khai")
    parser.add_argument("--source", type=Path, default=DEFAULT_FULL_RSP, help="Full RSP")
    parser.add_argument("--item-source", type=Path, default=DEFAULT_ITEM_RSP, help="Item-only RSP")
    parser.add_argument("--out", type=Path, default=DEFAULT_DATA, help="Thư mục pack/data")
    parser.add_argument("--zip", type=Path, default=DEFAULT_DEPLOY_ZIP, help="ZIP triển khai")
    parser.add_argument("--names", type=Path, default=NAMES_PATH, help="File model_names.json")
    args = parser.parse_args(argv)
    try:
        if args.import_full:
            import_section("models", args.import_full, args.names)
        elif args.import_items:
            import_section("items", args.import_items, args.names)
        elif args.build:
            build_web_source(args.source, args.item_source, args.out, args.zip, args.names)
        elif argv is None and len(sys.argv) > 1:
            parser.error("Chọn --import-full, --import-items hoặc --build")
        else:
            run_menu()
    except (OSError, ValueError, RuntimeError, zipfile.BadZipFile) as error:
        parser.exit(1, "Lỗi: {}\n".format(error))


if __name__ == "__main__":
    main()