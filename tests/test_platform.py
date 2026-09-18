from fastapi.testclient import TestClient
from aegisrover.service.api import app
from aegisrover.protocol.cobs import encode,decode
from aegisrover.protocol.varint import encode as ve,decode as vd
from aegisrover.runtime.ring import Ring
from aegisrover.storage.sqlite import Store

def test_api_live_and_plan():
 c=TestClient(app);assert c.get('/live').status_code==200
 r=c.post('/v1/plan',json={'start':[0,0],'goal':[2,0],'width':3,'height':2,'blocked':[]});assert r.status_code==200 and r.json()['cost']==2

def test_cobs_round_trip():
 data=b'a\x00b\x00';assert decode(encode(data))==data

def test_varint_round_trip():
 for n in [0,1,127,128,999999]:assert vd(ve(n))[0]==n

def test_ring_and_store():
 r=Ring(2);r.append(1);r.append(2);r.append(3);assert r.items()==[2,3]
 s=Store();v=s.put('x','a',{'n':1});assert s.get('x','a')==({'n':1},v)
