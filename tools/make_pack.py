#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
make_pack.py - rut gon VanGioi_Full_Pack.zip thanh pack/mobs.zip cho web.

Web chi can model quai/boss (assets/modelengine) + bang anh xa ia: -> texture.
Phan do vat/giap/HUD khong can => file nho hon nhieu, tai nhanh hon.
Dong thoi sua luon CRC/checksum PNG va ghi zip chuan.

Chay:   python3 make_pack.py VanGioi_Full_Pack.zip      -> pack/mobs.zip.001, .002 ...
        python3 make_pack.py VanGioi_Full_Pack.zip --single   -> 1 file pack/mobs.zip

Mac dinh chia thanh cac phan ~20 MB vi GitHub chi cho upload qua web file <= 25 MB.
Web tu tai cac phan roi ghep lai.
Khi server cap nhat pack: chay lai roi upload mobs.zip moi len host.
"""
import sys, os, re, json, zlib, struct, zipfile, argparse

ATLAS = "ia_overlay_legacy_atlas/assets/minecraft/atlases/blocks.json"


class RawZip:
    """Doc zip 'khoan dung' (pack server co header/CRC gia)."""
    def __init__(self, path):
        with open(path, "rb") as f:
            self.buf = f.read()
        zf = zipfile.ZipFile(path)
        self.info = {i.filename: i for i in zf.infolist() if not i.filename.endswith("/")}
        zf.close()

    def __contains__(self, n):
        return n in self.info

    def read(self, n):
        i = self.info[n]; b = self.buf; o = i.header_offset
        nl, el = struct.unpack("<HH", b[o + 26:o + 30]); st = o + 30 + nl + el
        if i.compress_type == 0:
            return b[st:st + i.compress_size]
        d = zlib.decompressobj(-15); out = []; p = st
        while not d.eof and p < len(b):
            out.append(d.decompress(b[p:p + 65536])); p += 65536
        return b"".join(out)


def _chunk(t, d):
    return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)


def fix_png(b):
    if b[:8] != b"\x89PNG\r\n\x1a\n":
        return b
    try:
        i, chs, idat, ok = 8, [], b"", True
        while i + 12 <= len(b):
            ln = struct.unpack(">I", b[i:i + 4])[0]
            typ, data = b[i + 4:i + 8], b[i + 8:i + 8 + ln]
            if struct.unpack(">I", b[i + 8 + ln:i + 12 + ln])[0] != (zlib.crc32(typ + data) & 0xFFFFFFFF):
                ok = False
            if typ == b"IDAT": idat += data
            elif typ != b"IEND": chs.append((typ, data))
            i += 12 + ln
        try:
            raw = zlib.decompress(idat)
        except Exception:
            ok = False
            raw = zlib.decompressobj(-15).decompress(idat[2:])
        if ok:
            return b
        out = bytearray(b[:8])
        for t, d in chs: out += _chunk(t, d)
        return bytes(out + _chunk(b"IDAT", zlib.compress(raw, 9)) + _chunk(b"IEND", b""))
    except Exception:
        return b


def tex_path(r):
    ns, p = r.split(":", 1) if ":" in r else ("minecraft", r)
    return "assets/%s/textures/%s.png" % (ns, p)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("full"); ap.add_argument("-o", "--out", default=os.path.join("pack", "mobs.zip"))
    ap.add_argument("--single", action="store_true", help="khong chia nho, chi tao 1 file mobs.zip")
    ap.add_argument("--split", type=int, default=20, help="dung luong moi phan (MB), mac dinh 20")
    a = ap.parse_args()
    print("Doc", a.full, "...")
    z = RawZip(a.full)
    sources = z.read(ATLAS)
    sources = json.loads(sources.decode("utf-8-sig"))["sources"] if ATLAS in z else []
    amap = {s["sprite"]: s for s in sources if "sprite" in s}
    files, used_sprites, used_res = {}, set(), set()
    rx = re.compile(r"^assets/modelengine/(models|items)/([^/]+)/(.+)\.json$")
    for n in sorted(z.info):
        m = rx.match(n)
        if not m: continue
        raw = z.read(n); files[n] = raw
        if m.group(1) != "models": continue
        try: d = json.loads(raw.decode("utf-8-sig"))
        except Exception: continue
        for v in (d.get("textures") or {}).values():
            if not isinstance(v, str) or v.startswith("#"): continue
            if v.startswith("ia:"):
                if v in amap: used_sprites.add(v); used_res.add(amap[v]["resource"])
            else:
                used_res.add(v)
    print("model:", sum(1 for n in files if "/models/" in n), "| texture can dung:", len(used_res))
    for r in sorted(used_res):
        p = tex_path(r)
        if p in z:
            files[p] = fix_png(z.read(p))
            if p + ".mcmeta" in z: files[p + ".mcmeta"] = z.read(p + ".mcmeta")
    files[ATLAS] = json.dumps({"sources": [amap[s] for s in sorted(used_sprites)]}, separators=(",", ":")).encode()
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    with zipfile.ZipFile(a.out, "w") as o:
        for n, data in files.items():
            png = n.endswith(".png")
            o.writestr(zipfile.ZipInfo(n, (2026, 1, 1, 0, 0, 0)), data,
                       compress_type=zipfile.ZIP_STORED if png else zipfile.ZIP_DEFLATED,
                       compresslevel=None if png else 9)
    print("Da tao %s (%.1f MB, %d file)" % (a.out, os.path.getsize(a.out) / 1048576, len(files)))
    if not a.single:
        data = open(a.out, "rb").read(); size = a.split * 1048576; n = 0
        for old in [f for f in os.listdir(os.path.dirname(os.path.abspath(a.out))) if re.match(r"^%s\.\d{3}$" % re.escape(os.path.basename(a.out)), f)]:
            os.remove(os.path.join(os.path.dirname(os.path.abspath(a.out)), old))
        for i in range(0, len(data), size):
            n += 1
            with open("%s.%03d" % (a.out, n), "wb") as f: f.write(data[i:i + size])
        os.remove(a.out)
        print("Da chia thanh %d phan: %s.001 ... %s.%03d" % (n, a.out, a.out, n))


if __name__ == "__main__":
    main()
