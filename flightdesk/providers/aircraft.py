import asyncio
import math
import re
import time
from typing import Protocol
import httpx
from ..models import Aircraft
from ..routes import DEMO_AIRPORTS, bearing_deg, gc_points

# A starter catalog, not a universal flight-number resolver. Ambiguous/shared and
# alphanumeric operational callsigns require a route/schedule resolver later.
IATA = {'AC': 'ACA', 'WS': 'WJA', 'PD': 'POE', 'UA': 'UAL', 'BA': 'BAW',
        'DL': 'DAL', 'AA': 'AAL', 'AF': 'AFR', 'LH': 'DLH', 'EK': 'UAE'}


def callsign(query):
    q = re.sub(r'\s+', '', query.upper())
    match = re.fullmatch(r'([A-Z]{2})(\d{1,5}[A-Z]?)', q)
    return IATA.get(match[1], match[1]) + match[2] if match else q


class Provider(Protocol):
    async def nearby(self, settings): ...
    async def search(self, query): ...
    async def by_id(self, aircraft_id): ...


# (callsign, type, origin, destination, offset from map centre, altitude ft, speed kt)
# Route-less entries orbit the map centre, like a private flight with no public plan.
DEMO_FLEET = [
    ('ACA123', 'B789', 'YYZ', 'YVR', (0.15, 0.10), 37000, 487),
    ('WJA610', 'B738', 'YYC', 'YYZ', (-0.20, 0.30), 36000, 462),
    ('POE442', 'DH8D', 'YYZ', 'YOW', (0.05, -0.35), 24000, 290),
    ('UAL930', 'A320', 'ORD', 'YYZ', (-0.10, -0.15), 31000, 441),
    ('ACA857', 'E295', 'YYZ', 'ORD', (0.20, -0.30), 33000, 430),
    ('CGKIT', 'C172', None, None, None, 4500, 104),
]


class DemoProvider:
    """Synthetic aircraft, visibly labelled. Never substituted for failed live data."""
    def __init__(self):
        self.paths = {}
        self.anchors = {}

    def path(self, origin, dest):
        if (origin, dest) not in self.paths:
            a, b = DEMO_AIRPORTS[origin], DEMO_AIRPORTS[dest]
            self.paths[(origin, dest)] = gc_points(a['lat'], a['lon'], b['lat'], b['lon'], 400)
        return self.paths[(origin, dest)]

    def anchor(self, i, origin, dest, target):
        """Index of the route point nearest this flight's spot over the map."""
        key = (i, round(target[0], 2), round(target[1], 2))
        if key not in self.anchors:
            pts = self.path(origin, dest)
            self.anchors[key] = min(range(len(pts)), key=lambda j: (pts[j][0]-target[0])**2 + (pts[j][1]-target[1])**2)
        return self.anchors[key]

    def fleet(self, lat=43.45, lon=-80.49):
        now = time.time()
        result = []
        for i, (cs, typ, origin, dest, offset, alt, speed) in enumerate(DEMO_FLEET):
            phase = now/600+i
            route = None
            if origin:
                pts = self.path(origin, dest)
                where = self.anchor(i, origin, dest, (lat+offset[0], lon+offset[1])) + 6*math.sin(now/120+i)
                where = max(0.0, min(len(pts)-1.001, where))
                j = int(where)
                f = where-j
                p, q = pts[j], pts[j+1]
                plat, plon = p[0]+(q[0]-p[0])*f, p[1]+(q[1]-p[1])*f
                heading = bearing_deg(p[0], p[1], q[0], q[1])
                route = {'airports': [DEMO_AIRPORTS[origin], DEMO_AIRPORTS[dest]]}
            else:
                plat, plon, heading = lat+math.sin(phase)*.20, lon+math.cos(phase)*.28, (phase*180/math.pi+90) % 360
            result.append(Aircraft(id='%06x' % (0xc00001+i), callsign=cs,
                registration='C-G%s' % cs[2:5] if cs[:2] == 'CG' else 'DEMO-%s' % (i+1), aircraft_type=typ,
                airline_icao=cs[:3] if origin else None, latitude=plat, longitude=plon,
                altitude_ft=alt, speed_kt=speed, heading_deg=heading, observed_at=now, source='demo', route=route))
        return result

    async def nearby(self, settings):
        return self.fleet(settings.latitude if settings.latitude is not None else 43.45,
                          settings.longitude if settings.longitude is not None else -80.49)

    async def search(self, query):
        return [a for a in self.fleet() if callsign(query) in (a.callsign, a.id.upper(), a.registration)]

    async def by_id(self, aircraft_id):
        return [a for a in self.fleet() if a.id == aircraft_id]


def normalize(payload, now=None):
    if not isinstance(payload, dict):
        raise ValueError('Unexpected feed document')
    now = time.time() if now is None else now
    # The provider's snapshot timestamp is more accurate than our fetch time.
    try:
        source_time = float(payload.get('now', now))
        if source_time > 1e11:
            source_time /= 1000
        source_time = min(source_time, now)
    except (TypeError, ValueError):
        source_time = now
    result = []
    rows = payload.get('ac', payload.get('aircraft', []))
    if not isinstance(rows, list):
        raise ValueError('Unexpected aircraft feed')
    for raw in rows:
        try:
            ident = raw['hex'].lower()
            # Non-ICAO temporary identifiers and absent/old positions are not drawn.
            age = float(raw.get('seen_pos', raw.get('seen', 0)))
            lat, lon = float(raw['lat']), float(raw['lon'])
            if not re.fullmatch('[0-9a-f]{6}', ident) or not (-90 <= lat <= 90 and -180 <= lon <= 180) or age > 120 or age < 0:
                continue
            cs = raw.get('flight', '').strip() or None
            alt = raw.get('alt_baro')
            result.append(Aircraft(id=ident, callsign=cs, registration=raw.get('r'),
                aircraft_type=raw.get('t'), airline_icao=cs[:3] if cs and re.match('[A-Z]{3}', cs) else None,
                latitude=lat, longitude=lon, altitude_ft=0 if alt == 'ground' else alt,
                speed_kt=raw.get('gs'), heading_deg=raw.get('track'), observed_at=source_time-age, source='adsbfi'))
        except (ValueError, TypeError, KeyError):
            continue
    return result


class FeedError(Exception):
    def __init__(self, message, retry_after=30, permanent=False):
        super().__init__(message)
        self.retry_after = retry_after
        self.permanent = permanent


class AdsbFiProvider:
    name = 'adsbfi'

    def __init__(self, client):
        self.client = client
        self.gate = asyncio.Lock()
        self.last_request = 0
        self.blocked_until = 0
        self.disabled = False

    async def get(self, path):
        # All nearby, follow and search calls share one rate gate and cooldown.
        async with self.gate:
            if self.disabled:
                raise FeedError('Feed paused after an access/configuration error; check provider setup and restart.', permanent=True)
            if time.monotonic() < self.blocked_until:
                raise FeedError('Provider cooldown', self.blocked_until-time.monotonic())
            await asyncio.sleep(max(0, self.last_request+1.1-time.monotonic()))
            self.last_request = time.monotonic()
            try:
                response = await self.client.get('https://opendata.adsb.fi/api/'+path,
                                                headers={'User-Agent': 'FlightDesk/0.1 personal-project'})
            except httpx.HTTPError:
                self.blocked_until = time.monotonic()+30
                raise FeedError('Internet feed unavailable')
            if response.status_code == 429:
                try:
                    wait = min(86400, max(30, float(response.headers.get('Retry-After', '60'))))
                except ValueError:
                    wait = 60
                self.blocked_until = time.monotonic()+wait
                raise FeedError('Provider rate limit; waiting before retry', wait)
            if 400 <= response.status_code < 500:
                self.disabled = True
                raise FeedError('Provider rejected the request; collection paused', permanent=True)
            if response.status_code >= 500:
                self.blocked_until = time.monotonic()+30
                raise FeedError('Provider temporarily unavailable')
            try:
                return normalize(response.json())
            except (ValueError, TypeError):
                self.blocked_until = time.monotonic()+30
                raise FeedError('Unexpected feed format')

    async def nearby(self, settings):
        return await self.get('v3/lat/%s/lon/%s/dist/%s' % (settings.latitude, settings.longitude, settings.radius_nm))

    async def search(self, query):
        q = callsign(query)
        if not re.fullmatch('[A-Z0-9-]{2,16}', q):
            raise FeedError('Use a flight number, callsign, registration or hex identifier')
        endpoint = 'hex' if re.fullmatch('[0-9A-F]{6}', q) else 'registration' if '-' in q else 'callsign'
        rows = await self.get('v2/%s/%s' % (endpoint, q))
        # Porter markets both the POE jet and PTR turboprop operations as PD.
        if not rows and re.fullmatch(r'PD\d{1,5}[A-Z]?', re.sub(r'\s+', '', query.upper())):
            rows = await self.get('v2/callsign/PTR' + q[3:])
        return rows

    async def by_id(self, aircraft_id):
        return await self.get('v2/hex/'+aircraft_id)
