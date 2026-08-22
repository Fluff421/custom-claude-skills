"""Cached, allowlisted live recipe retrieval."""
import hashlib,json,time
from pathlib import Path
from urllib.parse import urlparse
import requests
from bs4 import BeautifulSoup
ROOT=Path(__file__).parent; TTL=604800; ALLOW={'traeger.com','www.traeger.com','blackstoneproducts.com','www.blackstoneproducts.com','amazingribs.com','www.amazingribs.com'}
def fetch(url):
 if urlparse(url).netloc not in ALLOW: raise ValueError('source not allowlisted')
 p=ROOT/'data'/'cache'/(hashlib.sha256(url.encode()).hexdigest()+'.json'); p.parent.mkdir(parents=True,exist_ok=True)
 if p.exists() and time.time()-p.stat().st_mtime<TTL:return json.loads(p.read_text())
 try:
  r=requests.get(url,timeout=20,headers={'User-Agent':'PitMasterAI/1.0'});r.raise_for_status();s=BeautifulSoup(r.text,'html.parser');d={'url':url,'title':s.title.get_text(strip=True) if s.title else url,'text':' '.join(s.stripped_strings)[:50000],'cached':False};p.write_text(json.dumps(d));return d
 except requests.RequestException as e:
  if p.exists(): d=json.loads(p.read_text());d['stale']=True;return d
  return {'url':url,'text':'','error':str(e),'fallback':'Use GRILL_DB offline guidance.'}
