#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VanGioi Mob Studio
==================
Doc VanGioi_Full_Pack.zip, mo TRINH DUYET de xem truoc model (1 con hoac ca thu vien),
tick quai/boss, sua ten hien thi trong game, dat ten file, roi tao ra resource pack
nho chi chua cac con da tick.

  - KHONG gom do trong Item pack (ban dung item pack goc cua server)
  - KHONG gom am thanh
  - Doi "ia:1234" thanh duong dan texture that + them atlas rieng
    => ghep duoc voi item pack goc (vi so ia: cua Full va Item pack khac nhau)

Chay:      python3 vangioi_mob_pack.py
           (dat file zip cung thu muc; trinh duyet tu mo, Ctrl+C de tat)

Ten trong game: sua truc tiep tren trinh duyet (tu luu vao names.txt),
           hoac bam "Nhap ten..." de nap file .yml MythicMobs / names.txt / .json.

Lap rap dung vi tri: pack KHONG chua vi tri cac manh (nam trong blueprint cua
           ModelEngine tren server). Hay lay file .bbmodel trong
           plugins/ModelEngine/blueprints cua server, bam "Nap blueprint..." tren
           trinh duyet (hoac chep vao thu muc blueprints/ canh script).
           Ten file phai trung id model (tengu.bbmodel <-> tengu).

Che do khac (khong can trinh duyet):
           --tui                 giao dien terminal
           --list                in danh sach
           --select abyssal,...  --all   tao thang file zip
           --export-names        tao names.txt mau
"""
import sys, os, re, json, zlib, struct, zipfile, glob, argparse, collections, locale, unicodedata

ATLAS_PATHS = [
    "ia_overlay_legacy_atlas/assets/minecraft/atlases/blocks.json",
    "ia_overlay_modern_atlas/assets/minecraft/atlases/blocks.json",
    "ia_overlay_modern_atlas/assets/minecraft/atlases/items.json",
]

# ----------------------------------------------------------------- doc zip
class RawZip:
    """Doc zip kieu 'khoan dung': pack cua server co header/CRC/size gia
    nen zipfile thuong khong doc duoc. Ta chi dung central directory de lay
    offset, roi tu giai nen raw-deflate den het stream."""

    def __init__(self, path):
        self.path = path
        with open(path, "rb") as f:
            self.buf = f.read()
        zf = zipfile.ZipFile(path)
        self.info = {i.filename: i for i in zf.infolist() if not i.filename.endswith("/")}
        zf.close()

    def __contains__(self, name):
        return name in self.info

    def read(self, name):
        i = self.info[name]
        b, o = self.buf, i.header_offset
        nl, el = struct.unpack("<HH", b[o + 26:o + 30])
        st = o + 30 + nl + el
        if i.compress_type == 0:
            return b[st:st + i.compress_size]
        d = zlib.decompressobj(-15)
        out, p = [], st
        while not d.eof and p < len(b):
            out.append(d.decompress(b[p:p + 65536]))
            p += 65536
        return b"".join(out)

    def json(self, name):
        return json.loads(self.read(name).decode("utf-8-sig"))


# ----------------------------------------------------------------- png
def _chunk(t, d):
    return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)


def fix_png(b):
    """Pack goc co CRC/adler sai (chong giai nen). Game van doc duoc, nhung
    ta dung lai cho dung chuan de cac phan mem khac mo duoc."""
    if b[:8] != b"\x89PNG\r\n\x1a\n":
        return b
    try:
        i, chs, idat, ok = 8, [], b"", True
        while i + 12 <= len(b):
            ln = struct.unpack(">I", b[i:i + 4])[0]
            typ, data = b[i + 4:i + 8], b[i + 8:i + 8 + ln]
            crc = struct.unpack(">I", b[i + 8 + ln:i + 12 + ln])[0]
            if crc != (zlib.crc32(typ + data) & 0xFFFFFFFF):
                ok = False
            if typ == b"IDAT":
                idat += data
            elif typ != b"IEND":
                chs.append((typ, data))
            i += 12 + ln
        try:
            raw = zlib.decompress(idat)
        except Exception:
            ok = False
            raw = zlib.decompressobj(-15).decompress(idat[2:])
        if ok:
            return b
        out = bytearray(b[:8])
        for t, d in chs:
            out += _chunk(t, d)
        out += _chunk(b"IDAT", zlib.compress(raw, 9)) + _chunk(b"IEND", b"")
        return bytes(out)
    except Exception:
        return b


# ----------------------------------------------------------------- scan
def tex_path(res):
    ns, p = res.split(":", 1) if ":" in res else ("minecraft", res)
    return "assets/%s/textures/%s.png" % (ns, p)


def scan(full, item, dedupe=True, log=print):
    amap = {}
    for ap in ATLAS_PATHS:
        if ap in full:
            try:
                for s in full.json(ap)["sources"]:
                    if "sprite" in s and s["sprite"] not in amap:
                        amap[s["sprite"]] = s["resource"]
            except Exception as e:
                log("  ! khong doc duoc atlas %s: %s" % (ap, e))
    log("  atlas: %d sprite ia:" % len(amap))

    ids = collections.OrderedDict()
    def entry(i):
        return ids.setdefault(i, {"models": [], "items": [], "res": set(), "mbytes": 0, "unres": 0})

    for n in sorted(full.info):
        m = re.match(r"assets/modelengine/(models|items)/([^/]+)/(.+)\.json$", n)
        if m:
            entry(m.group(2))["models" if m.group(1) == "models" else "items"].append(n)
    log("  tim thay %d model boss/quai/vfx" % len(ids))

    for k, (i, e) in enumerate(ids.items()):
        for n in e["models"]:
            raw = full.read(n)
            e["mbytes"] += len(raw)
            try:
                d = json.loads(raw.decode("utf-8-sig"))
            except Exception:
                continue
            for v in d.get("textures", {}).values():
                if not isinstance(v, str) or v.startswith("#"):
                    continue
                if v.startswith("ia:"):
                    r = amap.get(v)
                    if r:
                        e["res"].add(r)
                    else:
                        e["unres"] += 1
                else:
                    e["res"].add(v)
        for n in e["items"]:
            e["mbytes"] += 100
        if k % 200 == 0:
            log("  quet model... %d/%d" % (k, len(ids)))

    # kich thuoc texture (that su, sau khi giai nen)
    allres = set().union(*[e["res"] for e in ids.values()]) if ids else set()
    tsize, intem, missing = {}, set(), set()
    for r in allres:
        p = tex_path(r)
        if dedupe and item is not None and p in item:
            intem.add(r)
            tsize[r] = 0
        elif p in full:
            tsize[r] = len(full.read(p))
        else:
            missing.add(r)
            tsize[r] = 0
    log("  texture: %d (da co trong Item pack: %d, thieu: %d)" % (len(allres), len(intem), len(missing)))
    return amap, ids, tsize, intem, missing


def family(i):
    return re.split(r"[_\-]", i)[0] or i


# ----------------------------------------------------------------- build
def build(full, ids, amap, sel, tsize, intem, missing, out, log=print):
    res_used = set()
    n_files = 0
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        z.writestr("pack.mcmeta", json.dumps({"pack": {
            "pack_format": 46, "supported_formats": [32, 9999],
            "description": "Van Gioi - Mob/Boss models (tu chon)"}}))
        for i in sel:
            e = ids[i]
            for n in e["models"]:
                try:
                    d = json.loads(full.read(n).decode("utf-8-sig"))
                except Exception:
                    z.writestr(n, full.read(n)); continue
                tx = d.get("textures")
                if isinstance(tx, dict):
                    for k, v in list(tx.items()):
                        if isinstance(v, str) and v.startswith("ia:") and v in amap:
                            tx[k] = amap[v]
                z.writestr(n, json.dumps(d, ensure_ascii=False, separators=(",", ":")))
                n_files += 1
            for n in e["items"]:
                z.writestr(n, full.read(n)); n_files += 1
            res_used |= e["res"]
        sources = []
        for r in sorted(res_used):
            if r in missing:
                continue
            sources.append({"type": "single", "resource": r})
            if r in intem:
                continue                      # texture da co trong Item pack
            p = tex_path(r)
            z.writestr(p, fix_png(full.read(p))); n_files += 1
            if p + ".mcmeta" in full:
                z.writestr(p + ".mcmeta", full.read(p + ".mcmeta")); n_files += 1
        atlas = json.dumps({"sources": sources}, separators=(",", ":"))
        z.writestr("assets/minecraft/atlases/blocks.json", atlas)   # 1.21.4
        z.writestr("assets/minecraft/atlases/items.json", atlas)    # 1.21.6+
    log("Da tao %s (%d file, %.1f MB)" % (out, n_files, os.path.getsize(out) / 1048576))


# ----------------------------------------------------------------- ten hien thi
def strip_accents(t):
    t = t.replace("\u0111", "d").replace("\u0110", "D")
    return "".join(c for c in unicodedata.normalize("NFD", t) if unicodedata.category(c) != "Mn")


def norm(t):
    return strip_accents(t).lower()


def clean_name(t):
    t = t.strip().strip("'\"")
    t = re.sub(r"[&\u00a7]#[0-9a-fA-F]{6}", "", t)
    t = re.sub(r"[&\u00a7][0-9a-fk-orA-FK-OR]", "", t)
    t = re.sub(r"<[^>]*>", "", t)
    return re.sub(r"\s+", " ", t).strip()


def scan_mythic(path):
    """Doc file .yml MythicMobs: lay Display + Model (ModelEngine) cua tung quai."""
    files = []
    if os.path.isdir(path):
        for r, _, fs in os.walk(path):
            files += [os.path.join(r, f) for f in fs if f.lower().endswith((".yml", ".yaml"))]
    else:
        files = [path]
    out = collections.OrderedDict()
    for fp in files:
        try:
            lines = open(fp, encoding="utf-8-sig", errors="replace").read().splitlines()
        except OSError:
            continue
        key, disp, model = None, None, None

        def flush():
            if key and model:
                nm = clean_name(disp) if disp else key
                lst = out.setdefault(model.lower(), [])
                if nm and nm not in lst:
                    lst.append(nm)

        for ln in lines:
            m = re.match(r"^([^\s#:][^:]*):\s*(#.*)?$", ln)
            if m:
                flush()
                key, disp, model = m.group(1).strip(), None, None
                continue
            m = re.match(r"^\s+Display:\s*(.+?)\s*$", ln)
            if m and disp is None:
                disp = m.group(1)
            m = re.match(r"^\s+(?:Model|ModelId|Id):\s*['\"]?([\w\-]+)", ln)
            if m and model is None and re.search(r"model", ln, re.I):
                model = m.group(1)
        flush()
    return {k: " / ".join(v) for k, v in out.items()}


def load_names(path):
    names = {}
    if not path or not os.path.exists(path):
        return names
    if os.path.isdir(path) or path.lower().endswith((".yml", ".yaml")):
        return scan_mythic(path)
    if path.lower().endswith(".json"):
        d = json.load(open(path, encoding="utf-8-sig"))
        return {str(k).lower(): clean_name(str(v)) for k, v in d.items() if v}
    for ln in open(path, encoding="utf-8-sig", errors="replace"):
        ln = ln.strip()
        if not ln or ln.startswith("#") or "=" not in ln:
            continue
        k, v = ln.split("=", 1)
        if v.strip():
            names[k.strip().lower()] = clean_name(v)
    return names


def load_pack_names(path):
    empty = {"models": {}, "items": {}, "sounds": {}, "soundEvents": {}}
    if not os.path.isfile(path):
        return empty
    try:
        with open(path, encoding="utf-8-sig") as stream:
            data = json.load(stream)
    except (OSError, ValueError) as error:
        print("  ! khong doc duoc pack names %s: %s" % (path, error))
        return empty
    if not isinstance(data, dict) or data.get("schemaVersion") != 1:
        return empty
    return {category: {str(key): clean_name(value) for key, value in (data.get(category) or {}).items()
                       if isinstance(value, str) and value.strip()}
            for category in empty}


def label(i, names):
    n = names.get(i.lower())
    return "%s  (%s)" % (n, i) if n else i


def matches(i, f, flt, names):
    return flt in i.lower() or flt in f.lower() or flt in norm(names.get(i.lower(), ""))


# ----------------------------------------------------------------- chon
def est_bytes(ids, tsize, sel):
    res = set()
    mb = 0
    for i in sel:
        res |= ids[i]["res"]
        mb += ids[i]["mbytes"]
    return mb + sum(tsize.get(r, 0) for r in res)


def run_tui(stdscr, ids, tsize, names):
    import curses
    curses.curs_set(0)
    fams = collections.OrderedDict()
    for i in sorted(ids):
        fams.setdefault(family(i), []).append(i)
    expanded, sel, flt, cur, top = set(), set(), "", 0, 0
    typing = False

    def rows():
        out = []
        for f, items in fams.items():
            m = [i for i in items if matches(i, f, flt, names)] if flt else items
            if not m:
                continue
            out.append(("f", f, m))
            if f in expanded or flt:
                for i in m:
                    out.append(("i", i, [i]))
        return out

    while True:
        R = rows()
        cur = max(0, min(cur, len(R) - 1))
        h, w = stdscr.getmaxyx()
        page = max(1, h - 5)
        if cur < top: top = cur
        if cur >= top + page: top = cur - page + 1
        stdscr.erase()
        mb = est_bytes(ids, tsize, sel) / 1048576
        stdscr.addnstr(0, 0, "VanGioi Mob Pack - tick quai/boss roi nhan ENTER de tao zip", w - 1, curses.A_BOLD)
        stdscr.addnstr(1, 0, "Len/Xuong | SPACE tick | Phai/Trai mo-dong | / tim | a tick het | n bo het | ENTER tao | q thoat", w - 1)
        stdscr.addnstr(2, 0, "Da chon: %d model  ~%.1f MB   Loc: %s%s" % (len(sel), mb, flt or "-", "_" if typing else ""), w - 1, curses.A_REVERSE)
        for k in range(page):
            ri = top + k
            if ri >= len(R): break
            kind, name, members = R[ri]
            n_sel = sum(1 for i in members if i in sel)
            box = "[x]" if n_sel == len(members) else ("[-]" if n_sel else "[ ]")
            if kind == "f":
                arrow = "v" if (name in expanded or flt) else ">"
                fb = sum(ids[i]["mbytes"] for i in members)
                line = "%s %s %s  (%d model)" % (arrow, box, label(name, names) if name in ids else name, len(members))
            else:
                line = "      %s %s" % (box, label(name, names))
            stdscr.addnstr(3 + k, 0, line, w - 1, curses.A_REVERSE if ri == cur else 0)
        stdscr.refresh()
        ch = stdscr.getch()
        if typing:
            if ch in (10, 13, curses.KEY_ENTER): typing = False
            elif ch == 27: typing, flt = False, ""
            elif ch in (curses.KEY_BACKSPACE, 127, 8): flt = flt[:-1]
            elif 32 <= ch < 127: flt += chr(ch).lower()   # go khong dau cung tim duoc ten co dau
            cur = top = 0
            continue
        if ch in (curses.KEY_UP, ord("k")): cur -= 1
        elif ch in (curses.KEY_DOWN, ord("j")): cur += 1
        elif ch == curses.KEY_PPAGE: cur -= page
        elif ch == curses.KEY_NPAGE: cur += page
        elif ch == curses.KEY_HOME: cur = 0
        elif ch == curses.KEY_END: cur = len(R) - 1
        elif ch == ord(" ") and R:
            _, _, mem = R[cur]
            if all(i in sel for i in mem): sel -= set(mem)
            else: sel |= set(mem)
        elif ch == curses.KEY_RIGHT and R and R[cur][0] == "f": expanded.add(R[cur][1])
        elif ch == curses.KEY_LEFT and R:
            f = R[cur][1] if R[cur][0] == "f" else family(R[cur][1])
            expanded.discard(f)
            if R[cur][0] == "i":
                for k2, r2 in enumerate(R):
                    if r2[0] == "f" and r2[1] == f: cur = k2; break
        elif ch == ord("/"): typing = True
        elif ch == 27: flt = ""
        elif ch == ord("a"):
            for _, _, mem in R: sel |= set(mem)
        elif ch == ord("n"): sel.clear()
        elif ch in (10, 13, curses.KEY_ENTER): return sorted(sel)
        elif ch == ord("q"): return None


def run_text(ids, tsize, names):
    fams = collections.OrderedDict()
    for i in sorted(ids):
        fams.setdefault(family(i), []).append(i)
    names = list(fams)
    for k, f in enumerate(names, 1):
        print("%3d. %-40s %d model" % (k, label(f, names) if f in ids else f, len(fams[f])))
    print("\nNhap so nhom (vd 3,5-8), hoac ten (vd abyssal), hoac 'all'. Enter de tao.")
    sel = set()
    while True:
        s = input("> ").strip().lower()
        if not s:
            return sorted(sel)
        for t in re.split(r"[,\s]+", s):
            if not t: continue
            if t == "all": sel |= set(ids)
            elif re.fullmatch(r"\d+(-\d+)?", t):
                a, _, b = t.partition("-"); b = b or a
                for k in range(int(a), int(b) + 1):
                    if 1 <= k <= len(names): sel |= set(fams[names[k - 1]])
            else:
                sel |= {i for i in ids if matches(i, family(i), t, names)}
        print("  da chon %d model (~%.1f MB). Nhap them hoac Enter de tao." % (len(sel), est_bytes(ids, tsize, sel) / 1048576))


# ----------------------------------------------------------------- web (trinh duyet)
import threading, webbrowser, base64, gzip, tempfile, http.server, urllib.parse


def get_scan(full, item, fp, ip, dedupe, here, log=print):
    """Quet pack (co cache de lan sau mo nhanh)."""
    def sig(p):
        if not p or not os.path.exists(p):
            return None
        st = os.stat(p)
        return [os.path.abspath(p), st.st_size, int(st.st_mtime)]
    key = {"v": 3, "full": sig(fp), "item": sig(ip) if dedupe else None, "dedupe": bool(dedupe)}
    cp = os.path.join(here, ".vangioi_cache.json")
    try:
        c = json.load(open(cp, encoding="utf-8"))
        if c.get("key") == key:
            ids = collections.OrderedDict()
            for k, e in c["ids"].items():
                e["res"] = set(e["res"])
                ids[k] = e
            log("  (dung cache quet lan truoc)")
            return c["amap"], ids, c["tsize"], set(c["intem"]), set(c["missing"])
    except Exception:
        pass
    amap, ids, tsize, intem, missing = scan(full, item, dedupe=dedupe, log=log)
    try:
        ser = {k: dict(e, res=sorted(e["res"])) for k, e in ids.items()}
        json.dump({"key": key, "amap": amap, "ids": ser, "tsize": tsize,
                   "intem": sorted(intem), "missing": sorted(missing)},
                  open(cp, "w", encoding="utf-8"), separators=(",", ":"))
    except Exception:
        pass
    return amap, ids, tsize, intem, missing


def save_names(path, names):
    with open(path, "w", encoding="utf-8") as f:
        f.write("# model_id = Ten hien thi trong game (tool tu luu khi ban sua tren trinh duyet)\n")
        for k in sorted(names):
            if names[k]:
                f.write("%s = %s\n" % (k, names[k]))


def parse_names_upload(name, text):
    low = name.lower()
    if low.endswith((".yml", ".yaml")):
        with tempfile.TemporaryDirectory() as td:
            fp = os.path.join(td, "x.yml")
            with open(fp, "w", encoding="utf-8") as f:
                f.write(text)
            return scan_mythic(fp)
    if low.endswith(".json"):
        d = json.loads(text.lstrip("\ufeff"))
        return {str(k).lower(): clean_name(str(v)) for k, v in d.items() if v}
    out = {}
    for ln in text.splitlines():
        ln = ln.strip()
        if ln and not ln.startswith("#") and "=" in ln:
            k, v = ln.split("=", 1)
            if v.strip():
                out[k.strip().lower()] = clean_name(v)
    return out


def bp_files():
    """Cac file blueprint (.bbmodel) trong thu muc blueprints/ canh script."""
    out = {}
    d = APP.bp_dir
    if os.path.isdir(d):
        for r, _, fs in os.walk(d):
            for f in fs:
                if f.lower().endswith((".bbmodel", ".json")):
                    out[os.path.splitext(f)[0].lower()] = os.path.join(r, f)
    return out


def load_host_blueprint(path, model_ids):
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, encoding="utf-8-sig") as stream:
            data = json.load(stream)
    except (OSError, ValueError) as error:
        print("  ! bo qua blueprint.json khong doc duoc: %s" % error)
        return {}
    if not isinstance(data, dict) or data.get("version") != 1 or not isinstance(data.get("models"), list):
        print("  ! bo qua blueprint.json sai schema")
        return {}
    valid_ids, order = set(model_ids), {}
    for row in data["models"]:
        if not isinstance(row, dict) or row.get("id") not in valid_ids or row["id"] in order:
            continue
        try:
            position = float(row.get("order"))
        except (TypeError, ValueError):
            continue
        if not __import__("math").isfinite(position):
            continue
        group = row.get("group")
        order[row["id"]] = {"order": position, "group": group.strip() if isinstance(group, str) and group.strip() else None}
    return order


def save_blueprint(name, text):
    tree = parse_bbmodel(text)
    if not tree:
        raise ValueError("%s: khong co bone (outliner) - can file .bbmodel cua Blockbench" % name)
    base = os.path.splitext(os.path.basename(name or "model"))[0]
    os.makedirs(APP.bp_dir, exist_ok=True)
    fn = re.sub(r"[^\w.\-]", "_", base, flags=re.U) + ".bbmodel"
    with open(os.path.join(APP.bp_dir, fn), "w", encoding="utf-8") as f:
        f.write(text)
    mid = os.path.splitext(fn)[0].lower()
    return {"id": mid, "bones": count_bones(tree), "matched": mid in APP.ids}


def parse_bbmodel(text):
    """Lay cay bone (group) tu Blockbench .bbmodel: ten, origin (pivot), rotation."""
    d = json.loads(text.lstrip("\ufeff"))

    def walk(nodes):
        out = []
        for n in nodes or []:
            if isinstance(n, dict):
                out.append({"name": str(n.get("name", "")),
                            "origin": n.get("origin") or [0, 0, 0],
                            "rotation": n.get("rotation") or [0, 0, 0],
                            "children": walk(n.get("children"))})
        return out
    return walk(d.get("outliner"))


def count_bones(t):
    return sum(1 + count_bones(n["children"]) for n in t)


class App(object):
    pass


APP = App()
_three = {}
_texcache = collections.OrderedDict()


def tex_bytes(r):
    if r in _texcache:
        return _texcache[r]
    p = tex_path(r)
    src = APP.full if p in APP.full else (APP.item if APP.item is not None and p in APP.item else None)
    if src is None:
        return None
    data = fix_png(src.read(p))
    W, H = struct.unpack(">II", data[16:24])
    fw, fh = W, H
    mc = p + ".mcmeta"
    if mc in src:
        try:
            an = json.loads(src.read(mc).decode("utf-8-sig")).get("animation")
        except Exception:
            an = None
        if an is not None:
            a, b = an.get("width"), an.get("height")
            if a is None and b is None: a = b = W
            elif a is None: a = W
            elif b is None: b = a
            fw, fh = min(int(a), W), min(int(b), H)
    _texcache[r] = (data, "%d,%d" % (fw, fh))
    if len(_texcache) > 400:
        _texcache.popitem(last=False)
    return _texcache[r]


def safe_name(n):
    n = re.sub(r"[^\w.\-]", "_", os.path.basename(n or ""), flags=re.U).strip("._") or "VanGioi_Mobs_Pack"
    return n if n.lower().endswith(".zip") else n + ".zip"


class Handler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="application/json; charset=utf-8", extra=None):
        if isinstance(body, (dict, list)):
            body = json.dumps(body, ensure_ascii=False).encode("utf-8")
        elif isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _body(self):
        n = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(n).decode("utf-8") or "{}")

    def do_GET(self):
        try:
            u = urllib.parse.urlparse(self.path)
            q = {k: v[0] for k, v in urllib.parse.parse_qs(u.query).items()}
            if u.path == "/":
                return self._send(200, INDEX_HTML, "text/html; charset=utf-8")
            if u.path == "/three.js":
                if "js" not in _three:
                    _three["js"] = gzip.decompress(base64.b64decode(THREE_GZ_B64))
                return self._send(200, _three["js"], "application/javascript")
            if u.path == "/api/list":
                res = sorted(APP.tsize)
                idx = {r: i for i, r in enumerate(res)}
                display_names = dict(APP.pack_names.get("models", {}))
                display_names.update(APP.names)
                blueprint = APP.host_blueprint
                model_ids = list(APP.ids)
                model_ids.sort(key=lambda mid: (0, blueprint[mid]["order"], mid) if mid in blueprint else (1, 0, mid))
                return self._send(200, {
                    "ids": [{"id": i, "fam": blueprint[i]["group"] if i in blueprint else None,
                             "parts": len(APP.ids[i]["models"]), "mb": APP.ids[i]["mbytes"],
                             "res": sorted(idx[r] for r in APP.ids[i]["res"] if r in idx)} for i in model_ids],
                    "res": [{"r": r, "b": APP.tsize.get(r, 0)} for r in res],
                    "names": display_names, "outName": APP.out_name, "bps": sorted(bp_files())})
            if u.path == "/api/items":
                if getattr(APP, "item_catalog", None) is None:
                    model_paths = {path for entry in APP.ids.values() for path in entry["models"]}
                    catalog = []
                    for group_id, model_entry in APP.ids.items():
                        for path in model_entry["items"]:
                            try:
                                document = APP.full.json(path)
                            except Exception:
                                continue
                            model_ref = ((document.get("model") or {}).get("model")
                                         if isinstance(document, dict) and isinstance(document.get("model"), dict) else None)
                            model_path = None
                            if isinstance(model_ref, str) and ":" in model_ref:
                                namespace, resource = model_ref.split(":", 1)
                                if re.fullmatch(r"[a-zA-Z0-9_.-]+", namespace) and ".." not in resource.split("/"):
                                    candidate = "assets/{}/models/{}.json".format(namespace, resource)
                                    if candidate in model_paths:
                                        model_path = candidate
                            model_id = model_path.split("/")[3] if model_path else None
                            item_name = path.split("/items/%s/" % group_id, 1)[-1][:-5]
                            item_label = APP.pack_names.get("items", {}).get(group_id + "/" + item_name) or \
                                         APP.pack_names.get("items", {}).get(group_id) or item_name
                            catalog.append({"groupId": group_id,
                                            "name": item_name, "displayName": item_label,
                                            "path": path, "modelRef": model_ref,
                                            "modelId": model_id,
                                            "part": model_path[:-5].split("/models/%s/" % model_id, 1)[-1] if model_id else None,
                                            "modelAvailable": bool(model_path)})
                    APP.item_catalog = catalog
                query = norm(q.get("q", "").strip())
                weapons_only = q.get("weapons") == "1"
                weapon_tokens = ("sword", "blade", "weapon", "bow", "crossbow", "spear", "dagger", "staff",
                                 "axe", "mace", "hammer", "scythe", "katana", "trident", "gun", "rifle",
                                 "shield", "claw", "saber", "rapier", "lance", "sickle", "whip", "wand",
                                 "flail", "knife", "pistol", "cannon")
                matches = []
                for entry in APP.item_catalog:
                    searchable = norm("%s %s %s %s" % (entry["groupId"], entry["name"],
                                                         entry.get("displayName", ""), entry["modelRef"] or ""))
                    if query and query not in searchable:
                        continue
                    if weapons_only and not any(token in searchable for token in weapon_tokens):
                        continue
                    matches.append(entry)
                try:
                    offset = max(0, int(q.get("offset", 0)))
                    limit = min(100, max(1, int(q.get("limit", 50))))
                except ValueError:
                    offset, limit = 0, 50
                return self._send(200, {"items": matches[offset:offset + limit],
                                        "total": len(matches), "offset": offset, "limit": limit})
            if u.path == "/api/model":
                i = q.get("id", "")
                if i not in APP.ids:
                    return self._send(404, "khong co model nay", "text/plain; charset=utf-8")
                parts = []
                for n in APP.ids[i]["models"]:
                    try:
                        d = json.loads(APP.full.read(n).decode("utf-8-sig"))
                    except Exception:
                        continue
                    tx = {k: (APP.amap.get(v, v) if isinstance(v, str) and v.startswith("ia:") else v)
                          for k, v in (d.get("textures") or {}).items()}
                    parts.append({"name": n.split("/models/%s/" % i, 1)[-1][:-5],
                                  "json": {"textures": tx, "elements": d.get("elements") or []}})
                wanted = q.get("part")
                if wanted:
                    parts = [part for part in parts if part["name"] == wanted]
                    if not parts:
                        return self._send(404, "khong co part nay", "text/plain; charset=utf-8")
                return self._send(200, {"parts": parts})
            if u.path == "/api/blueprint":
                fp = bp_files().get(q.get("id", "").lower())
                if not fp:
                    return self._send(404, "chua co blueprint", "text/plain; charset=utf-8")
                with open(fp, encoding="utf-8-sig", errors="replace") as f:
                    return self._send(200, {"tree": parse_bbmodel(f.read())})
            if u.path == "/api/tex":
                t = tex_bytes(q.get("res", ""))
                if not t:
                    return self._send(404, "khong co texture", "text/plain; charset=utf-8")
                return self._send(200, t[0], "image/png", {"X-Frame": t[1]})
            if u.path == "/download":
                fn = safe_name(q.get("name", ""))
                fp = os.path.join(APP.out_dir, fn)
                if not os.path.isfile(fp):
                    return self._send(404, "khong co file", "text/plain; charset=utf-8")
                with open(fp, "rb") as f:
                    data = f.read()
                return self._send(200, data, "application/zip",
                                  {"Content-Disposition": 'attachment; filename="%s"' % fn})
            self._send(404, "not found", "text/plain; charset=utf-8")
        except Exception as e:
            self._send(500, "%s: %s" % (type(e).__name__, e), "text/plain; charset=utf-8")

    def do_POST(self):
        try:
            u = urllib.parse.urlparse(self.path)
            d = self._body()
            if u.path == "/api/names":
                APP.names = {k.lower(): clean_name(str(v)) for k, v in (d.get("names") or {}).items() if str(v).strip()}
                save_names(APP.names_path, APP.names)
                return self._send(200, {"ok": True, "count": len(APP.names)})
            if u.path == "/api/import":
                got = {}
                for f in d.get("files", []):
                    got.update(parse_names_upload(f.get("name", ""), f.get("text", "")))
                APP.names.update(got)
                save_names(APP.names_path, APP.names)
                return self._send(200, {"names": got, "count": len(got)})
            if u.path == "/api/blueprint":
                items = []
                if d.get("zip_b64"):
                    import io
                    zf = zipfile.ZipFile(io.BytesIO(base64.b64decode(d["zip_b64"])))
                    for n in zf.namelist():
                        if n.lower().endswith(".bbmodel"):
                            try:
                                items.append(save_blueprint(n, zf.read(n).decode("utf-8-sig", "replace")))
                            except Exception:
                                pass
                    if not items:
                        return self._send(400, "zip khong co file .bbmodel hop le", "text/plain; charset=utf-8")
                    return self._send(200, {"items": items})
                return self._send(200, save_blueprint(d.get("name"), d.get("text", "")))
            if u.path == "/api/build":
                sel = [i for i in d.get("ids", []) if i in APP.ids]
                if not sel:
                    return self._send(400, "chua chon model nao", "text/plain; charset=utf-8")
                fn = safe_name(d.get("filename") or APP.out_name)
                out = os.path.join(APP.out_dir, fn)
                with APP.lock:
                    build(APP.full, APP.ids, APP.amap, sorted(sel), APP.tsize, APP.intem, APP.missing, out,
                          log=lambda *a: print(*a))
                return self._send(200, {"name": fn, "size": os.path.getsize(out), "dir": APP.out_dir})
            self._send(404, "not found", "text/plain; charset=utf-8")
        except Exception as e:
            self._send(500, "%s: %s" % (type(e).__name__, e), "text/plain; charset=utf-8")


def serve(port, open_browser):
    srv = None
    for p in range(port, port + 30):
        try:
            srv = http.server.ThreadingHTTPServer(("127.0.0.1", p), Handler)
            break
        except OSError:
            continue
    if srv is None:
        sys.exit("Khong mo duoc cong nao quanh %d." % port)
    url = "http://127.0.0.1:%d/" % srv.server_address[1]
    print("\n>>> Mo trinh duyet tai:  %s   (Ctrl+C de tat)" % url)
    if open_browser:
        threading.Timer(0.7, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nDa tat.")


# ----------------------------------------------------------------- main
def find(pattern, here):
    for d in (here, os.getcwd()):
        c = sorted(glob.glob(os.path.join(d, pattern)))
        if c:
            return c[0]
    return None


def main():
    ap = argparse.ArgumentParser(description="Tao resource pack chi chua model quai/boss tu VanGioi_Full_Pack.zip")
    ap.add_argument("full", nargs="?", help="duong dan VanGioi_Full_Pack.zip")
    ap.add_argument("--item", help="VanGioi_Item_Pack.zip (de bo texture trung)")
    ap.add_argument("--out", default="VanGioi_Mobs_Pack.zip", help="ten file zip dau ra")
    ap.add_argument("--names", help="names.txt / .json / thu muc MythicMobs (.yml) de hien ten trong game")
    ap.add_argument("--port", type=int, default=8765, help="cong cho giao dien trinh duyet")
    ap.add_argument("--no-browser", action="store_true", help="khong tu mo trinh duyet")
    ap.add_argument("--tui", action="store_true", help="dung giao dien terminal thay vi trinh duyet")
    ap.add_argument("--select", help="ten model/nhom, cach nhau bang dau phay (khong mo giao dien)")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--export-names", action="store_true", help="tao names.txt mau (id = ) de tu dien ten")
    ap.add_argument("--no-dedupe", action="store_true", help="khong bo texture da co trong Item pack")
    a = ap.parse_args()
    here = os.path.dirname(os.path.abspath(__file__))
    fp = a.full or find("*Full*.zip", here)
    if not fp or not os.path.exists(fp):
        sys.exit("Khong tim thay VanGioi_Full_Pack.zip - dat cung thu muc hoac truyen duong dan.")
    ip = a.item or find("*Item*.zip", here)
    print("Full pack :", fp)
    print("Item pack :", ip if ip and not a.no_dedupe else "(khong dung)")
    print("Dang doc pack (lan dau mat ~30 giay)...")
    full = RawZip(fp)
    item = RawZip(ip) if ip and os.path.exists(ip) and not a.no_dedupe else None
    amap, ids, tsize, intem, missing = get_scan(full, item, fp, ip, not a.no_dedupe, here)
    if not ids:
        sys.exit("Khong tim thay assets/modelengine/models trong pack.")
    names_file = os.path.join(here, "names.txt")
    npath = a.names or (names_file if os.path.exists(names_file) else None) or find("names.json", here)
    names = load_names(npath)
    pack_names = load_pack_names(os.path.join(here, "pack", "data", "names.json"))
    print("Ten hien thi:", ("%d ten tu %s" % (len(names), npath)) if names else "(chua co - nhap trong trinh duyet hoac xem huong dan dau file)")

    cli = a.tui or a.list or a.all or a.select or a.export_names
    if not cli:
        APP.full, APP.item, APP.ids, APP.amap = full, item, ids, amap
        APP.tsize, APP.intem, APP.missing = tsize, intem, missing
        APP.names, APP.names_path = dict(names), names_file
        APP.pack_names = pack_names
        APP.bp_dir = os.path.join(here, "blueprints")
        APP.host_blueprint = load_host_blueprint(os.path.join(here, "pack", "blueprint.json"), ids)
        APP.out_dir, APP.out_name, APP.lock = os.getcwd(), os.path.basename(a.out), threading.Lock()
        return serve(a.port, not a.no_browser)

    if a.export_names:
        outn = os.path.join(os.getcwd(), "names.txt")
        with open(outn, "w", encoding="utf-8") as f:
            f.write("# model_id = Ten hien thi trong game (dong de trong se bi bo qua)\n")
            for i in sorted(ids):
                f.write("%s = %s\n" % (i, names.get(i, "")))
        print("Da tao", outn); return
    if a.list:
        fams = collections.OrderedDict()
        for i in sorted(ids): fams.setdefault(family(i), []).append(i)
        for f, m in fams.items(): print("%-24s %s" % (f, ", ".join(label(x, names) for x in m)))
        return
    if a.all:
        sel = sorted(ids)
    elif a.select:
        toks = [t.strip().lower() for t in a.select.split(",") if t.strip()]
        sel = sorted({i for i in ids for t in toks if i == t or family(i) == t or i.startswith(t) or t in norm(names.get(i.lower(), ""))})
    else:
        try:
            import curses
            if not sys.stdout.isatty(): raise ImportError
            locale.setlocale(locale.LC_ALL, "")
            sel = curses.wrapper(run_tui, ids, tsize, names)
        except ImportError:
            sel = run_text(ids, tsize, names)
    if not sel:
        print("Chua chon gi - thoat."); return
    out = a.out if os.path.isabs(a.out) else os.path.join(os.getcwd(), a.out)
    print("Dang tao pack voi %d model..." % len(sel))
    build(full, ids, amap, sel, tsize, intem, missing, out)
    print("Xong! Bo file nay vao thu muc resourcepacks, dat tren/duoi Item pack deu duoc.")



# ----------------------------------------------------------------- tai nguyen nhung san
INDEX_HTML = r"""<!doctype html>
<html lang="vi"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>VanGioi Mob Studio</title>
<style>
:root{--bg:#14161a;--p:#1d2026;--p2:#252932;--bd:#323846;--tx:#e6e9ef;--mt:#8f98a8;--ac:#4f9cff;--ok:#3ecf8e}
*{box-sizing:border-box}
html,body{height:100%;margin:0;background:var(--bg);color:var(--tx);font:14px/1.4 system-ui,Segoe UI,Roboto,sans-serif}
header{display:flex;gap:10px;align-items:center;padding:8px 14px;background:var(--p);border-bottom:1px solid var(--bd)}
header h1{font-size:16px;margin:0 8px 0 0}
#mainTabs{display:flex;gap:4px;padding:3px;background:var(--bg);border:1px solid var(--bd);border-radius:8px}
#mainTabs button[aria-selected="true"]{background:var(--ac);border-color:var(--ac);color:#fff}
.model-control{display:inline-flex}
body.item-tab .model-control{display:none!important}
body.item-tab .sp{display:none}
.sp{flex:1}
button,input,select{font:inherit;color:var(--tx);background:var(--p2);border:1px solid var(--bd);border-radius:6px;padding:5px 9px}
button{cursor:pointer}button:hover{border-color:var(--ac)}
button.primary{background:var(--ac);border-color:var(--ac);color:#fff;font-weight:600}
button:disabled{opacity:.5;cursor:wait}
input[type=checkbox]{padding:0;width:16px;height:16px;accent-color:var(--ac)}
main{display:flex;height:calc(100% - 49px)}
aside{width:440px;min-width:320px;display:flex;flex-direction:column;border-right:1px solid var(--bd);background:var(--p)}
.tools{padding:8px;display:flex;flex-wrap:wrap;gap:6px;align-items:center;border-bottom:1px solid var(--bd)}
.tools #q{flex:1 1 100%}
.tools label{color:var(--mt);font-size:12px;display:flex;align-items:center;gap:4px}
.tools input[type=number]{width:52px}
#count{padding:6px 10px;color:var(--mt);font-size:12px;border-bottom:1px solid var(--bd)}
#list{flex:1;overflow:auto}
.fam{display:flex;align-items:center;gap:8px;padding:6px 10px;background:var(--p2);border-bottom:1px solid var(--bd);cursor:pointer}
.fam small{color:var(--mt)}.arr{width:12px;color:var(--mt)}
.row{display:grid;grid-template-columns:20px 1fr;gap:2px 8px;padding:5px 10px 5px 26px;border-bottom:1px solid #20242c;cursor:pointer}
.row:hover{background:#222733}.row.cur{background:#1f3556}
.row .nm{width:100%;padding:3px 7px;background:#171a20}
.row small{grid-column:2;color:var(--mt);font-size:11px}
section{flex:1;display:flex;flex-direction:column;min-width:0}
.vtools{display:flex;gap:14px;align-items:center;padding:7px 12px;border-bottom:1px solid var(--bd);background:var(--p);flex-wrap:wrap}
.vtools label{display:flex;align-items:center;gap:5px;color:var(--mt)}
#stage{flex:1;position:relative;min-height:200px;overflow:hidden}
#cv{position:absolute;inset:0;width:100%;height:100%;display:block;touch-action:none}
#hud{position:absolute;inset:0;pointer-events:none;overflow:hidden}
#hud span{position:absolute;transform:translate(-50%,-50%);font-size:11px;background:#000a;padding:1px 5px;border-radius:4px;white-space:nowrap}
#parts{padding:8px 12px;max-height:130px;overflow:auto;border-top:1px solid var(--bd);background:var(--p);display:flex;flex-wrap:wrap;gap:5px}
#parts button{padding:2px 8px;font-size:12px}#parts button.off{opacity:.4;text-decoration:line-through}
#info{padding:7px 12px;color:var(--mt);font-size:12px;border-top:1px solid var(--bd);background:var(--p)}
#gallery{position:absolute;inset:0;z-index:3;display:none;flex-direction:column;background:transparent}
#gbar{display:flex;gap:8px;align-items:center;padding:6px 12px;background:var(--p);border-bottom:1px solid var(--bd);flex-wrap:wrap}
#gwrap{flex:1;overflow:auto;display:grid;grid-template-columns:repeat(auto-fill,minmax(210px,1fr));gap:10px;padding:10px;align-content:start;grid-auto-rows:231px}
.tile{height:231px;border:1px solid var(--bd);border-radius:8px;overflow:hidden;background:transparent;cursor:pointer}
.tile:hover{border-color:var(--ac)}
.tbar{display:flex;align-items:center;gap:6px;padding:4px 8px;background:var(--p2)}
.tbar .tname{flex:1;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;font-size:12px}
.tbody{height:180px;background:transparent}
.tfoot{padding:3px 8px;background:var(--p2);font-size:11px;color:var(--mt);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.vtools select{padding:3px 6px}
#toast{position:fixed;right:16px;bottom:16px;max-width:420px;background:#0d2a1d;border:1px solid var(--ok);color:#c9f7e0;padding:10px 14px;border-radius:8px;display:none;white-space:pre-line}
#toast.err{background:#33191b;border-color:#e5484d;color:#ffd5d6}
#itemPanel{display:none;flex:1;min-width:0;min-height:0;flex-direction:column;padding:12px;overflow:auto}
#itemTools{display:flex;gap:8px;align-items:center;flex-wrap:wrap;padding-bottom:10px;border-bottom:1px solid var(--bd)}
#itemTools input[type=search]{flex:1 1 240px;min-width:0}
#itemStatus{padding:10px 2px;color:var(--mt);min-height:40px}
#itemResults{display:grid;grid-template-columns:repeat(auto-fill,minmax(min(330px,100%),1fr));gap:8px;align-content:start}
.item-result{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:4px 10px;padding:10px 12px;background:var(--p);border:1px solid var(--bd);border-radius:6px;min-width:0}
.item-result code,.item-result small{overflow-wrap:anywhere;min-width:0}
.item-result small{color:var(--mt);grid-column:1}
.item-result button{grid-column:2;grid-row:1/3;align-self:center}
#itemPages{display:flex;gap:10px;align-items:center;justify-content:center;padding:12px}
@media(max-width:760px){html,body{height:auto;min-height:100%;overflow-x:hidden;overflow-y:auto}body{min-height:100vh;min-height:100dvh}header{flex-wrap:wrap;padding:calc(8px + env(safe-area-inset-top)) 8px 8px}header h1{width:100%}#mainTabs{width:100%}#mainTabs button{flex:1}main{display:flex;flex-direction:column;height:auto;min-height:calc(100vh - 120px);min-height:calc(100dvh - 120px)}#modelPanel aside{width:100%;min-width:0;border-right:0;border-bottom:1px solid var(--bd)}#list{flex:0 0 auto;overflow:visible}#stage{min-height:48dvh}#parts{max-height:none;overflow:visible}#itemPanel{flex:0 0 auto;min-height:auto;overflow:visible;padding:8px 10px max(16px,env(safe-area-inset-bottom))}body.gallery-view #stage{flex:0 0 auto;height:auto;min-height:0;overflow:visible}body.gallery-view #gallery{position:relative;inset:auto;display:flex;min-height:0;overflow:visible}body.gallery-view #gwrap{flex:0 0 auto;overflow:visible}.item-result{grid-template-columns:minmax(0,1fr)}.item-result button{grid-column:1;grid-row:auto;justify-self:start}}
</style></head><body>
<header>
  <h1>VanGioi Mob Studio</h1>
    <nav id="mainTabs" role="tablist" aria-label="Khu vực dữ liệu">
        <button id="modelTab" type="button" role="tab" aria-selected="true">Model</button>
        <button id="itemsTab" type="button" role="tab" aria-selected="false">Item</button>
    </nav>
    <button id="btnSide" class="model-control" title="Ẩn / hiện bảng danh sách bên trái">◀ Ẩn danh sách</button>
    <button id="btnImport" class="model-control" title="Đọc tên từ file .yml MythicMobs / names.txt / .json">Nhập tên…</button>
    <input class="model-control" type="file" id="file" multiple hidden accept=".yml,.yaml,.txt,.json">
    <div class="sp model-control"></div>
    <label class="model-control" style="color:var(--mt)">Tên file&nbsp;<input id="outname" size="26"></label>
    <button id="btnBuild" class="primary model-control">Tạo ZIP</button>
</header>
<main id="modelPanel">
<aside>
  <div class="tools">
    <input id="q" placeholder="Tìm theo tên hoặc id (gõ không dấu cũng được)…">
    <label><input type="checkbox" id="hidefx"> Ẩn hiệu ứng (vfx/fx)</label>
    <label>≥ <input type="number" id="minparts" value="1" min="1"> mảnh</label>
    <button id="selvis">Tick tất cả đang hiện</button>
    <button id="clr">Bỏ tick hết</button>
  </div>
  <div id="count"></div>
  <div id="list"></div>
</aside>
<section>
  <div class="vtools">
    <label><input type="radio" name="view" value="single" checked> Xem 1 model</label>
    <label><input type="radio" name="view" value="gallery"> Thư viện (render nhiều model)</label>
    <span style="color:var(--bd)">|</span>
    <label><input type="radio" name="mode" value="grid" checked> Tách từng mảnh</label>
    <label><input type="radio" name="mode" value="overlay"> Ghép chồng</label>
    <label><input type="radio" name="mode" value="assembled"> Lắp ráp theo blueprint</label>
    <button id="btnBp" title="Nạp file .bbmodel hoặc .zip chứa nhiều .bbmodel (thư mục plugins/ModelEngine/blueprints của server)">Nạp blueprint…</button>
    <input type="file" id="bpfile" multiple hidden accept=".bbmodel,.json,.zip">
    <label><input type="checkbox" id="bprot" checked> xoay bone</label>
    <label><input type="checkbox" id="bp8" checked> tâm (8,8,8)</label>
    <label><input type="checkbox" id="frame" checked> Khung 16</label>
    <label><input type="checkbox" id="labels" checked> Nhãn</label>
    <button id="refit">Căn lại</button>
  </div>
  <div id="stage"><canvas id="cv"></canvas><div id="hud"></div>
    <div id="gallery"><div id="gbar">
      <button id="gfirst">«</button><button id="gprev">‹</button><span id="gpage"></span><button id="gnext">›</button><button id="glast">»</button>
      <label style="color:var(--mt)">mỗi trang <select id="gsize"><option>12</option><option selected>24</option><option>48</option></select></label>
      <button id="gtickpage">Tick cả trang</button>
      <span style="color:var(--mt);font-size:12px">Rê chuột vào ô để xoay · bấm vào hình để xem chi tiết</span></div>
      <div id="gwrap"></div></div></div>
  <div id="parts"></div>
  <div id="info">Bấm vào một dòng bên trái để xem model. Kéo chuột trái = xoay, chuột phải/Shift = dời, lăn chuột = zoom.</div>
</section>
</main>
<section id="itemPanel" role="tabpanel" aria-labelledby="itemsTab">
    <div id="itemTools"><input id="itemQuery" type="search" placeholder="Tìm tên vũ khí, item hoặc model…"><label><input id="weaponsOnly" type="checkbox"> Chỉ vũ khí</label><button id="itemRetry" type="button">Tìm</button></div>
    <div id="itemStatus" role="status" aria-live="polite">Nhập từ khóa hoặc mở tab để tải danh sách Item.</div>
    <div id="itemResults"></div>
    <div id="itemPages"><button id="itemPrev" type="button">Trang trước</button><span id="itemPageLabel"></span><button id="itemNext" type="button">Trang sau</button></div>
</section>
<div id="toast"></div>
<script src="/three.js"></script>
<script>
const $=s=>document.querySelector(s);
const esc=s=>String(s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const norm=t=>(t||'').normalize('NFD').replace(/[\u0300-\u036f]/g,'').replace(/đ/g,'d').replace(/Đ/g,'D').toLowerCase();
const fmt=b=>b>=1048576?(b/1048576).toFixed(1)+' MB':Math.max(1,Math.round(b/1024))+' KB';
const famOf=id=>id.split(/[_-]/)[0]||id;
const isFx=id=>/(^|[_-])(vfx|fx|effect|particle)([_-]|\d|$)/.test(id);
async function j(u,o){const r=await fetch(u,o);if(!r.ok)throw new Error((await r.text())||r.status);return r.json();}
function toast(t,err){const e=$('#toast');e.textContent=t;e.className=err?'err':'';e.style.display='block';clearTimeout(toast.t);toast.t=setTimeout(()=>e.style.display='none',err?9000:6000);}

let D=null,names={},sel=new Set(),cur=null,open=new Set(),groups=new Map();
try{sel=new Set(JSON.parse(localStorage.getItem('vg_sel')||'[]'));}catch(e){}
const saveSel=()=>{try{localStorage.setItem('vg_sel',JSON.stringify([...sel]))}catch(e){}};
let modelReady=null,itemPage=0,itemTotal=0,itemLoading=false,itemPending=false,itemTimer=null;
const itemPageSize=50;
function setWorkspace(tab){
    const items=tab==='items';document.body.classList.toggle('item-tab',items);document.body.classList.toggle('model-tab',!items);
    $('#modelTab').setAttribute('aria-selected',String(!items));$('#itemsTab').setAttribute('aria-selected',String(items));
    $('#modelPanel').style.display=items?'none':'flex';$('#itemPanel').style.display=items?'flex':'none';
    if(items)loadItems();else if(modelReady)return modelReady;
    return Promise.resolve();
}
async function loadItems(){
    if(itemLoading){itemPending=true;return;}itemLoading=true;$('#itemRetry').disabled=true;$('#itemStatus').textContent='Đang lọc danh sách item…';
    const query=$('#itemQuery').value.trim(),weapons=$('#weaponsOnly').checked;
    try{
        const params=new URLSearchParams({q:query,weapons:weapons?'1':'0',offset:String(itemPage*itemPageSize),limit:String(itemPageSize)});
        const response=await j('/api/items?'+params.toString());itemTotal=response.total;
        const list=$('#itemResults'),fragment=document.createDocumentFragment();
        for(const item of response.items){
            const row=document.createElement('div');row.className='item-result';
            const title=document.createElement('code');title.textContent=item.displayName&&item.displayName!==item.name?item.displayName+' ('+item.groupId+' / '+item.name+')':item.groupId+' / '+item.name;
            const ref=document.createElement('small');ref.textContent=item.modelRef||'Không có model reference';row.append(title,ref);
            if(item.modelAvailable&&item.modelId&&item.part){
                const button=document.createElement('button');button.type='button';button.textContent='Xem 3D';
                button.onclick=async()=>{try{await setWorkspace('model');preview(item.modelId,item.part);}catch(e){toast('Không mở được model: '+e.message,1);}};row.append(button);
            }else{const missing=document.createElement('small');missing.textContent='Không có mesh model khớp';row.append(missing);}
            fragment.append(row);
        }
        list.replaceChildren(fragment);
        const pages=Math.max(1,Math.ceil(itemTotal/itemPageSize));$('#itemPageLabel').textContent=`Trang ${itemPage+1}/${pages} · ${itemTotal} item`;
        $('#itemPrev').disabled=itemPage===0;$('#itemNext').disabled=itemPage>=pages-1;
        $('#itemStatus').textContent=itemTotal?`${itemTotal} item khớp${weapons?' · chỉ vũ khí':''}. Bấm “Xem 3D” để xem đúng mesh item.`:'Không có item phù hợp bộ lọc.';
    }catch(e){$('#itemStatus').textContent='Không tải được item: '+e.message;}
    finally{itemLoading=false;$('#itemRetry').disabled=false;if(itemPending){itemPending=false;loadItems();}}
}
$('#modelTab').onclick=()=>setWorkspace('model');$('#itemsTab').onclick=()=>setWorkspace('items');
$('#itemRetry').onclick=()=>loadItems();
$('#itemQuery').oninput=()=>{clearTimeout(itemTimer);itemTimer=setTimeout(()=>{itemPage=0;loadItems();},180);};
$('#weaponsOnly').onchange=()=>{itemPage=0;loadItems();};
$('#itemPrev').onclick=()=>{itemPage=Math.max(0,itemPage-1);loadItems();};
$('#itemNext').onclick=()=>{if((itemPage+1)*itemPageSize<itemTotal)itemPage++;loadItems();};

async function init(){
    D=await j('/api/list');D.bps=new Set(D.bps||[]);names=D.names||{};$('#outname').value=D.outName;
    D.byId={};D.ids.forEach(x=>{x.fam=x.fam||famOf(x.id);x.kb=x.mb+x.res.reduce((a,i)=>a+D.res[i].b,0);D.byId[x.id]=x;});
  sel=new Set([...sel].filter(i=>D.byId[i]));
  render();
}
function visible(){
  const q=norm($('#q').value.trim()),hf=$('#hidefx').checked,mp=+$('#minparts').value||1;
  return D.ids.filter(x=>x.parts>=mp&&!(hf&&isFx(x.id))&&(!q||norm(x.id).includes(q)||norm(names[x.id]||'').includes(q)||norm(x.fam).includes(q)));
}
function estimate(){let m=0;const rs=new Set();sel.forEach(id=>{const x=D.byId[id];m+=x.mb;x.res.forEach(i=>rs.add(i));});rs.forEach(i=>m+=D.res[i].b);return m;}
function updateCount(){
  const n=sel.size,e=estimate();
  $('#count').textContent=`Đã tick ${n} model · ước tính ~${fmt(e)} · đang hiện ${[...groups.values()].reduce((a,m)=>a+m.length,0)}/${D.ids.length}`;
  $('#btnBuild').textContent=n?`Tạo ZIP (${n} model, ~${fmt(e)})`:'Tạo ZIP';
}
function rowHtml(x){
  return `<div class="row${cur===x.id?' cur':''}" data-id="${esc(x.id)}"><input type="checkbox" class="cb" ${sel.has(x.id)?'checked':''}>`+
  `<input class="nm" value="${esc(names[x.id]||'')}" placeholder="${esc(x.id)}"><small>${esc(x.id)} · ${x.parts} mảnh · ${fmt(x.kb)}</small></div>`;
}
let render=function(){
  const vis=visible();groups=new Map();
  vis.forEach(x=>{if(!groups.has(x.fam))groups.set(x.fam,[]);groups.get(x.fam).push(x);});
  const q=$('#q').value.trim();let h='';
  for(const [f,m] of groups){
    const n=m.filter(x=>sel.has(x.id)).length,st=n==0?0:n==m.length?2:1,ex=open.has(f)||q;
    h+=`<div class="fam" data-f="${esc(f)}"><span class="arr">${ex?'▾':'▸'}</span><input type="checkbox" class="fcb" data-st="${st}" ${st==2?'checked':''}><b>${esc(names[f]||f)}</b><small>${m.length} model</small></div>`;
    if(ex)m.forEach(x=>h+=rowHtml(x));
  }
  const sc=$('#list').scrollTop;$('#list').innerHTML=h||'<div style="padding:16px;color:var(--mt)">Không có kết quả.</div>';$('#list').scrollTop=sc;
  document.querySelectorAll('.fcb').forEach(c=>c.indeterminate=c.dataset.st==='1');
  updateCount();
}
$('#list').addEventListener('click',e=>{
  const t=e.target,fam=t.closest('.fam'),row=t.closest('.row');
  if(t.classList.contains('nm'))return;
  if(fam){const f=fam.dataset.f;
    if(t.classList.contains('fcb')){const m=groups.get(f)||[];const all=m.every(x=>sel.has(x.id));m.forEach(x=>all?sel.delete(x.id):sel.add(x.id));saveSel();render();return;}
    open.has(f)?open.delete(f):open.add(f);render();return;}
  if(row){const id=row.dataset.id;
    if(t.classList.contains('cb')){t.checked?sel.add(id):sel.delete(id);saveSel();
      const f=D.byId[id].fam,fe=document.querySelector(`.fam[data-f="${CSS.escape(f)}"] .fcb`);
      if(fe){const m=groups.get(f)||[],n=m.filter(x=>sel.has(x.id)).length;fe.checked=n==m.length;fe.indeterminate=n>0&&n<m.length;}
      updateCount();return;}
    preview(id);}
});
let sv;
$('#list').addEventListener('input',e=>{
  if(!e.target.classList.contains('nm'))return;
  const id=e.target.closest('.row').dataset.id;names[id]=e.target.value.trim();
  clearTimeout(sv);sv=setTimeout(saveNames,500);
});
$('#list').addEventListener('keydown',e=>{if(e.key==='Enter'&&e.target.classList.contains('nm'))e.target.blur();});
async function saveNames(){try{await j('/api/names',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({names})});}catch(e){toast('Không lưu được tên: '+e.message,1);}}
let qt;$('#q').oninput=()=>{clearTimeout(qt);qt=setTimeout(render,150);};
$('#hidefx').onchange=$('#minparts').oninput=render;
$('#selvis').onclick=()=>{for(const m of groups.values())m.forEach(x=>sel.add(x.id));saveSel();render();};
$('#clr').onclick=()=>{sel.clear();saveSel();render();};
$('#btnImport').onclick=()=>$('#file').click();
$('#file').onchange=async e=>{
  const files=[...e.target.files];if(!files.length)return;
  const out=[];for(const f of files)out.push({name:f.name,text:await f.text()});
  try{const r=await j('/api/import',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({files:out})});
    Object.assign(names,r.names);render();toast(`Đã nhập ${r.count} tên.`);}catch(err){toast('Lỗi nhập tên: '+err.message,1);}
  e.target.value='';
};
$('#btnBuild').onclick=async()=>{
  if(!sel.size)return toast('Chưa tick con nào.',1);
  const b=$('#btnBuild');b.disabled=true;const old=b.textContent;b.textContent='Đang tạo…';
  try{await saveNames();
    const r=await j('/api/build',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({ids:[...sel],filename:$('#outname').value})});
    toast(`Đã tạo ${r.name} (${fmt(r.size)})\nLưu tại: ${r.dir}\nTrình duyệt sẽ tải về luôn.`);
    location.href='/download?name='+encodeURIComponent(r.name);
  }catch(err){toast('Lỗi tạo ZIP: '+err.message,1);}
  b.disabled=false;b.textContent=old;updateCount();
};

/* ------------------------------------------------------------ 3D */
const cv=$('#cv'),renderer=new THREE.WebGLRenderer({canvas:cv,antialias:true});
renderer.outputEncoding=THREE.sRGBEncoding;
const scene=new THREE.Scene();scene.background=new THREE.Color(0x1b1d22);
const cam=new THREE.PerspectiveCamera(40,1,0.1,8000);
const orb={th:-0.6,ph:1.15,d:60,t:new THREE.Vector3(8,8,8)};
function placeCam(c,o){const s=Math.sin(o.ph);c.position.set(o.t.x+o.d*s*Math.sin(o.th),o.t.y+o.d*Math.cos(o.ph),o.t.z+o.d*s*Math.cos(o.th));c.lookAt(o.t);c.updateMatrixWorld();}
const boxLine=new THREE.LineSegments(new THREE.EdgesGeometry(new THREE.BoxGeometry(16,16,16)),new THREE.LineBasicMaterial({color:0x4f9cff,transparent:true,opacity:.55}));
boxLine.position.set(8,8,8);scene.add(boxLine);
const grid=new THREE.GridHelper(64,16,0x39414f,0x2a303b);grid.position.set(8,0,8);scene.add(grid);
const root=new THREE.Group();scene.add(root);
function resize(){const r=$('#stage').getBoundingClientRect();renderer.setPixelRatio(Math.min(devicePixelRatio||1,2));renderer.setSize(r.width,r.height,false);cam.aspect=r.width/Math.max(1,r.height);cam.updateProjectionMatrix();gal.dirty=true;}
let drag=null;
cv.addEventListener('pointerdown',e=>{drag={x:e.clientX,y:e.clientY,pan:e.button!==0||e.shiftKey};cv.setPointerCapture(e.pointerId);});
cv.addEventListener('pointerup',()=>drag=null);
cv.addEventListener('contextmenu',e=>e.preventDefault());
cv.addEventListener('pointermove',e=>{
  if(!drag)return;const dx=e.clientX-drag.x,dy=e.clientY-drag.y;drag.x=e.clientX;drag.y=e.clientY;
  if(drag.pan){const k=orb.d*0.0016,m=cam.matrixWorld.elements;
    orb.t.x+=(-m[0]*dx+m[4]*dy)*k;orb.t.y+=(-m[1]*dx+m[5]*dy)*k;orb.t.z+=(-m[2]*dx+m[6]*dy)*k;}
  else{orb.th-=dx*0.01;orb.ph=Math.min(3.09,Math.max(0.05,orb.ph-dy*0.01));}
});
cv.addEventListener('wheel',e=>{e.preventDefault();orb.d=Math.min(4000,Math.max(3,orb.d*Math.exp(e.deltaY*0.0012)));},{passive:false});

/* mặt: [x,y,z] = 0 -> min, 1 -> max (đúng thứ tự đỉnh của Minecraft) */
const FACE={
 down:[[0,0,1],[0,0,0],[1,0,0],[1,0,1]],
 up:[[0,1,0],[0,1,1],[1,1,1],[1,1,0]],
 north:[[1,1,0],[1,0,0],[0,0,0],[0,1,0]],
 south:[[0,1,1],[0,0,1],[1,0,1],[1,1,1]],
 west:[[0,1,0],[0,0,0],[0,0,1],[0,1,1]],
 east:[[1,1,1],[1,0,1],[1,0,0],[1,1,0]]};
function defUV(d,f,t){switch(d){
 case 'down':return[f[0],16-t[2],t[0],16-f[2]];
 case 'up':return[f[0],f[2],t[0],t[2]];
 case 'north':return[16-t[0],16-t[1],16-f[0],16-f[1]];
 case 'south':return[f[0],16-t[1],t[0],16-f[1]];
 case 'west':return[f[2],16-t[1],t[2],16-f[1]];
 default:return[16-t[2],16-t[1],16-f[2],16-f[1]];}}
function rotPoint(p,r){
  if(!r||!r.angle)return p;const o=r.origin||[8,8,8],a=r.angle*Math.PI/180,c=Math.cos(a),s=Math.sin(a);
  let x=p[0]-o[0],y=p[1]-o[1],z=p[2]-o[2],t;
  if(r.axis==='x'){t=y*c-z*s;z=y*s+z*c;y=t;}
  else if(r.axis==='y'){t=x*c+z*s;z=-x*s+z*c;x=t;}
  else{t=x*c-y*s;y=x*s+y*c;x=t;}
  return[x+o[0],y+o[1],z+o[2]];}
function resolveTex(T,v){let n=0;while(typeof v==='string'&&v[0]==='#'&&n++<10)v=T[v.slice(1)];return typeof v==='string'?v:null;}
function buildPart(json,texs){
  const T=json.textures||{},B=new Map();
  (json.elements||[]).forEach(el=>{
    const f=el.from,t=el.to;if(!f||!t)return;
    for(const d in(el.faces||{})){
      const fc=el.faces[d],fd=FACE[d];if(!fd)continue;
      const key=resolveTex(T,fc.texture)||'?';
      if(!B.has(key))B.set(key,{p:[],u:[],i:[]});const b=B.get(key);
      const uv=fc.uv||defUV(d,f,t),k=(((fc.rotation||0)/90)|0)%4,base=b.p.length/3;
      for(let i=0;i<4;i++){
        const c=fd[i],p=rotPoint([c[0]?t[0]:f[0],c[1]?t[1]:f[1],c[2]?t[2]:f[2]],el.rotation);
        b.p.push(p[0],p[1],p[2]);
        const jx=(i+k)%4;b.u.push((jx<2?uv[0]:uv[2])/16,((jx==0||jx==3)?uv[1]:uv[3])/16);
      }
      b.i.push(base,base+1,base+2,base,base+2,base+3);
    }});
  if(!B.size)return null;
  const g=new THREE.Group();
  for(const [key,b] of B){
    const geo=new THREE.BufferGeometry();
    geo.setAttribute('position',new THREE.Float32BufferAttribute(b.p,3));
    geo.setAttribute('uv',new THREE.Float32BufferAttribute(b.u,2));geo.setIndex(b.i);
    const tx=texs[key];
    g.add(new THREE.Mesh(geo,new THREE.MeshBasicMaterial({map:tx||null,color:tx?0xffffff:0xff00ff,transparent:true,alphaTest:0.05,side:THREE.DoubleSide})));
  }
  g.updateMatrixWorld(true);
  const box=new THREE.Box3().setFromObject(g),size=box.getSize(new THREE.Vector3()),center=box.getCenter(new THREE.Vector3());
  return{group:g,size:Math.max(size.x,size.y,size.z,1),center};
}
const texCache=new Map();
function loadTex(r){
  if(texCache.size>500){texCache.forEach(p=>p.then(t=>t&&t.dispose()));texCache.clear();}
  if(!texCache.has(r))texCache.set(r,(async()=>{try{
    const res=await fetch('/api/tex?res='+encodeURIComponent(r));if(!res.ok)return null;
    const fr=(res.headers.get('X-Frame')||'').split(',').map(Number);
    const bm=await createImageBitmap(await res.blob());
    const fw=fr[0]||bm.width,fh=fr[1]||bm.height,c=document.createElement('canvas');c.width=fw;c.height=fh;
    c.getContext('2d').drawImage(bm,0,0,fw,fh,0,0,fw,fh);
    const t=new THREE.CanvasTexture(c);t.flipY=false;t.generateMipmaps=false;
    t.magFilter=t.minFilter=THREE.NearestFilter;t.encoding=THREE.sRGBEncoding;return t;
  }catch(e){return null;}})());
  return texCache.get(r);
}
async function fetchParts(id,onlyPart=null){
    const suffix=onlyPart?'&part='+encodeURIComponent(onlyPart):'';
    const m=await j('/api/model?id='+encodeURIComponent(id)+suffix),rs=new Set();
  m.parts.forEach(p=>Object.values(p.json.textures||{}).forEach(v=>{if(typeof v==='string'&&v[0]!=='#')rs.add(v);}));
  const texs={};await Promise.all([...rs].map(async r=>texs[r]=await loadTex(r)));
    const out=[];m.parts.forEach(p=>{const b=buildPart(p.json,texs);if(b){b.name=p.name;b.visible=true;out.push(b);}});
  return{parts:out,texCount:rs.size,missing:[...rs].filter(r=>!texs[r]).length};
}
function disposeGroup(g){g.traverse(o=>{if(o.geometry)o.geometry.dispose();if(o.material)o.material.dispose();});}

/* ----------------------------------------------- blueprint (.bbmodel) */
const bpCache=new Map(),bn=s=>String(s||'').toLowerCase().replace(/[^a-z0-9_]/g,'');
async function getBP(id){
  if(!D.bps.has(id))return null;
  if(!bpCache.has(id))bpCache.set(id,(await j('/api/blueprint?id='+encodeURIComponent(id))).tree);
  return bpCache.get(id);
}
function bpMats(tree){
  const rot=$('#bprot').checked,base=$('#bp8').checked?8:0,m=new Map(),rad=Math.PI/180;
  const walk=(n,P)=>{
    const o=n.origin||[0,0,0],r=n.rotation||[0,0,0];
    const T=new THREE.Matrix4().makeTranslation(o[0],o[1],o[2]),Ti=new THREE.Matrix4().makeTranslation(-o[0],-o[1],-o[2]);
    const R=new THREE.Matrix4();if(rot)R.makeRotationFromEuler(new THREE.Euler(r[0]*rad,r[1]*rad,r[2]*rad,'ZYX'));
    const M=P.clone().multiply(T).multiply(R).multiply(Ti);
    const Mp=M.clone().multiply(new THREE.Matrix4().makeTranslation(o[0]-base,o[1]-base,o[2]-base));
    const k=bn(n.name);if(k&&!m.has(k))m.set(k,Mp);
    (n.children||[]).forEach(c=>walk(c,M));
  };
  (tree||[]).forEach(n=>walk(n,new THREE.Matrix4()));
  return m;
}
/* đặt các mảnh theo chế độ; trả về số mảnh không có trong blueprint */
function placeParts(list,mode,tree){
  const vis=list.filter(p=>p.visible);let unplaced=0;
  list.forEach(p=>{p.group.matrixAutoUpdate=true;p.group.position.set(0,0,0);p.group.updateMatrix();p.group.visible=p.visible;});
  if(mode==='grid'){
    const step=Math.max(16,...vis.map(p=>p.size))*1.2,cols=Math.max(1,Math.ceil(Math.sqrt(vis.length)));
    vis.forEach((p,i)=>p.group.position.set((i%cols)*step-p.center.x+8,-p.center.y+Math.min(p.size,16)/2,Math.floor(i/cols)*step-p.center.z+8));
    }else if(mode==='assembled'&&tree){
    const mats=bpMats(tree);
    list.forEach(p=>{const M=mats.get(bn(p.name));
      if(M){p.group.matrixAutoUpdate=false;p.group.matrix.copy(M);p.group.matrixWorldNeedsUpdate=true;}else unplaced++;});
  }
  list.forEach(p=>p.group.updateMatrixWorld(true));
  return unplaced;
}
function boxOf(list){const b=new THREE.Box3();let any=false;list.forEach(p=>{if(p.visible){b.expandByObject(p.group);any=true;}});return any?b:null;}
const curMode=()=>document.querySelector('input[name=mode]:checked').value;

/* ----------------------------------------------- xem 1 model */
let parts=[],token=0,labelEls=[],curBP=null,view='single';
function clearParts(){while(root.children.length){const c=root.children.pop();disposeGroup(c);}parts=[];}
async function preview(id,onlyPart=null){
  cur=id;document.querySelectorAll('.row').forEach(r=>r.classList.toggle('cur',r.dataset.id===id));
    const my=++token;$('#info').textContent='Đang tải '+(onlyPart?onlyPart+' · ':'')+id+'…';
  try{
        const r=await fetchParts(id,onlyPart);curBP=onlyPart?null:await getBP(id);
    if(my!==token)return;
        if(onlyPart)document.querySelector('input[name=mode][value=grid]').checked=true;
    clearParts();parts=r.parts;parts.forEach(p=>root.add(p.group));
    layout(true);renderChips();
    const nm=names[id]?`${names[id]} (${id})`:id;
    infoBase=`${onlyPart?'Item '+onlyPart+' · ':''}${nm} — ${parts.length} mảnh có hình, ${r.texCount} texture${r.missing?`, ${r.missing} texture thiếu (hiện màu tím)`:''}. `;
    updInfo();
  }catch(e){$('#info').textContent='Lỗi: '+e.message;}
}
let infoBase='',lastUnplaced=0;
function updInfo(){
  if(!cur)return;const m=curMode();let t=infoBase;
  if(m==='assembled'){t+=curBP?(lastUnplaced?`Đã lắp theo blueprint; ${lastUnplaced} mảnh không có trong blueprint (nằm ở gốc). `:'Đã lắp theo blueprint. '):
    'Chưa có blueprint cho model này — bấm "Nạp blueprint…" (file .bbmodel). ';
    t+='Nếu lệch, thử đổi "xoay bone" / "tâm (8,8,8)".';}
    else t+='Tách từng mảnh hoặc ghép chồng; để lắp đúng vị trí, nạp blueprint ModelEngine rồi chọn "Lắp ráp theo blueprint".';
  $('#info').textContent=t;
}
function layout(fit){
  const mode=curMode();let eff=mode;
  if(mode==='assembled'&&!curBP)eff='overlay';
  lastUnplaced=placeParts(parts,eff,curBP);
    boxLine.visible=$('#frame').checked&&eff!=='grid';grid.visible=eff!=='grid';
  if(fit)fitCam();
  const hud=$('#hud');hud.innerHTML='';labelEls=[];
  if(eff==='grid')parts.filter(p=>p.visible).forEach(p=>{const s=document.createElement('span');s.textContent=p.name;hud.appendChild(s);labelEls.push([s,p]);});
  updInfo();
}
function fitCam(){
  root.updateMatrixWorld(true);const box=boxOf(parts);if(!box)return;
  const c=box.getCenter(new THREE.Vector3()),s=box.getSize(new THREE.Vector3());
  orb.t.copy(c);orb.d=Math.max(20,Math.max(s.x,s.y,s.z)*(curMode()==='grid'?1.15:1.7));
}
function renderChips(){
  const w=$('#parts');w.innerHTML='';
  const mk=(t,fn,cls)=>{const b=document.createElement('button');b.textContent=t;if(cls)b.className=cls;b.onclick=fn;w.appendChild(b);return b;};
  mk('Hiện hết',()=>{parts.forEach(p=>p.visible=true);layout(true);renderChips();});
  mk('Ẩn hết',()=>{parts.forEach(p=>p.visible=false);layout();renderChips();});
    parts.forEach(p=>{const b=mk(p.name,()=>{p.visible=!p.visible;layout();renderChips();},p.visible?'':'off');b.title='Bấm: ẩn/hiện';});
}

/* ----------------------------------------------- thư viện (nhiều model) */
const gal={page:0,size:24,tiles:[],dirty:true,hover:null,sig:''};
function disposeTiles(){gal.tiles.forEach(t=>{t.parts.forEach(p=>disposeGroup(p.group));t.dead=true;});gal.tiles=[];gal.hover=null;}
function tileName(id){return names[id]||id;}
function buildGallery(resetPage){
  disposeTiles();const vis=visible(),n=Math.max(1,Math.ceil(vis.length/gal.size));
  if(resetPage)gal.page=0;gal.page=Math.min(gal.page,n-1);
  $('#gpage').textContent=`Trang ${gal.page+1}/${n} · ${vis.length} model`;
  const gw=$('#gwrap');gw.innerHTML='';gw.scrollTop=0;
  vis.slice(gal.page*gal.size,(gal.page+1)*gal.size).forEach(x=>{
    const el=document.createElement('div');el.className='tile';el.dataset.id=x.id;
    el.innerHTML=`<div class="tbar"><input type="checkbox" class="tcb" ${sel.has(x.id)?'checked':''}><span class="tname">${esc(tileName(x.id))}</span></div><div class="tbody"></div><div class="tfoot">${esc(x.id)} · ${x.parts} mảnh · ${fmt(x.kb)}</div>`;
    gw.appendChild(el);
    const t={id:x.id,el,body:el.querySelector('.tbody'),scene:new THREE.Scene(),cam:new THREE.PerspectiveCamera(40,1,0.1,8000),parts:[],o:{th:-0.6,ph:1.15,d:60,t:new THREE.Vector3()},loaded:false,bp:null};
    gal.tiles.push(t);
  });
  gal.dirty=true;
  (async()=>{for(const t of [...gal.tiles]){if(t.dead)return;await loadTile(t);}})();
}
async function loadTile(t){
  try{
    const r=await fetchParts(t.id);if(t.dead){r.parts.forEach(p=>disposeGroup(p.group));return;}
    t.bp=await getBP(t.id);t.parts=r.parts;r.parts.forEach(p=>t.scene.add(p.group));
    t.loaded=true;layoutTile(t);
  }catch(e){}
  gal.dirty=true;
}
function layoutTile(t){
    const m=curMode(),eff=(m==='assembled'&&t.bp)?'assembled':(m==='overlay'?'overlay':'grid');
  placeParts(t.parts,eff,t.bp);t.scene.updateMatrixWorld(true);
  const b=boxOf(t.parts);if(!b)return;const c=b.getCenter(new THREE.Vector3()),s=b.getSize(new THREE.Vector3());
  t.o.t.copy(c);t.o.d=Math.max(14,Math.max(s.x,s.y,s.z)*((m==='grid'&&eff==='grid')?1.3:1.9));
}
function relayoutTiles(){gal.tiles.forEach(t=>t.loaded&&layoutTile(t));gal.dirty=true;}
function syncTiles(){gal.tiles.forEach(t=>{t.el.querySelector('.tcb').checked=sel.has(t.id);t.el.querySelector('.tname').textContent=tileName(t.id);});}
function galRender(){
  if(!gal.dirty&&!gal.hover)return;gal.dirty=false;
  const cr=cv.getBoundingClientRect();
  renderer.setScissorTest(false);renderer.setClearColor(0x14161a,1);renderer.clear();
  renderer.setScissorTest(true);
  for(const t of gal.tiles){
    const r=t.body.getBoundingClientRect();if(r.bottom<cr.top||r.top>cr.bottom||r.width<2||r.height<2)continue;
    const x=r.left-cr.left,y=cr.bottom-r.bottom;
    renderer.setViewport(x,y,r.width,r.height);renderer.setScissor(x,y,r.width,r.height);
    renderer.setClearColor(0x20242b,1);renderer.clear();
    if(!t.loaded)continue;
    if(t===gal.hover)t.o.th-=0.03;
    t.cam.aspect=r.width/r.height;t.cam.updateProjectionMatrix();placeCam(t.cam,t.o);renderer.render(t.scene,t.cam);
  }
  renderer.setScissorTest(false);renderer.setViewport(0,0,cv.clientWidth,cv.clientHeight);
}
function setView(v){
  view=v;const g=v==='gallery';
    document.body.classList.toggle('gallery-view',g);
  $('#gallery').style.display=g?'flex':'none';$('#parts').style.display=g?'none':'flex';$('#hud').style.display=g?'none':($('#labels').checked?'block':'none');
  if(g){gal.sig=filterSig();buildGallery(false);}
  else{disposeTiles();if(cur)preview(cur);}
}
const filterSig=()=>[$('#q').value,$('#hidefx').checked,$('#minparts').value].join('|');
const _render=render;
render=function(){_render();if(view==='gallery'){const s=filterSig();if(s!==gal.sig){gal.sig=s;buildGallery(true);}else syncTiles();}};
$('#gwrap').addEventListener('scroll',()=>gal.dirty=true);
$('#gwrap').addEventListener('mouseover',e=>{const el=e.target.closest('.tile');gal.hover=el?gal.tiles.find(t=>t.el===el)||null:null;});
$('#gwrap').addEventListener('mouseleave',()=>{gal.hover=null;});
$('#gwrap').addEventListener('click',e=>{
  const el=e.target.closest('.tile');if(!el)return;const id=el.dataset.id;
  if(e.target.classList.contains('tcb')){e.target.checked?sel.add(id):sel.delete(id);saveSel();updateCount();
    const f=D.byId[id].fam,fe=document.querySelector(`.fam[data-f="${CSS.escape(f)}"] .fcb`);if(fe){const m=groups.get(f)||[],n=m.filter(x=>sel.has(x.id)).length;fe.checked=n==m.length;fe.indeterminate=n>0&&n<m.length;}
    const rc=document.querySelector(`.row[data-id="${CSS.escape(id)}"] .cb`);if(rc)rc.checked=sel.has(id);return;}
  document.querySelector('input[name=view][value=single]').checked=true;setView('single');preview(id);
});
const pageTo=p=>{gal.page=p;buildGallery(false);};
$('#gfirst').onclick=()=>pageTo(0);$('#gprev').onclick=()=>pageTo(Math.max(0,gal.page-1));
$('#gnext').onclick=()=>pageTo(gal.page+1);$('#glast').onclick=()=>pageTo(1e6);
$('#gsize').onchange=e=>{gal.size=+e.target.value;buildGallery(true);};
$('#gtickpage').onclick=()=>{gal.tiles.forEach(t=>sel.add(t.id));saveSel();syncTiles();updateCount();render();};
document.querySelectorAll('input[name=view]').forEach(r=>r.onchange=()=>setView(r.value));
document.querySelectorAll('input[name=mode]').forEach(r=>r.onchange=()=>{view==='gallery'?relayoutTiles():layout(true);});

/* ----------------------------------------------- điều khiển chung */
function setSide(hide){
  document.querySelector('aside').style.display=hide?'none':'flex';
  $('#btnSide').textContent=hide?'▶ Hiện danh sách':'◀ Ẩn danh sách';
  try{localStorage.setItem('vg_hide',hide?'1':'0');}catch(e){}
  setTimeout(()=>{resize();gal.dirty=true;},30);
}
$('#btnSide').onclick=()=>setSide(document.querySelector('aside').style.display!=='none');
try{if(localStorage.getItem('vg_hide')==='1')setSide(true);}catch(e){}
$('#bprot').onchange=$('#bp8').onchange=()=>{view==='gallery'?relayoutTiles():layout(true);};
$('#frame').onchange=()=>layout();$('#refit').onclick=()=>fitCam();
$('#labels').onchange=()=>{$('#hud').style.display=$('#labels').checked&&view==='single'?'block':'none';};
$('#btnBp').onclick=()=>$('#bpfile').click();
$('#bpfile').onchange=async e=>{
  const files=[...e.target.files];if(!files.length)return;let ok=0,nomatch=[];
  for(const f of files){try{
    let body;
    if(/\.zip$/i.test(f.name)){const u=new Uint8Array(await f.arrayBuffer());let bin='';for(let i=0;i<u.length;i+=32768)bin+=String.fromCharCode.apply(null,u.subarray(i,i+32768));body={name:f.name,zip_b64:btoa(bin)};}
    else body={name:f.name,text:await f.text()};
    const r=await j('/api/blueprint',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
    (r.items||[r]).forEach(it=>{D.bps.add(it.id);bpCache.delete(it.id);it.matched?ok++:nomatch.push(it.id);});
  }catch(err){toast(`Lỗi nạp ${f.name}: ${err.message}`,1);}}
  e.target.value='';
  toast(`Đã nạp ${ok} blueprint khớp model.`+(nomatch.length?`\nKhông có model trùng tên: ${nomatch.slice(0,6).join(', ')}`:''));
  if(ok){document.querySelector('input[name=mode][value=assembled]').checked=true;
    if(view==='gallery'){gal.tiles.forEach(t=>t.bp=null);await Promise.all(gal.tiles.map(async t=>t.bp=await getBP(t.id)));relayoutTiles();}else if(cur)preview(cur);}
};
new ResizeObserver(resize).observe($('#stage'));
const tmpv=new THREE.Vector3();
(function loop(){
  requestAnimationFrame(loop);
  if(view==='gallery'){galRender();return;}
  placeCam(cam,orb);renderer.render(scene,cam);
  if(labelEls.length&&$('#labels').checked){const r=cv.getBoundingClientRect();
    labelEls.forEach(([el,p])=>{tmpv.copy(p.center).add(p.group.position).project(cam);
      el.style.display=(tmpv.z<1&&p.visible)?'block':'none';
      el.style.left=((tmpv.x+1)/2*r.width)+'px';el.style.top=((1-tmpv.y)/2*r.height)+'px';});}
})();
window.__vg={orb,parts:()=>parts,preview,gal,bpMats};
modelReady=init();modelReady.catch(e=>toast('Không tải được danh sách: '+e.message,1));
</script></body></html>
"""

# three.js r128 (MIT) - nen gzip + base64 de chay duoc khi khong co mang
THREE_GZ_B64 = (
    "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"
    "wugE4YrcUhOTqx6C0k5ZnzG1ptZppG9t15wKk761W0t2XaqY0oe7uPcR5mJhgeahdbu+xJGcPg5Xiq/Lm1y59IFMl1e5ctk8y8XX"
    "5lwBelvmX27cZU7mxl3haW55HPbm0lHL5bwEsDheHE51mkzUnPQ5nK+ChM9hfhUkfGX+56VGrnQEXgHZERVy4fPqOwgvQ7b0F14B"
    "2f2Hi299J+JlSKlTce1Uy75/ffPD97YaZ84Qf/q0U9ApWzPocxzRH7CHD82prg6Ol6ucFe+1hD01qkBNoB5xPy4Yj0n9+Cg7+WjQ"
    "2Qswq9HOW5FwR51kzHIN6wiidzYB4htpzAH2mpHuRoHk/pHdKQLBGKP3t/R50OaJsWSkeqEBSj7xkYxULxNgEi+ZauTKEexwMmW5"
    "O54GopuMrL4j6kR3iUC14chp3EB3ypHbXwPdkUduHw9MVx2V+nFATDYyfBeUeXJUy7xBif9GdWy6cU6aGzmnuDCxYEf2ufaEGhr0"
    "w8QM5V5gGBLZViQr3ieSFz9qVZSUaFCQhTKdeN5HVjp4DgpJok6x8+NUTFToKkCBGpFkwBMmbiW84k0RSLSj4mSDPW+Dii3OLQGA"
    "Z99dwqKPxL7CF6zy+YhtNqkU+AKqVcVPn5q1fSlKYbZKVwHEYojal7NuBnwU/UnG2dnItQdkrJ8u5SzA7iHQIInuv6TAd9yzE0bo"
    "eXjg4Lj76RN8HoWeOmKluVqetZqNuDxcYm/6dq7tY36NlYp03D3pjkI7aDLC2yF6g6+E5L963gl3N80Bips227LdUKHWgvB1DeFv"
    "LcLFMRgHw7pCOEX6PMLXknBnUx+guMG0LVv7gJvolHj/BuKGbXG6g04IpoxNCjFCYfM+oE7x8KGtTIFCbM6nv7J2z+vugOGcjeYY"
    "cgYGqMpTOjsYRo0tSJyJXw0WJ7weDWX0JOHAqyUEVsjJGe84E12oTxxmTj7SYCOkgJkwk/Ikr6lQPC+gidlITd/ExGykZnFSGFNU"
    "W7ejQWczqp26ScExavyUxudzhnO0guUJbUE31LC24wV4la48c5IjclCdPsGc49yd+ktUZur/pvacapDShZ2w5ryqcNzouU2UbD3B"
    "elNzgvXmthOsV3UnWK/MCVbn9P89KPvcc61InUr8NU66visH3liBv5QDr772GVmC9kYyZwfaH8ks/6PO00qCnRpT9Do19e86eSu5"
    "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"
    "eVgxQDWJgER0/py6PWYWH3dVt8D9Z6xDa0AxczrymRlamyo9jmAYHdkkBvEj6D7uRFZdacY6N7Vs6jWwpHCG6yF+TIsox1H9mg0u"
    "ALGjUh6cbGBIn+m3fqqh1lTTTzTUmnSSTQ1n6moJl7tmyUTZ3D1iNrZXk+ZBjJM4ra02Q3woAfQKtMdjLMoRpFy4ArRzJUxWpjI1"
    "9FpDkX1nWoquLOadaVm6ug+LllcgU7kMIdtZDogIr9sZPtNbw2e0N3ymN4fPaHf4TG8Pn9H+8JneID67Y4f4zN4iPnP3iM/cTeIz"
    "Z5d4e3nvsX185u4fn7kbyGfuDvLZLVvINUsgzg7vWWWL96yyx3tW2eTVRauM/OUyq9PLNZXxcbN57C7GGx4wS+8vty6933ZNyKxP"
    "lYa3iHbQm1Kk3ZiN7y0Xer7kHs+/8PrOv/CGzn/uXZx/77WbL7tv84W3avr/ObdqvvQmzVe7P/MVL8x84RWZ/n/OFZkvvRbz1S7D"
    "fNkcwdTjF04Q7qrRcjynWu++l+P9mcs4m7rMqxXsuxXsuxXsG3bHCz1yE8GgQe1EbiJ8+lRr+daSHAbDn98+kPJj6cyDmk+5u+KK"
    "trQpTmmJ1K6F7TjcRJ/1/IG+07TtKlMurjLl4h0ENDCqllvXUS6uMOXimhNaElVhoKmKq0u5uN6U0xUoq4Fus6pYIt9dYvqC61q2"
    "Gddwt5mL+1K5uC+Vy/tSOd6X8kqFb+rSD0wpMGrv1PMLfWdD14Ms66GM1TexcN1U1chQ5tuV0QY62qbcxvctIdmsBmBMXTKj3bZ5"
    "lOG1MD+BmViKd5og19hnMLlN8GoT5k3GrBlMXADIwJlC1KRUB3OYQ6/8dt4a+7hs7Ld1uccipGgBMG/PIViVdSZC4hYAizYklPfQ"
    "QCtFK163NPhAm9X5JcvnkxfizTmvHEUi0gv33maV3g95OeW2HCwiLCMaz5Kc6dfGvkq3GpS6h92tLHaqdCubiaorsZ/1vErnZtco"
    "XJ97VfDfc+3o33S16D/y+tB/2KWg/33Xff61l3r+9Xd3/q+9ofPnL9t85u2aP3Ol5mtcovmq12b+19yS+Xdch1FvAn3RpEukvd+M"
    "i+LeNd1yIlmbMC5c7r5UIlv7J2L7ROye4J4BDki4d7KmrZOb8ptmtLURm4dLinaqdkxuIrH5UTia2g+pWjSwD0aYXnRUt/lhtk/t"
    "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"
    "xTrVhW5ivCXNlnNqPVmmMqUpEt+YG2boiAUsMQmTz1BioXolLWsUow6jUw7fLwezMWST7aN2aeiX8fLKkYarhxd6gOyRJLC3YDcw"
    "bqdbHLnQnA1c3w+h1Ii9smnI/Vz1qsq8V6bLFSzmSvcAxmAuIC3sCOX3GjlXmnPoDw5dcugjh75w6AOEtFGWzjYCvniEuy1+QSet"
    "BnceoFOd7fZeXiQlIq+XK7Sb/F6IsKUY77EoetpSsNleMY1TVCUJs+sVZFFbc2/lvisur14n9GH+zTVa295UWCWZbZ3j3sa7OA0H"
    "yVmMnK0N1Rg5vLVb9xZkQ0Y9A7rG+pxdhYaS7Y3S/5i1UGemwBirRcUdRPwEdJj7y5oFeMthiT/WKKE92+QFe97FueM9UuMNY4N3"
    "gOm3XZj+i3TZOZmiyQnSjpW+KSKjgPKxnOnXrMrWMpk5OkyP7K0hOFpBB0iV/qWJZTBkoqP2m6QQ/sgKY/sVSIbI01zdcOXItamn"
    "xQ8FosHsF8PPzIOvktp8CKPYhFs6cGrGWEOMhIG6LOLAva6iwL2j0IF9CH8kRCtIi9FEIuiWEj0mVs2jei5zTDMZTqltoKkylmQu"
    "JKnDZuibHSPdDTCVfzQMNd1ScNTuTV+hqW53iry7zt16rq0rsDV1GWKitnyVWD4OOOctq9BVNWjgU9zbeDVDu2RodiPi+jawdxsT"
    "2b2NYRKyTuAEZVw3gglCesxOw2xtVs269YiC6JI1FZnBm0I6Y6XCjCvxroAtWjHaq3IZrtRvr93slS30BdvP5AT0Dc2EWOBWxlZD"
    "crFkANh3eRl/dZ+cZvtkcM/2mOR2TYOM/MjCA/56mzXbaAp/yYO8V1P9kfiHSq6eIJ1Zs0dC1zJgr1idgxHpxGGIams4paEB8mHr"
    "8wzZNzEHMoSWnqG+1j2ZSozGPpjqgrPAQVEc0yKM2FmLdqwAxMse/rHH0ouDfhiUb4SUqCQYKT57SRt0AoAAAHQpCowedyNH4go9"
    "GFbI/EeBtWfLW9NDSh6X8OH8FQCzJbJEzkZRIkUuEsAbJTxi/woktoYvuaoni4X2SHjlCFibqdSC7CbK9nZYBZ1hV8Plz1Sexszp"
    "SmBSquTGwRlI2ZmDHEV81GdHFLgKxsdTusTskgU5EwaVpygLzvp97949f9zbRPsM8vUusK8qhgzpUpihoB4hOVLE0T3j8ZHnsqCU"
    "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"
    "+QzTNRgdOihDEzaNR9ROyTSmS++YguqC/O5i+fpNUpMlazfI5dbQGLb29u2rgx5ec1aN9Thz2MDLAhqXiIHQpsXZGTfNnWugbrbf"
    "tMo6lV7hhcNHdaChBaa0c8T1bt7K2ZicrXHj/zFZVs8yh/GuEiPXgsdMuS1p8/TrMJ5kJUcnz8xM0+HJj1rmWRqYJbfMTLMk3h4o"
    "i6ver3j15WT/ReGmvy0AyU1eANFe/eT16eHrlzxKbJJW+X0TV4avUukMVVzsvhqLGzN6yFotwszVdTRJK6+B6O6+DSYYNThFMK42"
    "hlbSLum/ShoP+Op73LILb2K89CcZ+mJ7Dk3VXa4SynoPcS+fupM4RN0qJFl8B93tPVCUEn5Y5Wb8JpkEtqfuZxIvFYRN3QjWqXwy"
    "CEFSltDvAHFwjmZDEtLCaPHjV3GuAcYwuTEag2py6oYYTUfeQ5LwN8OLLuteTt1kks/JngrH5/jm4OP4Hua5e5P6xIAL2L/+GcO/"
    "HP+hRwUKR1jD27qT0bh2g2Pcn50P3He/KH/np/doUXDHgm7t7pgoUzoDDU+Mb42PZNo5qPFx7tsIIR4O8eEu5RFpNTH0F7W4dllC"
    "uU6SqKa9ihl18LcyI5O/oVImdVG+LK1r3z/kk4YzLQD/m0+t2uGbd6/3Tq7Ofz85vNp/+/zw6u07hRLGQTQZsNpPweSaXU3u4IOR"
    "Tmmu5Nv6WRtmbBsDA9DINASh3HkhJ8wHompO7aEo88+cYwVJRr2tefjY4KVqTr/A29ionSaDNLydsOwHqmmd1B41yXMXqNQWfz/q"
    "NUPF9puvrapmi7L/zNdqdFDboDbccikHymVhrGg0y1IXV2uDJJ9bQaPWbrZq60W/nb4+KGKNuA55HBfu5bMhpqNr980Vs8GoRHvX"
    "tE+OKM6WOfbFS/H0+VjbVVOo1pOjISFVHTJoD2+gd34UAbl4jUcNA7TVqLWg1474Z5Dyz1zQwfHsNpp/uVjWhSErZX2xCJjqCVFr"
    "EbdOTEKjxG109QLmM+1EnITNBm+u+IPvS5+PeplmentdW/OKr75Vu4SXrH0LVEVFy/DRwmjhehJCw+0+/PxUi+Fnba08QjSyYe1n"
    "Ty4+ZZR/5lzYN6FTM6l9mNAoX2aAXAJjA3o3F3Q0tDu6juO0Kr/6osdPrK5UT/Vbtl5gJK7a8pkCXBewszUDx/5S4Odf7rW4mNZr"
    "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"
    "pNL9OTxnjnLrdoGKJe1uCr8LDOukcQs43mCrjU7h2j0SoloYN0JnNXcDnsZDUUz3fSPstkhFkApky0OvvRLvpr2sn/DcYTMF5u8W"
    "/rtGhqsEsxQynnEDNYLaGNaGPr3W8414lVk8echtj3gF+UZodCcuusOc1QBGUnUH07I7MXQgVcRFQFwExEVIMPMa+VrbeVy97sJ6"
    "p1PZP7FdRYu2K582oWhuFOyEAnbxlSFSW+yCIO/mVmtO1bqY39W+OLw3vpFrw3kP/GgPBI7EmvVHwSxXiGKH99EjjfxwY5QQmgEF"
    "ajihnIaBRz/oqjYZsMir/3J6/qJu5EMVMVk90lLihyCDoXEaSSQN86iHl5iS5v1G+mStxAHhQSFMMxM/X1RALLrUThJFyc0NN0Ka"
    "0ZKOQm0ZZfLFhbT2lKNZHK3q9gY6CrZnlskXF9Lae+1/mT+OowIB29Lx80UFZDtEo7qIg760qiJJFtOBvcKnPbThkPuflnmMHpB4"
    "JqvOfAmTSIbUrGTS0D3gTP6Hu+mgioGNAAb3HlXkQHUOL21lhfsKxNyQMvEKKu9GX9s9qTLNBv00cPcD9yRw3INAaaPbTpO0e/9Q"
    "Ft6N/cA6RuJ9467+5MLzwQ5EIT/CSYq863k4YmtiOwQhCocmB9ABi3K/r9XS5IfhpxQ8+x2K/HtUFojFWKB0jVHg/j4P997E/TgP"
    "9y+Om6R4m8ufT8aBIkND/30e+n0J/eM8dCSGuwIhtlvFqqD+U8eQYqwRco+LSjll1B7WIjgNYUX7POQubP8INODr8AusmG8QBC97"
    "gL5/jfi7+9GMnK53IrLEDPH2ciNt+rz9PjEyy77Of0OE08N3r85eHb/B76d5+vL5HrnYPYEKyG84N+9EuHDwfSiS4p6ocvvd7YqM"
    "q72z8/2rdutLu3UlcrvPdto/2tlbeu62nbut5z6zc3f03B0zt2M23GmVsjt6dtvI3vyyqWW2zKq3zMwfrUyjQ2ar22Zm28o0Otsx"
    "MnfMkl0r0yi5aWUao7QlM5+fQKbM2N78UbV3eL7fuTrcU5nHMuPk3SkU6Tw/OXnXlpl/mZmbRuZzmXnWhbyDD+cqZ9/O6cqcEztH"
    "9fuA5xyoY7DvOeBQAX4VgMIHvRgnATjnqdKUFV1/3d5WVf0mQM8U5B8cgsPTLsat/eN2AVcT6oWAVY3YGyPPHLBXIq80XqeUUVDM"
    "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"
    "If3/9X8BKyGdXDU1CQA="
)


if __name__ == "__main__":
    main()
