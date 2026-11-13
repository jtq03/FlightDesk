import asyncio
import json
import time
from pathlib import Path
import httpx
import pytest
from fastapi.testclient import TestClient
from flightdesk.app import create_app
from flightdesk.models import Settings
from flightdesk.store import Store
from flightdesk.runtime import Runtime
from flightdesk.providers.aircraft import AdsbFiProvider, FeedError, normalize, callsign
from flightdesk.media import MediaCatalog


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(tmp_path), base_url='http://localhost') as client:
        yield client


def pair(client):
    response = client.post('/api/pair', json={'code': client.app.state.store.pairing_code})
    assert response.status_code == 200
    return response


def test_private_state_and_pairing_cookie(client):
    assert client.get('/api/health').status_code == 200
    for path in ['/api/snapshot', '/api/schema', '/api/search?q=AC123']:
        assert client.get(path).status_code == 401
    assert client.post('/api/pair', json={'code':'xxxxxx'}).status_code == 422
    response = pair(client)
    assert 'HttpOnly' in response.headers['set-cookie']
    assert 'SameSite=strict' in response.headers['set-cookie']
    assert client.get('/api/snapshot').status_code == 200
    assert client.post('/api/logout', json={}).status_code == 200
    assert client.get('/api/snapshot').status_code == 401


def test_origins_host_and_body_limits(client):
    assert client.post('/api/pair', json={'code':'123456'}, headers={'Origin':'https://other.example'}).status_code == 403
    assert client.get('/api/health', headers={'Host':'attacker.example'}).status_code == 400
    assert client.post('/api/pair', content='x', headers={'Content-Type':'text/plain'}).status_code == 415
    assert client.post('/api/pair', content='x'*17000, headers={'Content-Type':'application/json'}).status_code == 413


def test_pairing_throttle(client):
    for _ in range(5):
        assert client.post('/api/pair', json={'code':'999999' if client.app.state.store.pairing_code != '999999' else '888888'}).status_code == 403
    assert client.post('/api/pair', json={'code':client.app.state.store.pairing_code}).status_code == 429


def test_settings_validation_and_lost_update(client):
    pair(client)
    s = client.get('/api/snapshot').json()
    settings = s['settings']; settings['name'] = 'Bedroom sky'
    response = client.put('/api/settings', json={'expected_revision':s['revision'], 'settings':settings})
    assert response.status_code == 200
    assert response.json()['settings']['name'] == 'Bedroom sky'
    assert client.put('/api/settings', json={'expected_revision':s['revision'], 'settings':settings}).status_code == 409
    new = response.json()
    settings['provider'] = 'adsbfi'
    assert client.put('/api/settings', json={'expected_revision':new['revision'], 'settings':settings}).status_code == 422
    settings['provider'] = 'demo'; settings['airline_colours'] = {'AC':'red'}
    assert client.put('/api/settings', json={'expected_revision':new['revision'], 'settings':settings}).status_code == 422


def test_two_paired_sessions_share_search_selection_follow_and_map(client):
    pair(client)
    first_cookie = client.cookies.get('flightdesk_session')
    found = client.get('/api/search?q=AC123').json()['aircraft']
    assert len(found) == 1 and found[0]['callsign'] == 'ACA123'
    ident = found[0]['id']
    assert client.post('/api/desk', json={'mode':'detail', 'aircraft_id':ident}).status_code == 200
    pair(client)
    second_cookie = client.cookies.get('flightdesk_session')
    assert first_cookie != second_cookie
    assert client.get('/api/snapshot').json()['desk']['aircraft_id'] == ident
    assert client.post('/api/desk', json={'mode':'follow','aircraft_id':ident}).status_code == 200
    client.cookies.set('flightdesk_session', first_cookie)
    assert client.get('/api/snapshot').json()['desk']['mode'] == 'follow'
    view = {'latitude':43.5,'longitude':-80.4,'zoom':11}
    assert client.post('/api/map-view', json=view).status_code == 200
    assert client.get('/api/snapshot').json()['map_view'] == view
    assert client.post('/api/desk', json={'mode':'map'}).json()['desk'] == {'mode':'map','aircraft_id':None,'panel_open':False}
    assert client.post('/api/desk', json={'mode':'follow','aircraft_id':'ffffff'}).status_code == 404


def test_rotation_saves_immediately_and_survives_other_controls(client):
    pair(client)
    response=client.post('/api/display/rotation',json={'angle':90})
    assert response.status_code==200
    assert response.json()['confirmed_angle']==90
    assert response.json()['pending'] is None
    aircraft=client.get('/api/search?q=AC123').json()['aircraft'][0]
    client.post('/api/desk',json={'mode':'detail','aircraft_id':aircraft['id']})
    state=client.get('/api/snapshot').json()
    settings=state['settings'];settings['theme']='dusk'
    assert client.put('/api/settings',json={'expected_revision':state['revision'],'settings':settings}).status_code==200
    client.post('/api/desk',json={'mode':'map'})
    assert client.get('/api/snapshot').json()['display']['confirmed_angle']==90
    assert client.post('/api/display/rotation',json={'angle':270}).json()['confirmed_angle']==270
    assert client.post('/api/display/rotation',json={'angle':45}).status_code==422


def test_rotation_has_no_timeout_and_survives_restart(tmp_path,monkeypatch):
    store=Store(tmp_path);original_code=store.pairing_code
    async def scenario():
        runtime=Runtime(store)
        try:
            await runtime.rotate(270)
            now=time.time()
            monkeypatch.setattr(time,'time',lambda:now+60)
            await runtime.tick()
            assert store.read()['display']['confirmed_angle']==270
            assert store.read()['display']['pending'] is None
            await runtime.rotate(90)
        finally:await runtime.stop()
    asyncio.run(scenario())
    store.update(lambda d:d['settings'].update(name='Saved name'));store.close()
    store=Store(tmp_path)
    assert store.pairing_code==original_code
    assert store.read()['settings']['name']=='Saved name'
    assert store.read()['display']['requested_angle']==90
    assert store.read()['display']['confirmed_angle']==90
    assert store.read()['display']['pending'] is None
    store.close()


def test_normalization_keeps_unknown_unknown_and_rejects_bad_positions():
    rows = normalize({'ac':[
        {'hex':'c00001','flight':'ACA123  ','lat':43,'lon':-80,'seen_pos':5},
        {'hex':'c00002','lat':43,'lon':-80,'alt_baro':'ground'},
        {'hex':'c00003','lat':999,'lon':-80},
        {'hex':'c00004','lat':43,'lon':-80,'seen_pos':140},
        {'hex':'~abc123','lat':43,'lon':-80},
        {'hex':'c00005','lon':-80},
    ]}, now=1000)
    assert len(rows) == 2
    assert rows[0].observed_at == 995 and rows[0].speed_kt is None
    assert rows[0].route is None and rows[1].altitude_ft == 0
    assert callsign('ac 123') == 'ACA123'
    with pytest.raises(ValueError): normalize([])
    row = normalize({'now':900000,'ac':[{'hex':'c00001','lat':43,'lon':-80,'seen_pos':5}]},now=1000000)[0]
    assert row.observed_at == 899995


def test_shared_cache_coalesces_and_evicts(tmp_path):
    async def scenario():
        store = Store(tmp_path); runtime = Runtime(store); count = 0
        async def fetch():
            nonlocal count
            count += 1
            await asyncio.sleep(.01)
            return []
        try:
            await asyncio.gather(*(runtime.cached(('same',),fetch) for _ in range(10)))
            assert count == 1
            for i in range(135):
                await runtime.cached((i,),fetch)
            assert len(runtime.cache) == 128
            queue = asyncio.Queue(maxsize=1); runtime.subscribers.add(queue)
            for _ in range(20): runtime.publish()
            assert queue.qsize() == 1
        finally:
            await runtime.stop(); store.close()
    asyncio.run(scenario())


def test_live_failure_never_becomes_demo(tmp_path):
    async def scenario():
        store = Store(tmp_path)
        store.update(lambda d: d['settings'].update(provider='adsbfi',latitude=43,longitude=-80))
        async def fail(request):
            return httpx.Response(503)
        client = httpx.AsyncClient(transport=httpx.MockTransport(fail))
        runtime = Runtime(store,client=client)
        try:
            await runtime.tick()
            snap = await runtime.snapshot()
            assert snap['feed']['status'] == 'unavailable'
            assert snap['aircraft'] == []
            assert snap['settings']['provider'] == 'adsbfi'
        finally:
            await runtime.stop(); store.close()
    asyncio.run(scenario())


def test_rate_limit_is_shared_across_endpoint_types():
    async def scenario():
        count = 0
        async def respond(request):
            nonlocal count
            count += 1
            return httpx.Response(429,headers={'Retry-After':'90'})
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            provider = AdsbFiProvider(client)
            with pytest.raises(FeedError): await provider.search('ACA123')
            with pytest.raises(FeedError): await provider.by_id('c00001')
            assert count == 1
    asyncio.run(scenario())


def test_photos_fallback_is_explicit_and_catalog_paths_are_bounded(client,tmp_path):
    pair(client)
    aircraft = client.get('/api/search?q=AC123').json()['aircraft'][0]
    media = client.get('/api/aircraft/%s/media' % aircraft['id']).json()
    assert media['kind'] == 'illustration' and media['accuracy'] in {'generic','aircraft_type','aircraft_class'}
    folder = tmp_path/'media';folder.mkdir()
    (folder/'catalog.json').write_text(json.dumps({aircraft['id']:{'asset':'/media/../../private.jpg','credit':'x'}}))
    from flightdesk.models import Aircraft
    assert MediaCatalog(tmp_path).resolve(Aircraft(**aircraft))['accuracy'] == 'generic'


def test_follow_panel_can_close_without_stopping_and_is_shared(client):
    pair(client)
    ident=client.get('/api/snapshot').json()['aircraft'][0]['id']
    r=client.post('/api/desk',json={'mode':'follow','aircraft_id':ident,'panel_open':False})
    assert r.status_code==200
    assert r.json()['desk']=={'mode':'follow','aircraft_id':ident,'panel_open':False}
    # A fresh snapshot (and therefore the event stream/phone) retains the hidden panel.
    assert client.get('/api/snapshot').json()['desk']==r.json()['desk']
    r=client.post('/api/desk',json={'mode':'follow','aircraft_id':ident,'panel_open':True})
    assert r.json()['desk']['mode']=='follow' and r.json()['desk']['panel_open']
    assert client.post('/api/desk',json={'mode':'detail','aircraft_id':ident}).json()['desk']['mode']=='detail'
    assert client.post('/api/desk',json={'mode':'map'}).json()['desk']=={'mode':'map','aircraft_id':None,'panel_open':False}
