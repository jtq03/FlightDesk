import asyncio
import time
import json
from unittest.mock import AsyncMock
import pytest
from flightdesk.models import Aircraft
from flightdesk.overhead import Observer, nearest_airborne, distance_nm
from flightdesk.runtime import Runtime
from flightdesk.store import Store


def plane(ident, lat=43.5, lon=-80.5, age=0, altitude=3000):
    return Aircraft(id=ident, latitude=lat, longitude=lon, altitude_ft=altitude,
                    observed_at=1000-age, source='adsbfi')


def test_nearest_uses_distance_not_feed_order():
    observer = Observer(latitude=43.5, longitude=-80.5)
    close, far = plane('000001'), plane('000002',lat=43.7)
    assert nearest_airborne([far, close],observer,1000)[0].id == close.id
    assert nearest_airborne([far],observer,1000)[0].id == far.id


def test_ground_stale_unknown_future_and_distant_not_art():
    o = Observer(latitude=43.5, longitude=-80.5)
    rows=[plane('000001',altitude=0),plane('000002',age=46),
          plane('000003',altitude=None),plane('000004',age=-1),plane('000005',lat=45)]
    assert nearest_airborne(rows,o,1000) == (None,None)
    assert nearest_airborne([plane('000006')],None,1000) == (None,None)


def test_distance_dateline_and_identical_point():
    assert distance_nm(0,0,0,0)==0
    assert 119 < distance_nm(0,179,0,-179) < 121


def test_observer_validation():
    with pytest.raises(ValueError): Observer(latitude=91,longitude=0)
    with pytest.raises(ValueError): Observer(latitude=0,longitude=0,idle_minutes=0)


def test_observer_query_independent_of_map_and_private(tmp_path,monkeypatch):
    async def check():
        config=tmp_path/'observer.json';config.write_text(json.dumps(dict(latitude=43.5,longitude=-80.5,idle_minutes=5)))
        monkeypatch.setenv('FLIGHTDESK_OBSERVER',str(config))
        store=Store(tmp_path/'state');runtime=Runtime(store)
        runtime.map_view=dict(latitude=10,longitude=20,zoom=9)
        seen=[]
        async def nearby(settings):
            seen.append((settings.latitude,settings.longitude,settings.radius_nm))
            runtime.overhead_rows=[plane('000001')]
            return runtime.overhead_rows
        runtime.providers['demo'].nearby=nearby
        task=asyncio.create_task(runtime.run_overhead())
        await asyncio.sleep(.02);task.cancel()
        with pytest.raises(asyncio.CancelledError): await task
        assert seen==[(43.5,-80.5,50)]
        result=runtime.overhead_snapshot()
        assert result['idle_minutes']==5 and result['enabled']
        assert 'latitude' not in result and 'longitude' not in result
        assert runtime.aircraft=={}  # never pollutes browsed map
        await runtime.stop();store.close()
    asyncio.run(check())


def test_follow_suppresses_observer_network_poll(tmp_path,monkeypatch):
    async def check():
        config=tmp_path/'observer.json';config.write_text(json.dumps(dict(latitude=43.5,longitude=-80.5)))
        monkeypatch.setenv('FLIGHTDESK_OBSERVER',str(config))
        store=Store(tmp_path/'state');store.update(lambda s:s['desk'].update(mode='follow',aircraft_id='000001'))
        runtime=Runtime(store);fetch=AsyncMock(return_value=[]);runtime.providers['demo'].nearby=fetch
        task=asyncio.create_task(runtime.run_overhead());await asyncio.sleep(.02);task.cancel()
        with pytest.raises(asyncio.CancelledError):await task
        fetch.assert_not_awaited();await runtime.stop();store.close()
    asyncio.run(check())


def test_porter_operator_artwork_and_neutral_fallbacks():
    from pathlib import Path
    from flightdesk.media import MediaCatalog
    from flightdesk.aircraft_types import airline_name
    catalog=MediaCatalog(Path(__file__).resolve().parents[1]/'web')
    for code,typ,expected in [('PTR','DH8D','porter-dash8-profile.png'),('POE','E295','porter-e195-e2-profile.png'),('JZA','DH8D','dash8-neutral-profile.png'),('ACA','E295','e195-e2-neutral-profile.png')]:
        a=plane('000001').model_copy(update={'airline_icao':code,'aircraft_type':typ})
        item=catalog.resolve(a)
        assert item['asset'].endswith(expected)
    assert airline_name('PTR')=='Porter Airlines'
