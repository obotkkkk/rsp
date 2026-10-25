#!/usr/bin/env python3
"""Regression test for the bad-CRC deterrent on web-generated RSP ZIPs.

Generates sample archives using both fflate.zipSync (model RSP) and fflate.zip
(item RSP), applies the actual corruptZipCrc function from index.html, confirms
unzip reports Bad CRC, and verifies Java ZipFile + ZipFS can still read entries.
This does not launch Minecraft and does not imply encryption.
"""
from __future__ import annotations
import argparse
import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, text=True, capture_output=True, check=False, **kwargs)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--html", type=Path, default=ROOT / "index.html")
    parser.add_argument("--fflate", type=Path, default=ROOT / "lib" / "fflate.min.js")
    args = parser.parse_args()
    report = {"ok": False, "checks": {}, "notes": [], "errors": []}
    html_path, fflate_path = args.html.resolve(), args.fflate.resolve()
    html = html_path.read_text(encoding="utf-8")
    node, javac, java, unzip = (shutil.which(x) for x in ("node", "javac", "java", "unzip"))
    if not node or not javac or not java or not unzip:
        report["errors"].append("Cần Node.js, JDK (javac/java) và unzip để chạy bài kiểm thử đầy đủ.")
    else:
        with tempfile.TemporaryDirectory(prefix="vg-bad-crc-") as temp:
            td = Path(temp)
            model_zip, item_zip = td / "model-rsp.zip", td / "item-rsp.zip"
            node_script = td / "make_sample.cjs"
            node_script.write_text(r'''const fs = require("fs");
const path = require("path");
const fflate = require(path.resolve(process.argv[2]));
const html = fs.readFileSync(process.argv[3], "utf8");
const start = html.indexOf("function corruptZipCrc(zipBytes)");
if (start < 0) throw new Error("Không thấy corruptZipCrc trong index.html");
const open = html.indexOf("{", start);
let depth = 0, end = -1;
for (let i = open; i < html.length; i++) {
  if (html[i] === "{") depth++;
  else if (html[i] === "}" && --depth === 0) { end = i + 1; break; }
}
if (end < 0) throw new Error("Không tìm thấy cuối hàm corruptZipCrc");
const corruptZipCrc = new Function(html.slice(start, end) + "\nreturn corruptZipCrc;")();
const files = {
  "pack.mcmeta": [new TextEncoder().encode('{"pack":{"pack_format":46,"description":"test"}}'), {level:9}],
  "assets/minecraft/models/item/test.json": [new TextEncoder().encode('{"parent":"minecraft:item/generated"}'), {level:9}],
  "assets/minecraft/textures/item/test.png": [new Uint8Array([137,80,78,71,13,10,26,10,0,0,0,0]), {level:0}]
};
(async()=>{
  fs.writeFileSync(process.argv[4], corruptZipCrc(fflate.zipSync(files)));
  const asyncZip = await new Promise((resolve,reject)=>fflate.zip(files,{level:9},(err,out)=>err?reject(err):resolve(out)));
  fs.writeFileSync(process.argv[5], corruptZipCrc(asyncZip));
})().catch(e=>{console.error(e);process.exit(1)});
''', encoding="utf-8")
            made = run([node, str(node_script), str(fflate_path), str(html_path), str(model_zip), str(item_zip)])
            report["checks"]["both_web_zip_generators"] = made.returncode == 0 and model_zip.exists() and item_zip.exists()
            if not report["checks"]["both_web_zip_generators"]:
                report["errors"].append("Không tạo được ZIP mẫu từ JS: " + made.stderr[-1000:])
            else:
                crc_results = {}
                for label, sample in (("model", model_zip), ("item", item_zip)):
                    bad = run([unzip, "-t", str(sample)])
                    detected = bad.returncode != 0 and "bad CRC" in (bad.stdout + bad.stderr)
                    crc_results[label] = detected
                    if not detected:
                        report["errors"].append(f"unzip không phát hiện Bad CRC ở ZIP {label}.")
                report["checks"]["unzip_reports_bad_crc_for_both"] = all(crc_results.values())
                report["unzip_bad_crc"] = crc_results

                java_src = td / "ReadZip.java"
                java_src.write_text(r'''import java.nio.file.*;
import java.util.zip.ZipFile;
public class ReadZip {
  public static void main(String[] args) throws Exception {
    Path p = Path.of(args[0]);
    try (ZipFile z = new ZipFile(p.toFile())) {
      String[] names = {"pack.mcmeta", "assets/minecraft/models/item/test.json", "assets/minecraft/textures/item/test.png"};
      for (String n : names) {
        var e = z.getEntry(n);
        if (e == null) throw new RuntimeException("Missing entry: " + n);
        try (var in = z.getInputStream(e)) {
          if (in.readAllBytes().length == 0) throw new RuntimeException("Empty entry: " + n);
        }
      }
    }
    try (FileSystem fs = FileSystems.newFileSystem(p)) {
      for (String n : new String[]{"/pack.mcmeta", "/assets/minecraft/models/item/test.json", "/assets/minecraft/textures/item/test.png"}) {
        if (!Files.isRegularFile(fs.getPath(n)) || Files.readAllBytes(fs.getPath(n)).length == 0)
          throw new RuntimeException("ZIP filesystem cannot read: " + n);
      }
    }
  }
}
''', encoding="utf-8")
                comp = run([javac, str(java_src)])
                report["checks"]["java_test_compile"] = comp.returncode == 0
                if comp.returncode:
                    report["errors"].append("Không biên dịch được test Java: " + comp.stderr[-1000:])
                else:
                    readable = {}
                    for label, sample in (("model", model_zip), ("item", item_zip)):
                        result = run([java, "-cp", str(td), "ReadZip", str(sample)])
                        readable[label] = result.returncode == 0
                        if result.returncode:
                            report["errors"].append(f"Java không đọc được ZIP {label}: " + result.stderr[-1000:])
                    report["checks"]["java_zipfile_and_zipfs_can_read_both"] = all(readable.values())
                    report["java_readable"] = readable
    report["notes"].append("Đã kiểm tra luồng tạo ZIP đồng bộ (Model) và bất đồng bộ (Item).")
    report["notes"].append("Chỉ kiểm tra Java ZipFile/ZipFS; chưa khởi chạy Minecraft client thật.")
    report["notes"].append("Bad CRC chỉ gây lỗi với trình giải nén xác minh CRC; dữ liệu vẫn có thể được trích xuất/repack.")
    report["notes"].append("Không phải mã hóa và không đảm bảo chống sao chép tuyệt đối.")
    report["ok"] = not report["errors"] and all(v is True for v in report["checks"].values())
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
