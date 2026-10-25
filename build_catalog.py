"""Build auditable asset-to-skill-to-equipment mapping from the supplied server configs."""
import os,re,json,sys,gzip,collections,zipfile,unicodedata,struct,zlib
from pathlib import Path
try: import yaml
except ImportError: raise SystemExit('Cần pip install pyyaml để tạo lại catalog. Bản đóng gói có catalog sẵn.')
ROOT=Path(__file__).resolve().parent
SOURCES={
 'models':'VanGioi_Model_Pack.zip','items':'VanGioi_Item_Pack.zip','sounds':'VanGioi_ExtraSound_Pack.zip',
 'mythic':'Mythicmobs.zip','mmo':'MMOItems.zip','lib':'MythicLibs.zip','core':'VanGioiTuTienCore-6.9.3-release-source(1).zip','engine':'ModelEngine.zip'}

def safe_read(z,p):
 try:return z.read(p)
 except (zipfile.BadZipFile,ValueError):
  i=z.getinfo(p)
  with open(z.filename,'rb') as f:
   f.seek(i.header_offset);h=f.read(30)
   if h[:4]!=bytes([80,75,3,4]):raise ValueError('Invalid ZIP header '+p)
   nl,el=struct.unpack_from('<HH',h,26)
   f.seek(i.header_offset+30+nl+el);raw=f.read(i.compress_size)
  if i.compress_type==0:return raw
  if i.compress_type==8:return zlib.decompress(raw,-15)
  raise ValueError('Unsupported compression')

def getzip(k):
 for p in [ROOT/'packs'/SOURCES[k],Path('/mnt/data')/SOURCES[k],ROOT.parent/SOURCES[k]]:
  if p.exists():return zipfile.ZipFile(p)
 return None

def strip(s):
 return re.sub(r'(?i)§[0-9a-fk-or]|&[0-9a-fk-or]|<[^>]+>', '',str(s or '')).strip()

def norm(s):return str(s or '').lower().strip()
def flatstrings(o):
 if isinstance(o,str):yield o
 elif isinstance(o,list):
  for x in o:yield from flatstrings(x)
 elif isinstance(o,dict):
  for x in o.values():yield from flatstrings(x)

MODEL_RE=re.compile(r'(?i)(?:\bmid\b|\bmodelid\b|\bmodel_id\b|\bmodel\b)\s*[:=]\s*[\'\"]?([\w.\-]+)')
SKILL_RE=re.compile(r'(?i)\b(?:skill|castskill|skilltrigger)\s*\{[^}\n]{0,350}?\b(?:s|skill|id|name)\s*=\s*[\'\"]?([\w.\-]+)')
SOUND_RE=re.compile(r'(?i)(?:\b(?:sound|playsound|effect:sound)\s*\{[^}\n]{0,400}?\b(?:s|sound|name)\s*=\s*[\'\"]?)([\w.\-:]+)')
SUMMON_RE=re.compile(r'(?i)\b(?:summon|summonmob)\s*\{[^}\n]*?\b(?:type|mob|m)\s*=\s*[\'\"]?([\w.\-]+)')

def parse_yamls(z,prefixes):
 if not z:return {},0
 d={};fail=0
 for p in z.namelist():
  if not p.lower().endswith(('.yml','.yaml')) or not any(p.startswith(prefix) for prefix in prefixes):continue
  # Exclude irrelevant runtime userdata.
  if '/userdata/' in p or '/data/' in p:continue
  try:
   raw=safe_read(z,p).decode('utf8','replace')
   obj=yaml.safe_load(raw)
   if isinstance(obj,dict):
    for k,v in obj.items():
     if not isinstance(v,(dict,list)):continue
     # A variant definition can override previous; retain first and add separate path reference later.
     ky=norm(k)
     if ky not in d:d[ky]={'name':str(k),'src':p,'body':v,'raw':raw[:1000]}
     else:d[ky].setdefault('otherSources',[]).append(p)
  except Exception:fail+=1
 return d,fail

def extract_model(text):
 # Verify presence of mechanic-typed expression, not generic config text.
 out=[]
 for s in text:
  if re.search(r'(?i)\b(?:model|state|modelchange|setmodel|setmodeltag|bodyclamp|partvisibility|modelanimation|model_animation)\s*\{',s):
   out += MODEL_RE.findall(s)
 return set(map(norm,out))

def extract_skill(text):return set(map(norm,SKILL_RE.findall('\n'.join(text))))

def extract_sound(text):return set(map(norm,SOUND_RE.findall('\n'.join(text))))

def gather():
 mz=getzip('models');iz=getzip('items');sz=getzip('sounds');mm=getzip('mythic');mmo=getzip('mmo');lib=getzip('lib');core=getzip('core');eng=getzip('engine')
 # Index dependencies and model resource groups (paths only, no per-file payload copied).
 model_files=collections.defaultdict(list);model_textures=collections.defaultdict(set)
 assets={};source_keys={}
 for key,z in [('models',mz),('items',iz),('sounds',sz)]:
  if not z:continue
  for info in z.infolist():
   path=info.filename
   if info.is_dir() or not path.startswith('assets/') and path not in ('pack.mcmeta','pack.png'):continue
   assets[path]=key;source_keys.setdefault(path,[]).append(key)
   ma=re.match(r'^assets/modelengine/(?:models|items)/([^/]+)/.+\.json$',path,re.I)
   if ma and key=='models':model_files[norm(ma.group(1))].append(path)
 blueprint={}
 if not eng and (ROOT/'data/catalog.json.gz').exists():
  try:
   old=json.loads(gzip.decompress((ROOT/'data/catalog.json.gz').read_bytes()))
   for e in old.get('entries',[]):
    if e.get('blueprint'):blueprint[e.get('key','')]= {'source':e['blueprint'],'area':''}
  except Exception:pass
 if eng:
  for path in eng.namelist():
   if not path.lower().endswith('.bbmodel'):continue
   ident=norm(Path(path).stem)
   blueprint.setdefault(ident,{'source':path,'area':path.split('/')[2] if len(path.split('/'))>2 else ''})
 # Entries for sound events; include the raw file paths referenced by each event.
 events={}
 sound_paths=[(p,k) for p,k in assets.items() if p.endswith('/sounds.json')]
 for p,key in sound_paths:
  if iz and p in iz.NameToInfo:key='items'
  z={'items':iz,'models':mz,'sounds':sz}[key]
  try:doc=json.loads(safe_read(z,p).decode('utf-8-sig'))
  except Exception:continue
  namespace=p.split('/')[1]
  if not isinstance(doc,dict):continue
  for event,record in doc.items():
   eid=f'{namespace}:{event}'
   if not isinstance(record,dict):continue
   raw=record.get('sounds',[])
   paths=[]
   for v in raw:
    v=v if isinstance(v,str) else v.get('name','') if isinstance(v,dict) else ''
    if not v:continue
    parts=v.split(':',1);ns=parts[0] if len(parts)==2 else namespace;name=parts[-1]
    if name.startswith('minecraft:'):name=name.split(':',1)[1]
    f=f'assets/{ns}/sounds/{name}.ogg'
    if f in assets:paths.append(f)
    else:
     alt=f'assets/minecraft/sounds/{name}.ogg'
     if alt in assets:paths.append(alt)
   events[eid]={'id':eid,'name':event,'namespace':namespace,'category':'sound','files':list(dict.fromkeys(paths)),'definition':p,'evidence':[]}
 # Source yaml config dictionaries
 mob_docs,fm=parse_yamls(mm,['MythicMobs/mobs/','MythicMobs/packs/'])
 skill_docs,fs=parse_yamls(mm,['MythicMobs/skills/','MythicMobs/packs/'])
 libs,fl=parse_yamls(lib,['MythicLib/skill/'])
 item_docs,fi=parse_yamls(mmo,['MMOItems/item/'])
 # Mythic packs mixed mob/skills entries: keep those with Type/Health as mobs, other Skills as skill.
 for k,v in list(mob_docs.items()):
  b=v['body']
  if isinstance(b,dict) and not any(x in b for x in ('Type','Health','Display','Damage','type','health','display')):
   if k not in skill_docs and 'Skills' in b:skill_docs[k]=v
   del mob_docs[k]
 for k,v in list(skill_docs.items()):
  b=v['body']
  if isinstance(b,dict) and 'Type' in b and ('Health' in b or 'Display' in b):
   if k not in mob_docs:mob_docs[k]=v
   del skill_docs[k]
 # Reverse graph skill->skill reference; skill model direct; skill sound direct
 skill_model=collections.defaultdict(list);skill_audio=collections.defaultdict(list);skill_skill=collections.defaultdict(set)
 for sid,v in skill_docs.items():
  strings=list(flatstrings(v['body']))
  for m in extract_model(strings):skill_model[m].append(sid)
  for snd in extract_sound(strings):skill_audio[snd].append(sid)
  skill_skill[sid].update(extract_skill(strings)-{sid})
 # reverse parent skill graph, used to connect indirect references via chain
 skill_parents=collections.defaultdict(set)
 for s,children in skill_skill.items():
  for ch in children:skill_parents[ch].add(s)
 def ancestors(s):
  done=set();stack=[(s,0)];
  while stack:
   cur,d=stack.pop()
   if cur in done or d>6:continue
   done.add(cur)
   stack.extend((p,d+1) for p in skill_parents[cur])
  return done
 model_uses=collections.defaultdict(lambda:{'skills':{},'arts':{},'mobs':{},'items':{},'core':{}})
 audio_uses=collections.defaultdict(lambda:{'skills':{},'arts':{},'mobs':{},'items':{},'core':{}})
 def adduse(container,key,kind,name,src,via='direct'):
  entry=container[key][kind]
  if name not in entry:entry[name]={'name':name,'file':src,'via':via}
  elif via=='direct':entry[name]['via']='direct'
 # Mob->skills, mob->model
 mob_skills=collections.defaultdict(set);mob_models=collections.defaultdict(set);mob_sounds=collections.defaultdict(set)
 for mob,v in mob_docs.items():
  ss=list(flatstrings(v['body']))
  mob_skills[mob]=extract_skill(ss)
  mob_models[mob]=extract_model(ss)
  mob_sounds[mob]=extract_sound(ss)
  for m in mob_models[mob]:adduse(model_uses,m,'mobs',v['name'],v['src'])
  for s in mob_sounds[mob]:adduse(audio_uses,s,'mobs',v['name'],v['src'])
 # Items skill mapping: abilities via type=, supporting mythiclib aliases
 item_skill=collections.defaultdict(set)
 item_info={}
 for iid,v in item_docs.items():
  b=v['body'].get('base',v['body']) if isinstance(v['body'],dict) else {}
  if not isinstance(b,dict):continue
  abilities=b.get('ability',{}) or {}
  ss=set()
  if isinstance(abilities,dict):
   for ab in abilities.values():
    if isinstance(ab,dict) and ab.get('type'):ss.add(norm(ab['type']))
  name=strip(b.get('name','')) or v['name']
  desc={'name':name,'type':Path(v['src']).stem,'id':v['name'],'file':v['src'],'cmd':b.get('custom-model-data'),'material':b.get('material')}
  item_info[iid]=desc
  item_skill[iid]=ss
 # Expand item skills via mythiclib source field when present
 lib_to_skill={}
 for libid,v in libs.items():
  body=v['body'];src=body.get('source','') if isinstance(body,dict) else ''
  if isinstance(src,str) and src.lower().startswith('mythicmobs:'):lib_to_skill[libid]=norm(src.split(':',1)[1])
 item_resolved={}
 for item,skills in item_skill.items():
  expanded=set(skills)
  for s in list(skills):
   if s in lib_to_skill:expanded.add(lib_to_skill[s])
  item_resolved[item]=expanded
 # connect skill uses including ancestor chain
 all_mids=set(model_files)
 for key,look,container in [('model',skill_model,model_uses),('audio',skill_audio,audio_uses)]:
  for assetid,skills in look.items():
   allskills=set()
   for sid in skills:
    allskills|=ancestors(sid)
    sv=skill_docs.get(sid)
    if sv:adduse(container,assetid,'skills',sv['name'],sv['src'],'direct')
   for sid in allskills-set(skills):
    if sid in skill_docs:adduse(container,assetid,'skills',skill_docs[sid]['name'],skill_docs[sid]['src'],'indirect')
   for mob,ms in mob_skills.items():
    if ms & allskills:adduse(container,assetid,'mobs',mob_docs[mob]['name'],mob_docs[mob]['src'],'indirect')
   for item,iss in item_resolved.items():
    if iss & allskills:adduse(container,assetid,'items',item_info[item]['name']+' ['+item_info[item]['type']+':'+item_info[item]['id']+']',item_info[item]['file'],'indirect')
   for libid,real_skill in lib_to_skill.items():
    if real_skill in allskills:
     librec=libs[libid]
     title=strip(librec['body'].get('name',librec['name'])) if isinstance(librec['body'],dict) else librec['name']
     adduse(container,assetid,'arts',title+' ['+librec['name']+']',librec['src'],'indirect')
 # Extract Core Java references explicitly as literal identifiers. Avoid assuming a usage if the string is not a model name.
 if core:
  model_keys=set(model_files);sound_keys=set(events)
  for path in core.namelist():
   if not path.endswith('.java') or '/src/' not in ('/'+path):continue
   try:t=core.read(path).decode('utf8','replace')
   except Exception:continue
   for line in t.splitlines():
    if not any(k in line.lower() for k in ('model','vfx','sound','effect','mythic')):continue
    for literal in re.findall(r'"([^"\n]{3,110})"',line):
     ll=norm(literal)
     if ll in model_keys:adduse(model_uses,ll,'core',Path(path).stem,path,'literal')
     if ll in sound_keys:adduse(audio_uses,ll,'core',Path(path).stem,path,'literal')
 # Catalog models
 entries=[]
 for mid,files in model_files.items():
  bp=blueprint.get(mid)
  use=model_uses.get(mid,{})
  bp_path=bp['source'] if bp else ''
  vfx=bool(re.search(r'(?i)(?:^vfx|^fx|_vfx|_fx|effects?|particle|slash|hit|impact|explosion|shockwave|bullet|trail)',mid)) or (bp and bp['area'].lower() in ('skills','vfx'))
  entries.append({'id':'model:'+mid,'key':mid,'name':mid.replace('_',' '),'category':'vfx' if vfx else 'model','files':files,'blueprint':bp_path,'uses':{k:list(v.values())[:120] for k,v in use.items()},'parts':sum('/models/' in x for x in files),'source':'ModelEngine / resource pack'})
 # Match MMOItems custom-model-data to actual Minecraft item overrides (exact CMD + base material).
 # This is verifiable, unlike inferring an item from a similar-looking filename.
 item_asset_uses=collections.defaultdict(list)
 if iz:
  for resource in iz.namelist():
   mat=re.match(r'^assets/minecraft/models/item/([a-z0-9_]+)\.json$',resource)
   if not mat:continue
   try:doc=json.loads(safe_read(iz,resource))
   except Exception:continue
   if not isinstance(doc,dict):continue
   overrides={}
   for ov in doc.get('overrides',[]):
    if not isinstance(ov,dict):continue
    cmd=ov.get('predicate',{}).get('custom_model_data')
    if cmd is not None and ov.get('model'):
     try:overrides[int(float(cmd))]=ov['model']
     except Exception:pass
   for iid,info in item_info.items():
    try:cmd=int(float(info['cmd']))
    except Exception:continue
    mat_base=norm(info.get('material'))
    # Only regard the link as direct if both CMD and the Minecraft base material agree.
    if mat_base!=mat.group(1):continue
    ref=overrides.get(cmd)
    if not ref:continue
    ns,stem=ref.split(':',1) if ':' in ref else ('minecraft',ref)
    target=f'assets/{ns}/models/{stem}.json'
    if target in assets:
     item_asset_uses[target].append({'name':info['name']+' ['+info['type']+':'+info['id']+']','file':info['file'],'via':'direct','material':mat_base,'cmd':cmd,'model':ref})
 # Item model namespace via all Item zip path entries and only common assets/**/models/*.json (exclude modelengine)
 for p,key in assets.items():
  if key!='items' or not p.endswith('.json'):continue
  if not re.match(r'^assets/[^/]+/(?:models|items)/.+\.json$',p) or p.startswith('assets/modelengine/'):continue
  if p.endswith('/sounds.json'):continue
  ns=p.split('/')[1];stem=Path(p).stem
  entries.append({'id':'item:'+p,'key':p,'name':stem.replace('_',' '),'category':'item','files':[p],'namespace':ns,'uses':{'items':[{k:v for k,v in it.items() if k not in ('material','cmd','model')} for it in item_asset_uses.get(p,[])]},'bindings':[{k:v for k,v in it.items() if k in ('material','cmd','model')} for it in item_asset_uses.get(p,[])], 'source':'Item Pack'})
 # Sound event list
 for eid,e in events.items():
  if eid in audio_uses:e['uses']={k:list(v.values())[:120] for k,v in audio_uses[eid].items()}
  else:e['uses']={}
  entries.append({'id':'sound:'+eid,'key':eid,'name':eid.split(':',1)[-1].replace('_',' '),'category':'sound','files':e['files'],'definition':e['definition'],'uses':e['uses'],'namespace':e['namespace'],'source':'sounds.json'})
 # Ground mob display names in the actual MythicMobs Display field, retaining internal IDs.
 def clean_mob_display(s):
  s=re.sub(r'(?i)[§&]x(?:[§&][0-9a-f]){6}','',str(s or ''))
  s=re.sub(r'(?i)[§&](?:x|[0-9a-fk-or])','',s)
  return re.sub(r'\s+',' ',re.sub(r'<[^>]+>','',s)).strip()
 display_alias={}
 for mob_id,mob_doc in mob_docs.items():
  raw_body=mob_doc.get('body')
  if not isinstance(raw_body,dict):continue
  dn=clean_mob_display(raw_body.get('Display',raw_body.get('display','')))
  if dn and dn.lower()!=mob_id and len(dn)<110:display_alias[mob_id]=dn
 for ent in entries:
  for use in ent.get('uses',{}).get('mobs',[]):
   identifier=use.get('name','')
   if identifier.lower() in display_alias:use['name']=f'{display_alias[identifier.lower()]} [{identifier}]'
 entries.sort(key=lambda x:(x['category'],x['key']))
 meta={'entries':entries,'stats':dict(collections.Counter(x['category'] for x in entries)),
       'source_stats':{'mythic_mobs':len(mob_docs),'mythic_skills':len(skill_docs),'mmo_items':len(item_docs),'mythic_lib_skills':len(libs),'yaml_parse_errors':sum([fm,fs,fl,fi]),'blueprints':len(blueprint)},
       'pack_stats':{k:len(z.infolist()) for k,z in [('models',mz),('items',iz),('sounds',sz)] if z}}
 target=ROOT/'data/catalog.json.gz'
 with gzip.open(target,'wt',encoding='utf8',compresslevel=7) as f:json.dump(meta,f,ensure_ascii=False,separators=(',',':'))
 print('written',target,dict(collections.Counter(x['category'] for x in entries)),meta['source_stats'],target.stat().st_size)
 return meta
if __name__=='__main__':gather()
