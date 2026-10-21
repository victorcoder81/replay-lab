"""Exact-build explicit cooldown reports; zero does not establish castability."""
import json,struct,math
from pathlib import Path
def load_cooldown_profile(version, protocol):
 profile=json.loads(Path(__file__).with_name('cooldown-16.21.json').read_text(encoding='utf8'))
 if (version,protocol)!=(profile['build'],profile['protocol']):raise ValueError('Cooldown profile requires exact build and protocol.')
 for spec in profile['maps'].values():
  if sorted(spec['byteMap'])!=list(range(256)) or spec['order'] not in ('forward','reverse'):raise ValueError('Invalid cooldown profile map.')
 return profile
def ror(x,n):return ((x>>n)|(x<<(8-n)))&255
def decode_cooldown(payload, profile):
 if len(payload)<2:raise ValueError('header')
 h=int.from_bytes(payload[:2],'little');cursor=2;out={}
 for name,shift,defaults in [('a',0,{7:-1.,6:0.,4:2.,3:1.}),('b',4,{6:0.,0:2.,1:1.,7:-1.}),('c',7,{1:0.,6:2.,7:-1.,4:1.}),('slot',13,{1:2,3:1,2:255,7:0}),('d',10,{7:2.,0:-1.,3:1.,5:0.})]:
  sel=(h>>shift)&7
  if sel in defaults:out[name]=defaults[sel];continue
  size=1 if name=='slot' else 4
  if cursor+size>len(payload):raise ValueError('truncated '+name)
  raw=payload[cursor:cursor+size];cursor+=size
  if name=='slot':out[name]=ror((ror(raw[0],7)-0x41)&255,2);continue
  m=profile['maps'][name];raw=bytes(m['byteMap'][x] for x in raw)
  if m['order']=='reverse':raw=raw[::-1]
  value=struct.unpack('<f',raw)[0]
  if not math.isfinite(value):raise ValueError('nonfinite')
  out[name]=value
 if cursor!=len(payload):raise ValueError('suffix')
 return {'spellSlot':out['slot'], 'reportedCooldownSeconds':out['a'],
         'reportedRemainingCooldownSeconds':out['c'], 'unverifiedNumeric20':out['b'],
         'unverifiedNumeric36':out['d'], 'rawFlag3':bool(h&8),
         'timerStateAtUpdate':'positive' if out['c']>0 else 'zero' if out['c']==0 else 'negative_unverified',
         'spellCastability':'unknown', 'chargesDecoded':False,
         'scope':'explicit_update_only_no_projection'}
