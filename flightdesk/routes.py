"""Flight route lookup and journey-progress geometry.

Routes come from adsb.lol's public "standing data" (scheduled origin/destination
per airline callsign). It is schedule data, not live filing data, so every result
is sanity-checked against where the aircraft actually is, and dropped when the
aircraft is nowhere near the route. A wrong route is worse than no route.
"""
import asyncio
import math
import re
import time
from collections import OrderedDict
from typing import List, Optional
import httpx

BASE = 'https://vrs-standing-data.adsb.lol/routes/'
AIRLINE_CALLSIGN = re.compile(r'^[A-Z]{3}[0-9]{1,4}[A-Z]{0,2}$')
EARTH_NM = 3440.065
HIT_TTL, MISS_TTL, ERROR_TTL = 6 * 3600, 3600, 120


def dist_nm(a_lat, a_lon, b_lat, b_lon):
    p1, p2 = math.radians(a_lat), math.radians(b_lat)
    dp, dl = p2 - p1, math.radians(b_lon - a_lon)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_NM * math.asin(min(1, math.sqrt(h)))


def bearing_deg(a_lat, a_lon, b_lat, b_lon):
    p1, p2, dl = math.radians(a_lat), math.radians(b_lat), math.radians(b_lon - a_lon)
    y = math.sin(dl) * math.cos(p2)
    x = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    return (math.degrees(math.atan2(y, x)) + 360) % 360


def gc_points(a_lat, a_lon, b_lat, b_lon, n=48):
    """n points along the great circle a→b, longitudes unwrapped so lines never jump."""
    def vec(lat, lon):
        la, lo = math.radians(lat), math.radians(lon)
        return (math.cos(la) * math.cos(lo), math.cos(la) * math.sin(lo), math.sin(la))
    va, vb = vec(a_lat, a_lon), vec(b_lat, b_lon)
    omega = math.acos(max(-1, min(1, sum(x * y for x, y in zip(va, vb)))))
    out, prev = [], a_lon
    for i in range(n):
        t = i / (n - 1)
        if omega < 1e-9:
            k1, k2 = 1 - t, t
        else:
            k1, k2 = math.sin((1 - t) * omega) / math.sin(omega), math.sin(t * omega) / math.sin(omega)
        x, y, z = (k1 * va[j] + k2 * vb[j] for j in range(3))
        lat = math.degrees(math.atan2(z, math.hypot(x, y)))
        lon = math.degrees(math.atan2(y, x))
        while lon - prev > 180:
            lon -= 360
        while lon - prev < -180:
            lon += 360
        out.append([round(lat, 4), round(lon, 4)])
        prev = lon
    return out


def parse_airports(document) -> Optional[List[dict]]:
    """Airports in flying order from a standing-data route document, or None."""
    if not isinstance(document, dict):
        return None
    result = []
    for raw in document.get('_airports') or []:
        try:
            result.append({'iata': raw.get('iata') or None, 'icao': raw.get('icao') or None,
                           'name': str(raw.get('name') or '')[:80], 'city': str(raw.get('location') or '')[:60],
                           'lat': float(raw['lat']), 'lon': float(raw['lon'])})
        except (KeyError, TypeError, ValueError):
            return None
    return result if len(result) >= 2 else None


def route_view(airports, lat, lon, on_ground=False):
    """Origin, destination, progress and the planned arc split at the aircraft.

    Returns None when the aircraft is not plausibly on this route (stale schedule,
    reused callsign, diversion), so the panel falls back to a plain layout.
    """
    if not airports or len(airports) < 2:
        return None
    best = None
    for a, b in zip(airports, airports[1:]):
        total = dist_nm(a['lat'], a['lon'], b['lat'], b['lon'])
        d_o, d_d = dist_nm(a['lat'], a['lon'], lat, lon), dist_nm(lat, lon, b['lat'], b['lon'])
        detour = d_o + d_d - total
        if best is None or detour < best[0]:
            best = (detour, a, b, total, d_o, d_d)
    detour, origin, dest, total, d_o, d_d = best
    # Real flights stay close to the direct line. Anything well off it is a stale schedule,
    # a reused callsign or a diversion, and a wrong route is worse than none.
    if total < 20 or detour > max(40, 0.15 * total):
        return None
    # A parked or taxiing aircraft is only on this route if it is at one of its ends.
    if on_ground and min(d_o, d_d) > 30:
        return None
    progress = d_o / (d_o + d_d) if d_o + d_d else 0
    arc = gc_points(origin['lat'], origin['lon'], dest['lat'], dest['lon'], 64)
    # Match the aircraft's longitude to the arc's unwrapped longitudes.
    plane_lon = lon
    while plane_lon - arc[0][1] > 180:
        plane_lon -= 360
    while plane_lon - arc[0][1] < -180:
        plane_lon += 360
    split = max(0, min(len(arc) - 1, round(progress * (len(arc) - 1))))
    plane = [round(lat, 4), round(plane_lon, 4)]
    return {'origin': origin, 'destination': dest, 'progress': round(progress, 4),
            'total_nm': round(total), 'remaining_nm': round(d_d),
            'done': arc[:split + 1] + [plane], 'ahead': [plane] + arc[split + 1:]}


class RouteBook:
    """Cached, rate-limited, background route lookups. Never blocks the aircraft poll."""

    def __init__(self, client, on_change=None):
        self.client = client
        self.on_change = on_change
        self.cache = OrderedDict()   # callsign -> (expires_monotonic, airports | None)
        self.tasks = {}

    def peek(self, callsign):
        """('known', airports) | ('unknown', None) | ('loading', None)."""
        hit = self.cache.get(callsign)
        if hit and time.monotonic() < hit[0]:
            return ('known', hit[1]) if hit[1] else ('unknown', None)
        return ('loading', None) if callsign in self.tasks else ('unknown', None)

    def ensure(self, callsign):
        """Start a lookup if this callsign isn't cached or already in flight."""
        if not callsign or not AIRLINE_CALLSIGN.fullmatch(callsign):
            return
        hit = self.cache.get(callsign)
        if (hit and time.monotonic() < hit[0]) or callsign in self.tasks or len(self.tasks) >= 4:
            return
        task = asyncio.create_task(self._fetch(callsign))
        self.tasks[callsign] = task
        task.add_done_callback(lambda _t, c=callsign: self._done(c))

    def _done(self, callsign):
        self.tasks.pop(callsign, None)
        if self.on_change:
            self.on_change()

    def _store(self, callsign, airports, ttl):
        self.cache[callsign] = (time.monotonic() + ttl, airports)
        self.cache.move_to_end(callsign)
        while len(self.cache) > 200:
            self.cache.popitem(last=False)

    async def _fetch(self, callsign):
        url = '%s%s/%s.json' % (BASE, callsign[:2], callsign)
        try:
            response = await self.client.get(url, headers={'User-Agent': 'FlightDesk/0.2 personal-project'})
        except httpx.HTTPError:
            return self._store(callsign, None, ERROR_TTL)
        if response.status_code == 404:
            return self._store(callsign, None, MISS_TTL)
        if response.status_code != 200:
            return self._store(callsign, None, ERROR_TTL)
        try:
            airports = parse_airports(response.json())
        except ValueError:
            airports = None
        self._store(callsign, airports, HIT_TTL if airports else MISS_TTL)

    async def stop(self):
        for task in list(self.tasks.values()):
            task.cancel()
        await asyncio.gather(*list(self.tasks.values()), return_exceptions=True)


# Airports used only by the synthetic demo flights.
DEMO_AIRPORTS = {
    'YYZ': {'iata': 'YYZ', 'icao': 'CYYZ', 'name': 'Toronto Pearson International Airport', 'city': 'Toronto', 'lat': 43.6772, 'lon': -79.6306},
    'YVR': {'iata': 'YVR', 'icao': 'CYVR', 'name': 'Vancouver International Airport', 'city': 'Vancouver', 'lat': 49.1947, 'lon': -123.1792},
    'YYC': {'iata': 'YYC', 'icao': 'CYYC', 'name': 'Calgary International Airport', 'city': 'Calgary', 'lat': 51.1139, 'lon': -114.0203},
    'YOW': {'iata': 'YOW', 'icao': 'CYOW', 'name': 'Ottawa Macdonald-Cartier International Airport', 'city': 'Ottawa', 'lat': 45.3225, 'lon': -75.6692},
    'ORD': {'iata': 'ORD', 'icao': 'KORD', 'name': "Chicago O'Hare International Airport", 'city': 'Chicago', 'lat': 41.9742, 'lon': -87.9073},
    'DEN': {'iata': 'DEN', 'icao': 'KDEN', 'name': 'Denver International Airport', 'city': 'Denver', 'lat': 39.8561, 'lon': -104.6737},
}
