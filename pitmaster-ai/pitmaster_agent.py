import json
from pathlib import Path
ROOT=Path(__file__).parent
class PitMasterAgent:
 def __init__(self,path=ROOT/'grill_db.json'):
  self.foods=json.loads(Path(path).read_text())['foods'];self.alias={a.lower():k for k,v in self.foods.items() for a in [k,*v.get('aliases',[])]}
 def resolve(self,q):
  k=self.alias.get(q.lower().strip())
  if not k: raise ValueError('Unknown food; use available_foods()')
  return self.foods[k]
 def available_foods(self): return sorted(self.foods)
 def plan(self,q,serve_in=45):
  f=self.resolve(q);t=f.get('traeger');b=f.get('blackstone');both=bool(f.get('reverse_sear') and t and b)
  timeline=[{'at':0,'action':'Preheat grills and prepare ingredients.'}]
  if both: timeline += [{'at':10,'action':f"Smoke to {t['internal_target_f']}F."},{'at':serve_in-18,'action':f"Blackstone sear: {b['cook_time']}"},{'at':serve_in-f['rest_time_min'],'action':f"Rest {f['rest_time_min']} min; serve."}]
  return {'dish':f['id'],'grill_assignment':'Both' if both else ('Traeger' if t else 'Blackstone'),'traeger':t,'blackstone':b,'timeline':timeline,'usda_min_temp_f':f.get('usda_min_temp_f'),'chef_target_f':f.get('chef_target_f')}
 def pantry(self,items):
  return sorted([{'food':self.resolve(x)['id'],'score':3 if self.resolve(x).get('reverse_sear') else 2} for x in items if x.lower() in self.alias],key=lambda x:x['score'],reverse=True)
