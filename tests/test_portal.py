import io,json,time
from pathlib import Path
from PIL import Image
from fastapi.testclient import TestClient
from flightdesk.app import create_app


def test_kiosk_has_automatic_local_session_but_remote_cannot_get_code(tmp_path):
    app=create_app(tmp_path)
    with TestClient(app,base_url='http://localhost',client=('127.0.0.1',12345)) as c:
        assert c.get('/display').status_code==200
        assert c.cookies.get('flightdesk_session')
        assert c.get('/api/kiosk/pairing').json()['code']==app.state.store.pairing_code
        assert c.get('/api/snapshot').json()['pairing']['paired_devices']==0
    with TestClient(create_app(tmp_path),base_url='http://localhost',client=('192.168.1.80',12345)) as c:
        c.get('/display')
        assert not c.cookies.get('flightdesk_session')
        c.post('/api/pair',json={'code':c.app.state.store.pairing_code})
        assert c.get('/api/kiosk/pairing').status_code==403


def test_two_named_phones_and_independent_revocation(tmp_path):
    with TestClient(create_app(tmp_path),base_url='http://localhost') as c:
        code=c.app.state.store.pairing_code
        c.post('/api/pair',json={'code':code,'device_name':"Jake's phone"});first=c.cookies.get('flightdesk_session')
        c.post('/api/pair',json={'code':code,'device_name':"Her phone"});second=c.cookies.get('flightdesk_session')
        devices=c.get('/api/devices').json()['devices'];assert [d['name'] for d in devices]==["Jake's phone","Her phone"]
        assert devices[1]['this_device'] and not devices[0]['this_device']
        assert c.get('/api/snapshot').json()['pairing']['paired_devices']==2
        assert c.request('DELETE','/api/devices/'+devices[0]['id'],json={}).status_code==200
        assert c.get('/api/snapshot').status_code==200
        c.cookies.clear();c.cookies.set('flightdesk_session',first);assert c.get('/api/snapshot').status_code==401
        c.cookies.clear();c.cookies.set('flightdesk_session',second);assert c.get('/api/snapshot').status_code==200
        c.post('/api/pairing/show',json={})
        assert c.get('/api/snapshot').json()['pairing']['show_until']>time.time()
        c.post('/api/pairing/hide',json={});assert c.get('/api/snapshot').json()['pairing']['show_until']==0


def test_presets_observer_settings_and_restart(tmp_path,monkeypatch):
    monkeypatch.setenv('FLIGHTDESK_OBSERVER',str(tmp_path/'missing'))
    with TestClient(create_app(tmp_path),base_url='http://localhost') as c:
        c.post('/api/pair',json={'code':c.app.state.store.pairing_code})
        s=c.get('/api/snapshot').json();settings=s['settings']
        assert [p['name'] for p in settings['presets']]==['Waterloo','Pearson']
        settings.update(presets=[{'name':'Test place','latitude':45,'longitude':-75,'zoom':10}],observer={'label':'Home test','latitude':43.4,'longitude':-80.4,'idle_minutes':7})
        response=c.put('/api/settings',json={'expected_revision':s['revision'],'settings':settings})
        assert response.status_code==200
        assert response.json()['overhead']['idle_minutes']==7
        assert c.app.state.runtime.observer.latitude==43.4
    with TestClient(create_app(tmp_path),base_url='http://localhost') as c:
        c.post('/api/pair',json={'code':c.app.state.store.pairing_code})
        assert c.get('/api/snapshot').json()['settings']['presets'][0]['name']=='Test place'
        assert c.app.state.runtime.observer.longitude==-80.4
        s=c.get('/api/snapshot').json();settings=s['settings'];settings['observer']=None
        assert c.put('/api/settings',json={'expected_revision':s['revision'],'settings':settings}).status_code==200
        assert c.app.state.runtime.observer is None


def test_upload_protection_shared_catalog_and_restore(tmp_path):
    with TestClient(create_app(tmp_path),base_url='http://localhost') as c:
        b=io.BytesIO();Image.new('RGB',(400,100),'white').save(b,format='PNG')
        assert c.put('/api/artwork/E295',content=b.getvalue(),headers={'Content-Type':'image/png'}).status_code==401
        c.post('/api/pair',json={'code':c.app.state.store.pairing_code})
        original=c.get('/api/artwork').json()['catalog']['E295']
        assert c.put('/api/artwork/E295',content=b'not a photo',headers={'Content-Type':'image/png'}).status_code==422
        r=c.put('/api/artwork/E295',content=b.getvalue(),headers={'Content-Type':'image/png'})
        assert r.status_code==200,r.text
        saved=r.json();assert saved['custom'] and saved['bounds']==[0,0,400,100]
        assert c.get(saved['asset']).status_code==200
        assert c.get('/api/artwork').json()['catalog']['E295']['asset']==saved['asset']
        assert c.get('/api/snapshot').json()['artwork_revision']==1
        svg=b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'
        assert c.put('/api/artwork/E295',content=svg,headers={'Content-Type':'image/svg+xml'}).status_code==415
        assert c.put('/api/artwork/E295',content=b'x'*(6*1024*1024+1),headers={'Content-Type':'image/png'}).status_code==413
        assert c.request('DELETE','/api/artwork/E295',json={}).status_code==200
        assert c.get('/api/artwork').json()['catalog']['E295']==original
        assert c.get('/api/artwork/files/bad.png').status_code==404


def test_address_lookup_runs_on_request_and_caches_results(tmp_path,monkeypatch):
    import httpx
    with TestClient(create_app(tmp_path),base_url='http://localhost') as c:
        c.post('/api/pair',json={'code':c.app.state.store.pairing_code})
        calls=[]
        async def fake_get(url,**kwargs):
            calls.append(kwargs['params']['q'])
            return httpx.Response(200,json=[{'display_name':'Waterloo airport test','lat':'43.46','lon':'-80.38'}],request=httpx.Request('GET',url))
        monkeypatch.setattr(c.app.state.runtime.client,'get',fake_get)
        assert calls==[]
        one=c.get('/api/locations/search',params={'q':'Waterloo airport'})
        assert one.status_code==200 and one.json()['results'][0]['latitude']==43.46
        assert c.get('/api/locations/search',params={'q':'Waterloo airport'}).status_code==200
        assert calls==['Waterloo airport']


def test_porter_marketing_number_falls_back_to_turboprop_operator():
    import asyncio
    from flightdesk.providers.aircraft import AdsbFiProvider
    async def check():
        provider=AdsbFiProvider(None);calls=[]
        async def fake_get(endpoint):
            calls.append(endpoint)
            return ['Porter Dash 8'] if endpoint.endswith('PTR442') else []
        provider.get=fake_get
        assert await provider.search('PD442')==['Porter Dash 8']
        assert calls==['v2/callsign/POE442','v2/callsign/PTR442']
    asyncio.run(check())
