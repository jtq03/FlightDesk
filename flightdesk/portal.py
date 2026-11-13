"""Phone controls: local pairing, connected devices and protected artwork uploads."""
import asyncio
import hashlib
import io
import json
import re
import time
import warnings
from pathlib import Path
from fastapi import Depends, HTTPException, Request
from fastapi.responses import FileResponse
from starlette.concurrency import run_in_threadpool
from .aircraft_types import TYPES, AIRLINES

KEY = re.compile(r'^(?:[A-Z0-9]{2,8}|POE_[A-Z0-9]{2,8}|class_[a-z_]{2,30}|DEFAULT)$')


class ArtworkLibrary:
    def __init__(self, web, state):
        self.web = web
        self.directory = state/'artwork'
        self.directory.mkdir(mode=0o700, exist_ok=True)
        self.index = self.directory/'index.json'

    def custom(self):
        return json.loads(self.index.read_text()) if self.index.exists() else {}

    def catalog(self):
        return {**json.loads((self.web/'media/catalog.json').read_text()), **self.custom()}

    def save(self, entries):
        tmp=self.directory/'index.tmp'
        tmp.write_text(json.dumps(entries));tmp.chmod(0o600);tmp.replace(self.index)

    def put(self,key,body):
        from PIL import Image, ImageOps, UnidentifiedImageError
        if not KEY.fullmatch(key):
            raise ValueError('Use an aircraft type, class, or Porter variant from the library')
        Image.MAX_IMAGE_PIXELS=12_000_000
        try:
            with warnings.catch_warnings():
                warnings.simplefilter('error', Image.DecompressionBombWarning)
                image=Image.open(io.BytesIO(body))
                if image.format not in ('PNG','JPEG','WEBP'):
                    raise ValueError('Choose a PNG, JPEG or WebP image')
                if image.width*image.height > 12_000_000 or min(image.size)<8:
                    raise ValueError('Use an image between 8 pixels and 12 megapixels')
                image=ImageOps.exif_transpose(image).convert('RGBA')
                image.thumbnail((1600,1200))
                image.info.clear()  # remove GPS, EXIF and other embedded metadata
                output=io.BytesIO();image.save(output,format='PNG')
        except (UnidentifiedImageError,OSError,Image.DecompressionBombError,Image.DecompressionBombWarning):
            raise ValueError('That image could not be read. Use a PNG, JPEG or WebP up to 12 megapixels.')
        data=output.getvalue();name=hashlib.sha256(data).hexdigest()+'.png'
        entries=self.custom()
        if key not in entries and len(entries)>=128:raise ValueError('The custom library is full (128 images)')
        if sum(p.stat().st_size for p in self.directory.glob('*.png'))+len(data)>128*1024*1024:
            raise ValueError('Artwork storage is full. Restore unused custom images first.')
        path=self.directory/name
        if not path.exists():
            path.write_bytes(data);path.chmod(0o600)
        entries[key]={'asset':'/api/artwork/files/'+name,'kind':'illustration','alt':'Custom '+key+' aircraft artwork',
            'credit':'Your personal artwork','source':'Uploaded from a paired phone','license':'Personal upload',
            'label':key,'width':image.width,'height':image.height,'bounds':[0,0,image.width,image.height],
            'description':'Your custom aircraft image.','custom':True}
        old=self.custom().get(key)
        self.save(entries)
        self.remove_unused(old,entries)
        return entries[key]

    def remove_unused(self,old,entries):
        asset=old.get('asset') if old else None
        if asset and not any(v.get('asset')==asset for v in entries.values()):
            (self.directory/asset.rsplit('/',1)[-1]).unlink(missing_ok=True)

    def restore(self,key):
        entries=self.custom();old=entries.pop(key,None);self.save(entries);self.remove_unused(old,entries)


def install_portal_routes(app, authenticated, web):
    last_geocode=0.0
    geocode_cache={}

    def library():return ArtworkLibrary(web,app.state.store.directory)
    def changed():
        app.state.store.update(lambda d:d.update(artwork_revision=d.get('artwork_revision',0)+1))
        app.state.runtime.publish()
    def loopback(request):
        if not request.client or request.client.host not in ('127.0.0.1','::1'):
            raise HTTPException(403,'Pairing codes are shown only on the desk screen')

    @app.get('/api/kiosk/pairing',dependencies=[Depends(authenticated)])
    async def kiosk_pairing(request:Request):
        loopback(request)
        return {'code':app.state.store.pairing_code,'paired_devices':len(app.state.store.devices()),
                'portal_url':__import__('os').environ.get('FLIGHTDESK_PORTAL_URL','http://flightdesk.local:8765/portal')}

    @app.post('/api/pairing/show',dependencies=[Depends(authenticated)])
    async def show_pairing():
        app.state.store.update(lambda d:d.update(pairing_show_until=time.time()+120))
        app.state.runtime.publish()
        return {'shown':True}

    @app.post('/api/pairing/hide',dependencies=[Depends(authenticated)])
    async def hide_pairing():
        app.state.store.update(lambda d:d.update(pairing_show_until=0))
        app.state.runtime.publish()
        return {'shown':False}

    @app.get('/api/devices',dependencies=[Depends(authenticated)])
    async def devices(request:Request):
        own=app.state.store.digest(request.cookies.get('flightdesk_session',''))[:16]
        return {'devices':[{**d,'this_device':d['id']==own} for d in app.state.store.devices()]}

    @app.delete('/api/devices/{ident}',dependencies=[Depends(authenticated)])
    async def revoke(ident:str):
        if not re.fullmatch('[a-f0-9]{16}',ident):raise HTTPException(422,'Invalid device')
        app.state.store.revoke_device(ident);app.state.runtime.publish()
        return {'removed':True}

    @app.get('/api/airlines',dependencies=[Depends(authenticated)])
    async def airlines():return {'airlines':AIRLINES}

    @app.get('/api/artwork',dependencies=[Depends(authenticated)])
    async def artwork():
        return {'catalog':library().catalog(),'types':{k:v[0] for k,v in TYPES.items()},
                'revision':app.state.store.read().get('artwork_revision',0)}

    @app.put('/api/artwork/{key}',dependencies=[Depends(authenticated)])
    async def upload(key:str,request:Request):
        if request.headers.get('content-type','').split(';')[0] not in ('image/png','image/jpeg','image/webp','application/octet-stream'):
            raise HTTPException(415,'Choose a PNG, JPEG or WebP')
        body=await request.body()
        if not body:raise HTTPException(422,'Choose an image first')
        try:
            async with app.state.artwork_lock:
                result=await run_in_threadpool(library().put,key,body)
                changed()
            return result
        except ValueError as exc:raise HTTPException(422,str(exc))

    @app.delete('/api/artwork/{key}',dependencies=[Depends(authenticated)])
    async def restore(key:str):
        if not KEY.fullmatch(key):raise HTTPException(422,'Invalid artwork key')
        async with app.state.artwork_lock:
            await run_in_threadpool(library().restore,key);changed()
        return {'restored':True}

    @app.get('/api/artwork/files/{name}',dependencies=[Depends(authenticated)])
    async def custom_image(name:str):
        if not re.fullmatch('[a-f0-9]{64}\\.png',name):raise HTTPException(404)
        path=library().directory/name
        if not path.is_file():raise HTTPException(404)
        return FileResponse(path,media_type='image/png')

    @app.get('/api/locations/search',dependencies=[Depends(authenticated)])
    async def geocode(q:str):
        # User-triggered lookup only, never autocomplete. Nominatim allows <=1 request/sec.
        nonlocal last_geocode
        q=q.strip()
        if not 3<=len(q)<=180:raise HTTPException(422,'Enter an address or place (3–180 characters)')
        async with app.state.geocode_lock:
            now=time.monotonic()
            if q in geocode_cache and now-geocode_cache[q][0]<300:return {'results':geocode_cache[q][1]}
            await asyncio.sleep(max(0,1.1-(now-last_geocode)))
            last_geocode=time.monotonic()
            import httpx
            try:
                response=await app.state.runtime.client.get('https://nominatim.openstreetmap.org/search',
                    params={'q':q,'format':'jsonv2','limit':5},headers={'User-Agent':'FlightDesk-Personal/0.2 (personal flight display)','Accept-Language':'en'})
                response.raise_for_status()
                results=[{'label':x['display_name'],'latitude':float(x['lat']),'longitude':float(x['lon'])} for x in response.json()]
            except (httpx.HTTPError,KeyError,ValueError):raise HTTPException(503,'Address search is unavailable. You can enter coordinates instead.')
            if len(geocode_cache)>=32:geocode_cache.clear()
            geocode_cache[q]=(now,results)
        return {'results':results,'credit':'© OpenStreetMap contributors'}
