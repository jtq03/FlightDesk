import asyncio
import httpx
from flightdesk.aircraft_types import airline_name, describe_type
from flightdesk.routes import RouteBook, gc_points, parse_airports, route_view

YYZ = {'iata': 'YYZ', 'icao': 'CYYZ', 'name': 'Toronto Pearson', 'city': 'Toronto', 'lat': 43.6772, 'lon': -79.6306}
YVR = {'iata': 'YVR', 'icao': 'CYVR', 'name': 'Vancouver', 'city': 'Vancouver', 'lat': 49.1947, 'lon': -123.1792}
CVG = {'iata': 'CVG', 'icao': 'KCVG', 'name': 'Cincinnati', 'city': 'Cincinnati', 'lat': 39.0488, 'lon': -84.6678}
EWR = {'iata': 'EWR', 'icao': 'KEWR', 'name': 'Newark', 'city': 'Newark', 'lat': 40.6925, 'lon': -74.1687}


def test_progress_and_arc_split_at_the_aircraft():
    mid = gc_points(YYZ['lat'], YYZ['lon'], YVR['lat'], YVR['lon'], 3)[1]
    view = route_view([YYZ, YVR], mid[0], mid[1])
    assert abs(view['progress'] - .5) < .02
    assert view['done'][-1] == view['ahead'][0]                       # the arc joins at the plane
    assert view['done'][0][0] == round(YYZ['lat'], 4) and view['ahead'][-1][0] == round(YVR['lat'], 4)


def test_route_dropped_when_aircraft_is_nowhere_near_it():
    assert route_view([YYZ, YVR], 25.0, -80.0) is None               # Florida is not on YYZ-YVR


def test_parked_aircraft_at_an_unrelated_airport_gets_no_route():
    # Hamilton, Ont. is a modest detour from CVG-EWR in the air, but a parked jet there is not on that flight.
    assert route_view([CVG, EWR], 43.17, -79.93, on_ground=True) is None
    assert route_view([CVG, EWR], 43.17, -79.93) is None              # and too far off the line even airborne


def test_on_ground_at_either_end_keeps_route():
    assert route_view([YYZ, YVR], YYZ['lat'], YYZ['lon'], on_ground=True)['progress'] < .01


def test_arc_longitudes_are_continuous_across_the_dateline():
    pts = gc_points(35.5, 139.7, 37.6, -122.4, 40)                    # Tokyo to San Francisco
    assert all(abs(a[1] - b[1]) < 30 for a, b in zip(pts, pts[1:]))


def test_standing_data_parsing_rejects_bad_documents():
    assert parse_airports({'_airports': [{'lat': 1, 'lon': 2, 'iata': 'A'}]}) is None   # one airport is not a route
    assert parse_airports({'_airports': [{'iata': 'A'}, {'iata': 'B'}]}) is None        # no coordinates
    assert parse_airports('nonsense') is None
    ok = parse_airports({'_airports': [{'iata': 'YYZ', 'icao': 'CYYZ', 'name': 'x', 'location': 'Toronto', 'lat': 43.6, 'lon': -79.6},
                                      {'iata': 'CUN', 'icao': 'MMUN', 'name': 'y', 'location': 'Cancún', 'lat': 21.0, 'lon': -86.8}]})
    assert [a['iata'] for a in ok] == ['YYZ', 'CUN']


def test_type_names_and_art_categories():
    assert describe_type('C172') == ('Cessna 172 Skyhawk', 'single_high')
    assert describe_type('b789')[1] == 'wide_twin'
    assert describe_type('A388')[1] == 'wide_quad'
    assert describe_type('R44')[1] == 'helicopter'
    assert describe_type('ZZZZ') == (None, 'narrow')                   # unknown: no invented name
    assert describe_type(None)[0] is None
    assert airline_name('ACA') == 'Air Canada' and airline_name('QQQ') is None


def test_route_lookup_is_cached_and_skips_non_airline_callsigns():
    calls = []

    def handler(request):
        calls.append(str(request.url))
        if request.url.path.endswith('POE766.json'):
            return httpx.Response(200, json={'_airports': [
                {'iata': 'CUN', 'icao': 'MMUN', 'name': 'Cancun', 'location': 'Cancún', 'lat': 21.03, 'lon': -86.87},
                {'iata': 'YYZ', 'icao': 'CYYZ', 'name': 'Toronto', 'location': 'Toronto', 'lat': 43.67, 'lon': -79.63}]})
        return httpx.Response(404)

    async def scenario():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            book = RouteBook(client)
            book.ensure('CGILN')       # private registration-style callsign: never looked up
            book.ensure('POE766')
            book.ensure('POE766')      # already in flight
            await asyncio.sleep(.2)
            book.ensure('POE766')      # cached now
            book.ensure('ACA1457')
            await asyncio.sleep(.2)
            return book.peek('POE766'), book.peek('ACA1457'), book.peek('CGILN')

    known, missing, private = asyncio.run(scenario())
    assert known[0] == 'known' and known[1][1]['iata'] == 'YYZ'
    assert missing[0] == 'unknown' and private[0] == 'unknown'
    assert len(calls) == 2 and not any('CGILN' in c for c in calls)
