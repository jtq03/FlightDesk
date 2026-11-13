import asyncio
import json
import os
import secrets
import time
from collections import OrderedDict, deque
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlsplit
from fastapi import FastAPI, Depends, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware
from .models import SettingsWrite, DeskCommand, RotationRequest, RotationConfirm, PairRequest, MapView
from .store import Store, Conflict
from .runtime import Runtime
from .providers.aircraft import FeedError
from .media import MediaCatalog

WEB = Path(__file__).resolve().parent.parent / 'web'


def create_app(directory=None, runtime_factory=Runtime):
    @asynccontextmanager
    async def lifespan(app):
        app.state.artwork_lock = asyncio.Lock()
        app.state.geocode_lock = asyncio.Lock()
        app.state.store = Store(Path(directory or os.environ.get('FLIGHTDESK_STATE', '.state')))
        app.state.runtime = runtime_factory(app.state.store)
        await app.state.runtime.start()
        try:
            yield
        finally:
            await app.state.runtime.stop()
            app.state.store.close()

    app = FastAPI(title='Flight Desk', version='0.1.0', lifespan=lifespan,
                  docs_url=None, redoc_url=None, openapi_url=None)
    hosts = os.environ.get('FLIGHTDESK_HOSTS', 'localhost,127.0.0.1,[::1]').split(',')
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=hosts)
    attempts = OrderedDict()

    @app.middleware('http')
    async def boundary(request, call_next):
        if request.method not in ('GET', 'HEAD', 'OPTIONS'):
            # Cross-origin writes (including pairing) are rejected. No wildcard CORS.
            origin = request.headers.get('origin')
            expected = str(request.base_url).rstrip('/')
            if (origin and origin.rstrip('/') != expected) or request.headers.get('sec-fetch-site') == 'cross-site':
                return JSONResponse({'detail': 'Use the portal on this device address'}, status_code=403)
            is_upload = request.method == 'PUT' and request.url.path.startswith('/api/artwork/')
            if not is_upload and not request.headers.get('content-type', '').startswith('application/json'):
                return JSONResponse({'detail': 'JSON body required'}, status_code=415)
            total = 0
            chunks = []
            async for chunk in request.stream():
                total += len(chunk)
                if total > (6*1024*1024 if is_upload else 16384):
                    return JSONResponse({'detail': 'Request too large'}, status_code=413)
                chunks.append(chunk)
            request._body = b''.join(chunks)  # bounded replay for Starlette's wrapped request
        response = await call_next(request)
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: https://tile.openstreetmap.org; connect-src 'self'; frame-ancestors 'self'; base-uri 'self'; form-action 'self'"
        if request.url.path.startswith('/api'):
            response.headers['Cache-Control'] = 'no-store'
        else:
            # Pages and scripts are revalidated on every load (cheap 304s), so a kiosk or phone
            # never gets stuck on an old version after an update.
            response.headers['Cache-Control'] = 'no-cache'
        return response

    def authenticated(request: Request):
        if not request.app.state.store.authenticated(request.cookies.get('flightdesk_session')):
            raise HTTPException(401, 'Pair this browser first')

    @app.get('/api/health')
    async def health():
        return {'status': 'ok', 'version': '0.1.0', 'hardware': 'not-tested'}

    @app.post('/api/pair')
    async def pair(body: PairRequest, request: Request, response: Response):
        # Gate globally as well as per address, so proxy clients cannot bypass it.
        now = time.monotonic()
        ip = request.client.host if request.client else 'unknown'
        for key, limit in [('global', 30), (ip, 5)]:
            queue = attempts.setdefault(key, deque(maxlen=31))
            while queue and now-queue[0] > 60:
                queue.popleft()
            if len(queue) >= limit:
                raise HTTPException(429, 'Too many pairing attempts. Wait one minute.')
            queue.append(now)
        while len(attempts) > 128:
            attempts.popitem(last=False)
        if not secrets.compare_digest(body.code, app.state.store.pairing_code):
            raise HTTPException(403, 'Incorrect pairing code')
        response.set_cookie('flightdesk_session', app.state.store.session(body.device_name), httponly=True,
                            secure=request.url.scheme == 'https', samesite='strict', max_age=90*86400)
        app.state.runtime.publish()
        return {'paired': True}

    @app.post('/api/logout', dependencies=[Depends(authenticated)])
    async def logout(request: Request, response: Response):
        app.state.store.logout(request.cookies.get('flightdesk_session'))
        app.state.runtime.publish()
        response.delete_cookie('flightdesk_session')
        return {'paired': False}

    @app.get('/api/snapshot', dependencies=[Depends(authenticated)])
    async def snapshot():
        return await app.state.runtime.snapshot()

    @app.get('/api/diagnostics', dependencies=[Depends(authenticated)])
    async def diagnostics():
        return await app.state.runtime.diagnostics()

    @app.put('/api/settings', dependencies=[Depends(authenticated)])
    async def settings(body: SettingsWrite):
        previous = app.state.store.read()['settings']
        try:
            app.state.store.update(lambda d: d.update(settings=body.settings.model_dump()), body.expected_revision)
        except Conflict as exc:
            raise HTTPException(409, str(exc))
        if (previous['latitude'], previous['longitude']) != (body.settings.latitude, body.settings.longitude):
            app.state.runtime.map_view = {
                'latitude': body.settings.latitude if body.settings.latitude is not None else 43.45,
                'longitude': body.settings.longitude if body.settings.longitude is not None else -80.49, 'zoom': 9}
        observer = body.settings.observer.model_dump() if body.settings.observer else None
        if previous.get('observer') != observer:
            await app.state.runtime.set_observer(observer)
        app.state.runtime.request_poll()
        app.state.runtime.publish()
        return await app.state.runtime.snapshot()

    @app.post('/api/desk', dependencies=[Depends(authenticated)])
    async def desk(body: DeskCommand):
        runtime = app.state.runtime
        if body.aircraft_id and body.aircraft_id not in runtime.aircraft:
            raise HTTPException(404, 'Search or select an available aircraft first')
        app.state.store.update(lambda d: d.update(desk=body.model_dump()))
        runtime.request_poll()
        runtime.publish()
        return await runtime.snapshot()

    @app.post('/api/map-view', dependencies=[Depends(authenticated)])
    async def map_view(body: MapView):
        app.state.runtime.map_view = body.model_dump()
        app.state.runtime.publish()
        return {'saved': True}

    @app.get('/api/search', dependencies=[Depends(authenticated)])
    async def search(q: str):
        q = q.strip()
        if not 2 <= len(q) <= 16:
            raise HTTPException(422, 'Enter 2–16 characters')
        try:
            rows = await app.state.runtime.lookup(q)
        except FeedError as exc:
            raise HTTPException(503, str(exc))
        return {'aircraft': [a.model_dump() for a in rows], 'status': 'found' if rows else 'not_found',
                'message': None if rows else 'No current position found. The flight may not be airborne, covered or resolved by this provider.'}

    @app.get('/api/aircraft/{aircraft_id}/media', dependencies=[Depends(authenticated)])
    async def media(aircraft_id: str):
        aircraft = app.state.runtime.aircraft.get(aircraft_id)
        if not aircraft:
            raise HTTPException(404, 'Aircraft is no longer in the current snapshot')
        return MediaCatalog(WEB).resolve(aircraft)

    @app.post('/api/display/rotation', dependencies=[Depends(authenticated)])
    async def rotation(body: RotationRequest):
        try:
            return await app.state.runtime.rotate(body.angle)
        except ValueError as exc:
            raise HTTPException(409, str(exc))

    @app.post('/api/display/confirm', dependencies=[Depends(authenticated)])
    async def confirm(body: RotationConfirm):
        try:
            app.state.runtime.confirm_rotation(body.token)
        except ValueError as exc:
            raise HTTPException(409, str(exc))
        return await app.state.runtime.snapshot()

    @app.get('/api/events', dependencies=[Depends(authenticated)])
    async def events(request: Request):
        runtime = app.state.runtime
        if len(runtime.subscribers) >= 12:
            raise HTTPException(429, 'Too many open displays')
        queue = asyncio.Queue(maxsize=1)
        runtime.subscribers.add(queue)
        async def stream():
            try:
                yield 'event: snapshot\ndata: '+json.dumps(await runtime.snapshot())+'\n\n'
                while not await request.is_disconnected():
                    if not app.state.store.authenticated(request.cookies.get('flightdesk_session')):
                        break
                    try:
                        await asyncio.wait_for(queue.get(), 15)
                        yield 'event: snapshot\ndata: '+json.dumps(await runtime.snapshot())+'\n\n'
                    except asyncio.TimeoutError:
                        yield ': heartbeat\n\n'
            finally:
                runtime.subscribers.discard(queue)
        return StreamingResponse(stream(), media_type='text/event-stream', headers={'X-Accel-Buffering': 'no'})

    @app.get('/')
    @app.get('/portal')
    async def portal_page():
        return FileResponse(WEB/'portal.html')

    @app.get('/display')
    async def display_page(request: Request):
        response = FileResponse(WEB/'index.html')
        if request.client and request.client.host in ('127.0.0.1','::1'):
            store=app.state.store
            if not store.authenticated(request.cookies.get('flightdesk_session')):
                response.set_cookie('flightdesk_session',store.session('Desk screen','kiosk'),httponly=True,samesite='strict',max_age=90*86400)
        return response

    @app.get('/api/schema', dependencies=[Depends(authenticated)])
    async def schema():
        return app.openapi()

    from .portal import install_portal_routes
    install_portal_routes(app, authenticated, WEB)
    app.mount('/', StaticFiles(directory=WEB), name='web')
    return app


app = create_app()
