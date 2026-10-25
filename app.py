"""VanGioi RSP Pro • self-contained localhost studio and dependency-aware Lite exporter.
Run: python app.py | Depends only on Python 3.10+ standard library for runtime.
"""
from __future__ import annotations
import collections,gzip,io,json,mimetypes,os,re,struct,sys,tempfile,threading,webbrowser,zipfile,zlib,time
from pathlib import Path
from urllib.parse import urlsplit,parse_qs,unquote
from http.server import ThreadingHTTPServer,BaseHTTPRequestHandler

ROOT=Path(__file__).resolve().parent
PACKS={'models':'VanGioi_Model_Pack.zip','items':'VanGioi_Item_Pack.zip','sounds':'VanGioi_ExtraSound_Pack.zip'}
CATALOG=json.loads(gzip.decompress((ROOT/'data/catalog.json.gz').read_bytes()))
BY_ID={x['id']:x for x in CATALOG['entries']}
SRC={}; ASSET={}; SOURCES={}
for key,name in PACKS.items():
 p=ROOT/'packs'/name
 if not p.exists():p=Path('/mnt/data')/name
 if p.exists():
  z=zipfile.ZipFile(p)
  SRC[key]=(p,z)
  for info in z.infolist():
   if info.is_dir():continue
   if info.filename.startswith('assets/') or info.filename in ('pack.mcmeta','pack.png'):
    SOURCES.setdefault(info.filename,[]).append(key)
    ASSET[info.filename]=key
print('Loaded',len(BY_ID),'catalog entries;',len(ASSET),'resource paths')

LEGACY=ROOT/'packs/rsp-main.zip'
if not LEGACY.exists():LEGACY=Path('/mnt/data/rsp-main.zip')
LEG_Z=zipfile.ZipFile(LEGACY) if LEGACY.exists() else None

# The provided Item pack and Full pack intentionally have mismatched local header names / CRCs.
# We use central directory offsets and decompress raw entries. We do not modify the input packs.
def zread(key,path):
 p,z=SRC[key]
 info=z.getinfo(path)
 with open(p,'rb') as fd:
  fd.seek(info.header_offset)
  header=fd.read(30)
  if len(header)!=30 or header[:4]!=b'PK\x03\x04':raise ValueError('ZIP local header invalid: '+path)
  nl,ex=struct.unpack_from('<HH',header,26)
  fd.seek(info.header_offset+30+nl+ex)
  raw=fd.read(info.compress_size)
 if info.compress_type==zipfile.ZIP_STORED:out=raw
 elif info.compress_type==zipfile.ZIP_DEFLATED:out=zlib.decompress(raw,-15)
 else:raise ValueError('Unsupported compression method: '+str(info.compress_type))
 # Protected Item Pack contains intentionally falsified central-directory uncompressed sizes.
 # Trust decompression stream boundaries rather than its unreliable file_size field.
 if len(out)>128*1024*1024:raise ValueError('Unreasonably large ZIP member: '+path)
 return out

def load(p,preferred=None):
 # Prefer explicit source for model / sound; fallback to any with same relative path.
 keys=([preferred] if preferred else [])+list(reversed(SOURCES.get(p,[])))
 for k in dict.fromkeys(keys):
  if k in SRC and p in SRC[k][1].NameToInfo:
   return zread(k,p)
 raise FileNotFoundError(p)


def fix_png(data):
 if not data.startswith(b'\x89PNG\r\n\x1a\n'):return data
 try:
  p=8;chunks=[];idat=[];dirty=False
  while p+12<=len(data):
   n=struct.unpack_from('>I',data,p)[0];typ=data[p+4:p+8]
   if p+12+n>len(data):return data
   payload=data[p+8:p+8+n];old=struct.unpack_from('>I',data,p+8+n)[0]
   if old!=(zlib.crc32(typ+payload)&0xffffffff):dirty=True
   if typ==b'IDAT':idat.append(payload)
   else:chunks.append((typ,payload))
   p+=12+n
   if typ==b'IEND':break
  if not idat:return data
  compressed=b''.join(idat)
  if len(compressed)>6:
   try:zlib.decompress(compressed)
   except zlib.error:
    try:
     plain=zlib.decompress(compressed[2:-4],-15)
     compressed=compressed[:-4]+struct.pack('>I',zlib.adler32(plain)&0xffffffff)
     dirty=True
    except zlib.error:return data
  if not dirty:return data
  out=bytearray(data[:8]);placed=False
  for typ,payload in chunks:
   if typ==b'IEND' and not placed:
    out+=mkchunk(b'IDAT',compressed);placed=True
   out+=mkchunk(typ,payload)
  return bytes(out)
 except Exception:return data

def mkchunk(typ,payload):return struct.pack('>I',len(payload))+typ+payload+struct.pack('>I',zlib.crc32(typ+payload)&0xffffffff)

# ItemAdder atlas maps, sourced from the original rsp-main website data.
try:
 AMAP=json.loads(LEG_Z.read('rsp-main/pack/data/items/index.json')).get('amap',{}) if LEG_Z else {}
except Exception:AMAP={}

# Resource path resolution and safe trimming of minimal sounds.json

def model_path(ref,ns='minecraft'):
 if not isinstance(ref,str) or not ref or ref[0]=='#' or ref.startswith('builtin/') or ref in ('generated','item/generated','builtin/generated'):return None
 if ':' in ref:ns,ref=ref.split(':',1)
 if re.match(r'^(?:item|block|minecraft:)/',ref) and ns=='minecraft':
  # Vanilla base resources need not be shipped unless present in provided packs.
  pass
 p=f'assets/{ns}/models/{ref}.json'
 return p if p in ASSET else None

def tex_path(ref,ns='minecraft'):
 if not isinstance(ref,str) or not ref or ref.startswith('#'):return None,None
 ref=AMAP.get(ref,ref)
 if ':' in ref:ns,ref=ref.split(':',1)
 path=f'assets/{ns}/textures/{ref}.png'
 return path,ref if path in ASSET else None

def deep_strings(o):
 if isinstance(o,str):yield o
 elif isinstance(o,dict):
  for v in o.values():yield from deep_strings(v)
 elif isinstance(o,list):
  for v in o:yield from deep_strings(v)

def export(ids,filename,mode='lite'):
 chosen=[BY_ID[i] for i in dict.fromkeys(ids) if i in BY_ID]
 if not chosen:raise ValueError('Chưa chọn tài nguyên hợp lệ.')
 if len(chosen)>4000:raise ValueError('Giới hạn 4.000 mục mỗi lần xuất.')
 files={} # filename -> preferred archive
 errors=[];atlas=set();sound_events=collections.defaultdict(dict);included=collections.Counter()
 item_bindings=collections.defaultdict(list);generated={}
 pending=collections.deque();processed=set()
 def add(p,k=None):
  if not p or p in files:return
  if p not in ASSET:errors.append('Thiếu resource: '+p);return
  files[p]=k or ASSET[p]
  if p.endswith('.png') and p+'.mcmeta' in ASSET:files[p+'.mcmeta']=ASSET[p+'.mcmeta']
  if p.endswith('.json'):pending.append(p)
 for obj in chosen:
  if obj['category']=='item':
   for b in obj.get('bindings',[]):item_bindings[b['material']].append(b)
  for p in obj.get('files',[]):add(p, 'models' if obj['category'] in ('vfx','model') else None)
  if obj['category']=='sound':
   path=obj.get('definition','')
   ns=obj['key'].split(':',1)[0];event=obj['key'].split(':',1)[1]
   if path in ASSET:
    try:
     d=json.loads(load(path,'items' if 'items' in SRC and path in SRC['items'][1].NameToInfo else None))
     if event in d:sound_events[ns][event]=d[event]
    except Exception as e:errors.append('Không đọc được sound event '+obj['key']+': '+str(e))
 while pending:
  path=pending.popleft()
  if path in processed:continue
  processed.add(path)
  try:doc=json.loads(load(path,files[path]).decode('utf-8-sig'))
  except Exception as ex:errors.append('JSON không đọc được: '+path+' ('+str(ex)+')');continue
  ns=path.split('/')[1] if '/' in path else 'minecraft'
  nsref='minecraft' if ns=='modelengine' else ns
  # Referenced geometry models from item selectors / parents and overrides.
  parent=doc.get('parent') if isinstance(doc,dict) else None
  if isinstance(parent,str):add(model_path(parent,nsref))
  tex=doc.get('textures') if isinstance(doc,dict) else None
  if isinstance(tex,dict):
   for val in tex.values():
    if isinstance(val,str):
     raw=AMAP.get(val,val)
     pt,ref=tex_path(raw,nsref)
     if ref:atlas.add((raw if ':' in raw else ns+':'+raw))
     if pt and ref:add(pt)
  # Model refs in overrides, 1.21+ item model conditions, components, nested configs.
  if isinstance(doc,dict):
   for key,val in doc.items():
    if key in ('overrides','model','models','cases','entries','fallback','property','on_false','on_true','animation') or key=='items':
     def walk(x):
      if isinstance(x,dict):
       for k,v in x.items():
        if k in ('model','parent') and isinstance(v,str):add(model_path(v,nsref))
        else:walk(v)
      elif isinstance(x,list):
       for v in x:walk(v)
     walk(val)
  # For modelengine display bone variants, don't include other unrelated model groups.
  if '/modelengine/' in path:
   pass
 # Restore minimal custom-model-data routing for selected MMOItems models.
 # Without this parent override, a selected item JSON can be present but never activated in game.
 for material,bindings in item_bindings.items():
  base=f'assets/minecraft/models/item/{material}.json'
  if base not in ASSET:errors.append('Không tìm được file gốc CMD: '+base);continue
  try:
   original=json.loads(load(base))
   if not isinstance(original,dict) or not isinstance(original.get('overrides'),list):continue
   choices={(int(x['cmd']),x['model']) for x in bindings}
   overrides=[]
   for ov in original['overrides']:
    if not isinstance(ov,dict):continue
    pred=ov.get('predicate',{})
    if 'custom_model_data' not in pred:
     overrides.append(ov);continue
    try:cmd=int(float(pred['custom_model_data']))
    except (TypeError,ValueError):continue
    if (cmd,ov.get('model')) in choices:overrides.append(ov)
   if any('custom_model_data' in x.get('predicate',{}) for x in overrides):
    generated[base]=json.dumps({**original,'overrides':overrides},ensure_ascii=False,separators=(',',':')).encode()
  except Exception as ex:errors.append('Không thể tạo CMD override '+base+': '+str(ex))
 # sound event dependencies stored as a filtered merged sounds.json
 for ns,defs in sound_events.items():
  sndpath=f'assets/{ns}/sounds.json'
  if sndpath in files:files.pop(sndpath,None)
  # preserve only selected sound events to avoid unnecessary declarations
  for event,rec in defs.items():
   for item in rec.get('sounds',[]):
    name=item if isinstance(item,str) else item.get('name') if isinstance(item,dict) else None
    if not name:continue
    ps=name.split(':',1);rn=ps[-1];rns=ps[0] if len(ps)==2 else ns
    p=f'assets/{rns}/sounds/{rn}.ogg'
    add(p)
 # mark loose PNG textures in atlases. Several texture references are not atlas sprites; supplying atlas for valid ones is harmless.
 if not chosen:raise ValueError('Trống')
 # pack.mcmeta Minecraft support range matches original supplied model pack.
 packmeta={'pack':{'pack_format':15,'supported_formats':[15,32767],'description':'VanGioi RSP Pro • Lite selective resource pack'}}
 safe=re.sub(r'[^\w.\-\u00C0-\u1EF9]','_',filename or 'VanGioi_RSP_Lite').strip('._')[:70] or 'VanGioi_RSP_Lite'
 if not safe.lower().endswith('.zip'):safe+='.zip'
 fd,tmp=tempfile.mkstemp(prefix='vangioi_pro_',suffix='.zip');os.close(fd)
 # Uncompressed selected files streamed directly from originals; final compressed output is valid CRC-compliant ZIP.
 try:
  with zipfile.ZipFile(tmp,'w',allowZip64=True) as out:
   def wr(name,data):
    method=zipfile.ZIP_STORED if name.endswith(('.png','.ogg','.jpg','.webp')) else zipfile.ZIP_DEFLATED
    out.writestr(name,data,compress_type=method,compresslevel=7 if method==zipfile.ZIP_DEFLATED else None)
   wr('pack.mcmeta',json.dumps(packmeta,ensure_ascii=False).encode())
   try:wr('pack.png',load('pack.png','models'))
   except Exception:pass
   # Explicit atlas for subset needed by modelengine dynamic geometry.
   if atlas:
    atlas_data=json.dumps({'sources':[{'type':'single','resource':r} for r in sorted(atlas)]},ensure_ascii=False).encode()
    wr('assets/minecraft/atlases/blocks.json',atlas_data)
    wr('assets/minecraft/atlases/items.json',atlas_data)
   for path,raw in generated.items():wr(path,raw)
   for path,key in sorted(files.items()):
    if path in generated:continue
    if path in ('pack.mcmeta','pack.png','assets/minecraft/atlases/blocks.json','assets/minecraft/atlases/items.json') and atlas:continue
    try:
     raw=load(path,key)
     if path.endswith('.png'):raw=fix_png(raw)
     elif '/modelengine/models/' in path and path.endswith('.json'):
      # Replace ItemAdder ID aliases by the actual mapped texture reference.
      try:
       d=json.loads(raw)
       if isinstance(d.get('textures'),dict):
        d['textures']={k:AMAP.get(v,v) if isinstance(v,str) else v for k,v in d['textures'].items()}
        raw=json.dumps(d,separators=(',',':')).encode()
      except Exception:pass
     wr(path,raw);included[key]+=1
    except Exception as e:errors.append('Không thể trích xuất '+path+': '+str(e))
   for ns,defs in sound_events.items():
    wr(f'assets/{ns}/sounds.json',json.dumps(defs,ensure_ascii=False,separators=(',',':')).encode())
   report={'app':'VanGioi RSP Pro','mode':mode,'chosen':[o['id'] for o in chosen], 'files':sum(included.values())+len(generated),'generated_cmd_overrides':list(generated),'missing':sorted(set(errors)),'note':'Liên kết chưa phát hiện không được tự động đưa vào pack. Một số cấu hình thuộc server-side plugin, không phải resource pack.'}
   wr('VANGIOI_LITE_REPORT.json',json.dumps(report,ensure_ascii=False,indent=2).encode())
  return tmp,safe,report
 except Exception:
  Path(tmp).unlink(missing_ok=True);raise

class Handler(BaseHTTPRequestHandler):
 protocol_version='HTTP/1.1'
 def log_message(self,fmt,*args):
  if '/api/catalog' not in str(args):print('[HTTP]',fmt%args)
 def send(self,status,body,content_type='application/json',headers=None):
  self.send_response(status);self.send_header('Content-Type',content_type);self.send_header('Content-Length',str(len(body)));self.send_header('Cache-Control','no-cache')
  self.send_header('X-Content-Type-Options','nosniff')
  for k,v in (headers or {}).items():self.send_header(k,v)
  self.end_headers();self.wfile.write(body)
 def do_GET(self):
  parsed=urlsplit(self.path);p=unquote(parsed.path);query=parse_qs(parsed.query)
  try:
   if p in ('/','/index.html'):
    return self.send(200,(ROOT/'index.html').read_bytes(),'text/html; charset=utf-8')
   if p=='/api/catalog':
    return self.send(200,json.dumps(CATALOG,ensure_ascii=False,separators=(',',':')).encode(),'application/json; charset=utf-8')
   if p=='/api/status':
    return self.send(200,json.dumps({'packs':list(SRC),'legacy':bool(LEG_Z),'stats':CATALOG['stats']}).encode())
   if p=='/api/thumbnail':
    obj=BY_ID.get(query.get('id',[''])[0]);file=None
    if obj:
     for path in obj.get('files',[])[:32]:
      if not path.endswith('.json'):continue
      try:
       d=json.loads(load(path))
       ns=path.split('/')[1]
       if ns=='modelengine':ns='minecraft'
       vals=list((d.get('textures') or {}).values()) if isinstance(d,dict) else []
       for v in vals:
        png,ref=tex_path(v,ns)
        if png in ASSET:file=png;break
       if file:break
      except Exception:pass
    if not file:return self.send(404,b'', 'image/png')
    return self.send(200,fix_png(load(file)),'image/png')
   if p=='/api/audio':
    obj=BY_ID.get(query.get('id',[''])[0]);ff=obj['files'] if obj and obj.get('category')=='sound' else []
    if ff:return self.send(200,load(ff[0]),'audio/ogg')
    return self.send(404,b'', 'audio/ogg')
   if p.startswith('/studio/') and LEG_Z:
    sub=p[len('/studio/'):]
    if sub in ('', 'index.html'):
     return self.send(200,(ROOT/'studio_integrated.html').read_bytes(),'text/html; charset=utf-8')
    if sub.startswith('/') or '..' in sub.split('/'):return self.send(403,b'')
    name='rsp-main/'+(sub or 'index.html')
    try:raw=LEG_Z.read(name)
    except KeyError:return self.send(404,b'not found','text/plain')
    mime=mimetypes.guess_type(name)[0] or 'application/octet-stream'
    return self.send(200,raw,mime+'; charset=utf-8' if mime in ('text/html','text/javascript','application/javascript','application/json') else mime)
   return self.send(404,b'not found','text/plain')
  except Exception as e:
   print('GET ERROR',p,repr(e));self.send(500,json.dumps({'error':str(e)}).encode())
 def do_POST(self):
  path=urlsplit(self.path).path
  if path!='/api/export':return self.send(404,b'not found')
  try:
   size=int(self.headers.get('Content-Length','0'))
   if size>2_000_000 or size<1:return self.send(413,b'{"error":"invalid body size"}')
   body=json.loads(self.rfile.read(size))
   if not isinstance(body,dict) or not isinstance(body.get('ids'),list):raise ValueError('Danh sách chọn không hợp lệ')
   tmp,name,report=export(body['ids'],body.get('filename','VanGioi_RSP_Lite'),body.get('mode','lite'))
   sz=os.path.getsize(tmp)
   safe=name.encode('ascii','ignore').decode() or 'VanGioi_RSP_Lite.zip'
   self.send_response(200);self.send_header('Content-Type','application/zip');self.send_header('Content-Disposition',f'attachment; filename="{safe}"');self.send_header('Content-Length',str(sz));self.send_header('X-RSP-Missing',str(len(report['missing'])));self.end_headers()
   try:
    with open(tmp,'rb') as f:
     while chunk:=f.read(1024*1024):self.wfile.write(chunk)
   finally:Path(tmp).unlink(missing_ok=True)
  except Exception as e:
   print('EXPORT ERROR',repr(e));self.send(400,json.dumps({'error':str(e)},ensure_ascii=False).encode())

if __name__=='__main__':
 port=int(os.getenv('RSP_PORT',8765));server=ThreadingHTTPServer(('127.0.0.1',port),Handler)
 url=f'http://127.0.0.1:{port}/'
 print('VanGioi RSP Pro:',url,flush=True)
 if '--no-browser' not in sys.argv:threading.Timer(0.9,lambda:webbrowser.open(url)).start()
 try:server.serve_forever()
 except KeyboardInterrupt:pass
