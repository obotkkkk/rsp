#!/usr/bin/env python3
"""Static regression checks for a built VanGioi deploy ZIP."""
from __future__ import annotations
import argparse
import json
import re
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ZIP = ROOT / "dist" / "VanGioi_Web_SRC.zip"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--zip", type=Path, default=DEFAULT_ZIP)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    zpath = args.zip.expanduser().resolve()
    report = {"zip": zpath.name, "checks": {}, "errors": []}
    if not zpath.is_file():
        report["errors"].append("Không tìm thấy ZIP triển khai")
    else:
        with zipfile.ZipFile(zpath) as archive:
            names = set(archive.namelist())
            bad = archive.testzip()
            report["checks"]["zip_crc"] = bad is None
            if bad:
                report["errors"].append("CRC lỗi: " + bad)
            required = {"index.html", "lib/three.min.js", "lib/fflate.min.js",
                        "pack/data/version.json", "pack/data/model_names.json",
                        "pack/data/items/index.json", "pack/mobs.zip.001"}
            missing = sorted(required - names)
            report["checks"]["required_files"] = not missing
            if missing:
                report["errors"].append("Thiếu file: " + ", ".join(missing))
            forbidden = [n for n in names if n.startswith("tools/") or n.endswith(".pyc")
                         or n in {"VanGioi_Full_Pack.zip", "VanGioi_Item_Only.zip", "VanGioi_Item_Pack.zip"}]
            report["checks"]["no_build_tools_or_source_rsp"] = not forbidden
            if forbidden:
                report["errors"].append("Có công cụ build/RSP nguồn trong ZIP")
            html = archive.read("index.html").decode("utf-8")
            report["checks"]["basic_guard"] = 'id="vg-web-guard"' in html
            report["checks"]["no_source_map"] = "sourceMappingURL=" not in html
            report["checks"]["bad_crc_output_hooks"] = (
                "function corruptZipCrc" in html
                and "return corruptZipCrc(fflate.zipSync(files))" in html
                and "corruptZipCrc(cleanZip)" in html
            )
            if not report["checks"]["basic_guard"]:
                report["errors"].append("Thiếu lớp cản phím tắt")
            if not report["checks"]["no_source_map"]:
                report["errors"].append("Còn source map reference")
            if not report["checks"]["bad_crc_output_hooks"]:
                report["errors"].append("Chưa áp dụng Bad CRC cho cả ZIP Model và Item")
            item_index = json.loads(archive.read("pack/data/items/index.json"))
            report["item_group_count"] = len(item_index.get("items", []))
            report["item_count"] = sum(int(g.get("count", 0) or 0) for g in item_index.get("items", []))
            report["entry_count"] = len(names)
            if not report["item_group_count"]:
                report["errors"].append("Item index rỗng")
            # Check that hosted split parts reassemble into a readable ZIP.
            parts = sorted(n for n in names if re.fullmatch(r"pack/mobs\.zip\.\d{3}", n))
            report["pack_part_count"] = len(parts)
            try:
                with tempfile.NamedTemporaryFile(suffix=".zip") as temp:
                    for part in parts:
                        temp.write(archive.read(part))
                    temp.flush()
                    with zipfile.ZipFile(temp.name) as pack:
                        report["checks"]["hosted_pack_crc"] = pack.testzip() is None
                        report["model_entry_count"] = sum(
                            1 for n in pack.namelist()
                            if n.startswith("assets/modelengine/models/") and n.endswith(".json"))
            except Exception as error:
                report["checks"]["hosted_pack_crc"] = False
                report["errors"].append("Pack chia phần không đọc được: " + str(error))
            # Parse inline JS if Node.js is installed; this isn't a browser runtime test.
            scripts = [m.group(2) for m in re.finditer(r"<script([^>]*)>(.*?)</script>", html, re.I | re.S)
                       if not re.search(r"\bsrc\s*=", m.group(1), re.I) and m.group(2).strip()]
            node = shutil.which("node")
            report["inline_script_count"] = len(scripts)
            if node:
                syntax_ok = True
                with tempfile.TemporaryDirectory() as directory:
                    for i, script in enumerate(scripts):
                        js = Path(directory) / ("inline_{}.js".format(i))
                        js.write_text(script, encoding="utf-8")
                        result = subprocess.run([node, "--check", str(js)], capture_output=True, text=True)
                        if result.returncode:
                            syntax_ok = False
                            report["errors"].append("JS cú pháp lỗi script {}: {}".format(i, result.stderr.strip()))
                report["checks"]["inline_js_syntax"] = syntax_ok
            else:
                report["checks"]["inline_js_syntax"] = None
                report["notes"] = ["Không có Node.js; bỏ qua kiểm tra cú pháp JS"]
    report["ok"] = not report["errors"] and all(v is not False for v in report["checks"].values())
    payload = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    print(payload, end="")
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(payload, encoding="utf-8")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
