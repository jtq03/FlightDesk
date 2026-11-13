import asyncio
import json
from pathlib import Path
import contextlib
import logging
import os
import secrets
import time
from collections import OrderedDict, deque
import httpx
from .models import Settings
from .display import PreviewDisplay, WaylandDisplay
from .providers.aircraft import DemoProvider, AdsbFiProvider, FeedError
from .routes import RouteBook, route_view
from .aircraft_types import describe_type, airline_name


class Runtime:
    def __init__(self, store, client=None, display=None):
        self.store = store
        self.client = client or httpx.AsyncClient(timeout=8, follow_redirects=False,
                                                limits=httpx.Limits(max_connections=4))
        self.providers = {'demo': DemoProvider(), 'adsbfi': AdsbFiProvider(self.client)}
        self.display = display or (WaylandDisplay(os.environ["FLIGHTDESK_DISPLAY_OUTPUT"]) if os.environ.get("FLIGHTDESK_DISPLAY_OUTPUT") else PreviewDisplay())
        self.rotation_watch = None
        self.rotation_lock = asyncio.Lock()
        self.routes = RouteBook(self.client, self.publish)
        self.aircraft = {}
        self.trails = OrderedDict()
        self.cache = OrderedDict()
        self.inflight = {}
        self.subscribers = set()
        self.task = None
        self.next_poll = 0
        self.wake = asyncio.Event()
        self.feed = {'status': 'starting', 'last_success_at': None, 'message': None}
        self.map_view = None
        self.last_query_key = None
        self.started_at = time.time()
        self.observer = None
        self.overhead_task = None
        self.overhead_rows = []
        self.overhead_status = 'starting'
        # Private per-device configuration, deliberately absent from public snapshots.
        try:
            from .overhead import Observer
            path = Path(os.environ.get('FLIGHTDESK_OBSERVER', str(Path.home()/'.config/flightdesk/observer.json')))
            self.observer = Observer(**json.loads(path.read_text()))
        except (OSError, ValueError, TypeError):
            pass
        saved = self.store.read()['settings'].get('observer')
        if saved:
            self.observer = Observer(**{k:saved[k] for k in ('latitude','longitude','idle_minutes')})
        elif self.observer and not self.store.read().get('observer_migrated'):
            self.store.update(lambda d: d['settings'].update(observer={**self.observer.model_dump(), 'label':'Home'}))
        else:
            self.observer = None
        self.store.update(lambda d: d.update(observer_migrated=True))

    async def start(self):
        if isinstance(self.display, WaylandDisplay):
            try:
                await self.display.request_rotation(self.store.read()['display']['confirmed_angle'])
            except ValueError:
                pass  # Desktop session may not be ready yet; explicit retry remains available.
        self.task = asyncio.create_task(self.run())
        if self.observer:
            self.overhead_task = asyncio.create_task(self.run_overhead())

    async def set_observer(self, saved):
        from .overhead import Observer
        if self.overhead_task:
            self.overhead_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self.overhead_task
        self.overhead_task = None
        self.overhead_rows = []
        self.observer = Observer(**{k:saved[k] for k in ('latitude','longitude','idle_minutes')}) if saved else None
        self.overhead_status = 'starting' if saved else 'not_configured'
        # Configuration now lives in the protected state database, outside the source checkout.
        if self.observer:
            self.overhead_task = asyncio.create_task(self.run_overhead())
        self.publish()

    async def stop(self):
        if self.overhead_task:
            self.overhead_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self.overhead_task
        if self.rotation_watch:
            self.rotation_watch.cancel()
        if self.task:
            self.task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self.task
        for task in list(self.inflight.values()):
            task.cancel()
        await asyncio.gather(*list(self.inflight.values()), return_exceptions=True)
        await self.routes.stop()
        await self.client.aclose()

    def publish(self):
        for queue in list(self.subscribers):
            if queue.full():
                queue.get_nowait()
            queue.put_nowait(True)  # bounded notifications; snapshot built at delivery

    def request_poll(self):
        self.next_poll = 0
        self.wake.set()

    async def cached(self, key, fetch, ttl=10):
        hit = self.cache.get(key)
        if hit and time.monotonic()-hit[0] < ttl:
            self.cache.move_to_end(key)
            return hit[1]
        if key not in self.inflight:
            if len(self.inflight) >= 16:
                raise FeedError('Please wait for the current searches to finish')
            async def perform():
                try:
                    rows = await fetch()
                    self.cache[key] = (time.monotonic(), rows)
                    self.cache.move_to_end(key)
                    while len(self.cache) > 128:
                        self.cache.popitem(last=False)
                    return rows
                finally:
                    self.inflight.pop(key, None)
            self.inflight[key] = asyncio.create_task(perform())
        return await asyncio.shield(self.inflight[key])

    def merge(self, rows):
        for a in rows:
            self.aircraft[a.id] = a
            trail = self.trails.setdefault(a.id, deque(maxlen=120))
            if not trail or a.observed_at > trail[-1]['at']:
                trail.append({'lat': a.latitude, 'lon': a.longitude, 'at': a.observed_at})
            self.trails.move_to_end(a.id)
        while len(self.trails) > 300:
            self.trails.popitem(last=False)
        # Hard upper bounds protect a 1 GB Pi, even during repeated global searches.
        self.aircraft = dict(sorted(self.aircraft.items(), key=lambda x: x[1].observed_at, reverse=True)[:300])

    async def lookup(self, query):
        settings = Settings(**self.store.read()['settings'])
        provider = self.providers[settings.provider]
        rows = await self.cached((settings.provider, 'search', query.upper()), lambda: provider.search(query), 30)
        self.merge(rows)
        self.publish()
        return rows

    async def tick(self):
        d = self.store.read()
        if time.monotonic() < self.next_poll:
            return
        settings = Settings(**d['settings'])
        # Browse the geographic area currently visible, rather than permanently
        # querying only the original airport. Calls remain shared and rate-limited.
        if settings.provider != 'demo' and self.map_view and d['desk']['mode'] != 'follow':
            settings = settings.model_copy(update={'latitude': round(self.map_view['latitude'], 2),
                                                   'longitude': round(self.map_view['longitude'], 2)})
        key = (settings.provider, settings.latitude, settings.longitude, settings.radius_nm)
        if key != self.last_query_key:
            self.aircraft.clear()
            self.trails.clear()
            self.feed = {'status': 'starting', 'last_success_at': None, 'message': None}
            self.last_query_key = key
        self.next_poll = time.monotonic()+settings.poll_seconds
        try:
            provider = self.providers[settings.provider]
            rows = await self.cached(('nearby',)+key, lambda: provider.nearby(settings), settings.poll_seconds)
            self.merge(rows)
            ident = d['desk']['aircraft_id']
            if ident and ident not in {a.id for a in rows}:
                self.merge(await self.cached((settings.provider, 'id', ident), lambda: provider.by_id(ident)))
            self.feed = {'status': 'demo' if settings.provider == 'demo' else 'live',
                         'last_success_at': time.time(), 'message': None}
        except FeedError as exc:
            self.feed.update(status='unavailable', message=str(exc))
            self.next_poll = time.monotonic()+max(settings.poll_seconds, exc.retry_after)
        except (ValueError, httpx.HTTPError):
            self.feed.update(status='unavailable', message='The aircraft feed could not be read')
            self.next_poll = time.monotonic()+30
        self.aircraft = {k:a for k,a in self.aircraft.items() if time.time()-a.observed_at < 300}
        self.publish()

    async def run_overhead(self):
        # Separate query/cache: panning the map never moves the home observer.
        while True:
            delay = 30
            try:
                settings = Settings(**self.store.read()['settings'])
                if self.store.read()['desk']['mode'] != 'follow':
                    settings = settings.model_copy(update={'latitude': round(self.observer.latitude, 2),
                        'longitude': round(self.observer.longitude, 2), 'radius_nm': 50})
                    self.overhead_rows = await self.providers[settings.provider].nearby(settings)
                    self.overhead_status = 'demo' if settings.provider == 'demo' else 'live'
                    self.publish()
            except asyncio.CancelledError:
                raise
            except FeedError as exc:
                self.overhead_status = 'unavailable'
                delay = max(30, exc.retry_after)
                self.publish()
            except Exception:
                self.overhead_status = 'unavailable'
                self.publish()
            await asyncio.sleep(delay)

    def overhead_snapshot(self):
        from .overhead import nearest_airborne
        a, distance = nearest_airborne(self.overhead_rows, self.observer, time.time())
        item = None
        if a:
            item = a.model_dump()
            item.update(age_seconds=max(0, round(time.time()-a.observed_at, 1)), stale=False)
        return {'enabled': self.observer is not None,
                'idle_minutes': self.observer.idle_minutes if self.observer else 5,
                'status': self.overhead_status, 'aircraft': item,
                'distance_nm': round(distance, 1) if distance is not None else None,
                'info': self.selected_info(a) if a else None}

    async def run(self):
        while True:
            try:
                await self.tick()
            except asyncio.CancelledError:
                raise
            except Exception:
                # One bad poll must never stop the display from updating again.
                logging.getLogger('flightdesk').exception('Poll failed; retrying shortly')
                self.feed.update(status='unavailable', message='Something went wrong reading aircraft; retrying')
                self.next_poll = time.monotonic()+15
                self.publish()
            self.wake.clear()
            try:
                await asyncio.wait_for(self.wake.wait(), timeout=1)
            except asyncio.TimeoutError:
                pass

    def selected_info(self, a):
        """Friendly details for the selected flight. Route is included only when known
        and plausible; otherwise the panel stays plain rather than guessing."""
        if not a:
            return None
        type_name, category = describe_type(a.aircraft_type)
        info = {'airline': airline_name(a.airline_icao), 'type_name': type_name,
                'category': category, 'route': None, 'route_state': 'unknown'}
        airports, state = None, 'unknown'
        if a.route:
            airports, state = a.route['airports'], 'known'
        elif a.callsign and a.source != 'demo':
            self.routes.ensure(a.callsign)
            state, airports = self.routes.peek(a.callsign)
        if airports:
            info['route'] = route_view(airports, a.latitude, a.longitude, on_ground=a.altitude_ft == 0)
            state = 'known' if info['route'] else 'unknown'
        info['route_state'] = state
        return info

    async def snapshot(self):
        d = self.store.read()
        now = time.time()
        rows = []
        for a in self.aircraft.values():
            item = a.model_dump()
            item['age_seconds'] = max(0, round(now-a.observed_at, 1))
            item['stale'] = now-a.observed_at > 30
            if now-a.observed_at <= 120 or a.id == d['desk']['aircraft_id']:
                rows.append(item)
        selected = d['desk']['aircraft_id']
        return {'schema_version': 1, 'server_time': now, **d, 'aircraft': rows,
                'map_view': self.map_view, 'feed': self.feed,
                'overhead': self.overhead_snapshot(),
                'pairing': {'paired_devices': len(self.store.devices()), 'show_until': d.get('pairing_show_until',0)},
                'artwork_revision': self.store.read().get('artwork_revision',0),
                'selected_trail': list(self.trails.get(selected, [])),
                'selected_info': self.selected_info(self.aircraft.get(selected)) if selected else None,
                'display_driver': await self.display.status(),
                'attribution': {'name': 'Synthetic demonstration' if d['settings']['provider'] == 'demo' else 'adsb.fi',
                                'url': None if d['settings']['provider'] == 'demo' else 'https://adsb.fi'},
                'capabilities': {'physical_rotation': isinstance(self.display, WaylandDisplay), 'live_positions': True,
                                 'flight_number_resolution': 'starter_alias_catalog',
                                 'scheduled_flights': False, 'route_enrichment': True,
                                 'aircraft_photos': False, 'aircraft_art': True}}

    async def diagnostics(self):
        """No coordinates, pairing codes, tokens or raw provider responses."""
        return {'version': '0.1.0', 'uptime_seconds': round(time.time()-self.started_at),
                'provider': self.store.read()['settings']['provider'], 'feed': self.feed,
                'cached_aircraft': len(self.aircraft), 'cached_queries': len(self.cache),
                'active_searches': len(self.inflight), 'connected_views': len(self.subscribers),
                'display': await self.display.status(), 'hardware_tested': False}

    async def rotate(self, angle):
        # An explicit orientation choice is permanent, not a timed preview.
        async with self.rotation_lock:
            if self.rotation_watch:
                self.rotation_watch.cancel()
                self.rotation_watch = None
            await self.display.request_rotation(angle)
            self.store.update(lambda s: s['display'].update(
                confirmed_angle=angle, requested_angle=angle, pending=None))
            self.publish()
            return self.store.read()['display']

    def confirm_rotation(self, token):
        def confirm(d):
            pending = d['display']['pending']
            if not pending or pending['expires_at'] <= time.time() or not secrets.compare_digest(pending['token'], token):
                raise ValueError('Rotation preview expired or changed')
            d['display'].update(confirmed_angle=d['display']['requested_angle'], pending=None)
        self.store.update(confirm)
        if self.rotation_watch:
            self.rotation_watch.cancel()
        self.publish()
