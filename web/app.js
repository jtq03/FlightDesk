import {chooseArtwork} from '/art-choice.js';
let artCatalog = {};
let artworkRevision = -1, presetKey;
export const portalHooks = {load:null, save:null, notify:null};
export const getSnapshot = () => snapshot;

const $ = id => document.getElementById(id);
const DISPLAY = location.pathname === '/display';
document.body.dataset.surface = DISPLAY ? 'display' : 'portal';
const chrome = document.createElement('section'); chrome.id = 'desk-chrome';
chrome.append($('top'), document.querySelector('.places'));
$('app').prepend(chrome);
let snapshot, stream, map, tiles, suppressMap = false, viewKey, viewTimer, settingsRevision;
let connected = false, settingsDirty = false, settingsAtOpen, lastMode, lastSelected, fitKey, centeredFor, artKey;
let routeLayer, doneLine, aheadLine;
let panelMotion;
const reducedMotion = () => matchMedia('(prefers-reduced-motion: reduce)').matches;
const panelVisible = s => !!s && s.desk.mode !== 'map' && s.desk.panel_open !== false;
let expanded = false, idle = false, lastTouch = performance.now(), waking = false;
document.body.dataset.controls = DISPLAY ? 'closed' : 'open';
const tray = document.createElement('section'); tray.id = 'controls-tray';
for (const el of document.querySelectorAll('.searchbar, .nearby, footer')) tray.append(el);
chrome.append(tray);
$('controls-toggle').onclick = () => {
  const open = document.body.dataset.controls !== 'open';
  document.body.dataset.controls = open ? 'open' : 'closed';
  $('controls-toggle').setAttribute('aria-expanded', String(open));
  if (snapshot) renderList(snapshot);
  if (open && !reducedMotion()) tray.animate([{opacity:0,transform:'translateY(-8px)'},{opacity:1,transform:'none'}],{duration:220,easing:'cubic-bezier(.2,.8,.2,1)'});
};
function presentArt(animate = false) {
  const card = $('flight-card');
  const before = animate && !card.hidden ? card.getBoundingClientRect() : null;
  if (animate) panelMotion?.cancel();
  const full = expanded || idle;
  document.body.classList.toggle('flight-selected', panelVisible(snapshot));
  document.body.classList.toggle('art-open', full);
  document.body.classList.toggle('idle-art', idle);
  $('flight-view').classList.toggle('art-expanded', full);
  $('card-expand').textContent = full ? '⌄' : '⌃';
  $('card-expand').setAttribute('aria-label', full ? 'Return to map and flight' : 'Expand flight art');
  $('card-expand').setAttribute('aria-expanded', String(full));
  $('idle-label').hidden = !idle;
  $('quiet-sky').hidden = !(idle && !snapshot?.overhead?.aircraft);
  if (snapshot) {
    $('flight-card').hidden = idle ? !snapshot.overhead?.aircraft : !panelVisible(snapshot);
    $('flight-view').classList.toggle('selected', idle || panelVisible(snapshot));
  }
  fitAircraftFrame();
  if (animate && before && !card.hidden && !reducedMotion()) {
    const after = card.getBoundingClientRect();
    if (after.width && after.height && before.width && before.height) {
      panelMotion = card.animate([
        {transformOrigin:'top left',transform:`translate(${before.left-after.left}px,${before.top-after.top}px) scale(${before.width/after.width},${before.height/after.height})`,opacity:.94},
        {transformOrigin:'top left',transform:'none',opacity:1}
      ],{duration:340,easing:'cubic-bezier(.2,.8,.2,1)'});
    }
  }
  requestAnimationFrame(() => map?.invalidateSize({pan: false, animate: false}));
}
function wakeArt() {
  idle = false; expanded = false; lastTouch = performance.now();
  presentArt(); if (snapshot) render(snapshot);
}
function activity(e) {
  lastTouch = performance.now();
  if (!idle) return;
  // The first touch wakes without accidentally selecting/following a plane.
  const shortcut = e.target.closest?.('.places button');
  wakeArt();
  if (!shortcut) { waking = true; e.preventDefault(); e.stopImmediatePropagation(); }
}
addEventListener('pointerdown', activity, true);
addEventListener('keydown', activity, true);
addEventListener('click', e => {
  if (waking) { waking = false; e.preventDefault(); e.stopImmediatePropagation(); }
}, true);
addEventListener('pointerup', () => { if (waking) setTimeout(() => { waking = false; }, 350); }, true);
$('card-expand').onclick = () => { expanded = !expanded; presentArt(true); };
let swipe;
$('flight-card').style.touchAction = 'pan-x';
$('flight-card').addEventListener('pointerdown', e => {
  if (e.target.closest('button, input, a, select')) return;
  swipe = {x: e.clientX, y: e.clientY, id: e.pointerId};
  e.currentTarget.setPointerCapture(e.pointerId);
});
$('flight-card').addEventListener('pointerup', e => {
  if (!swipe || swipe.id !== e.pointerId) return;
  const dy = e.clientY - swipe.y, dx = e.clientX - swipe.x; swipe = null;
  if (Math.abs(dy) > 48 && Math.abs(dy) > Math.abs(dx) * 1.4) {
    if (dy > 0 && !expanded) closePanel();
    else { expanded = dy < 0; presentArt(true); }
  }
});
$('flight-card').addEventListener('pointercancel', () => { swipe = null; });
setInterval(() => {
  if (!DISPLAY || !snapshot || !connected || !snapshot.overhead?.enabled || !snapshot.pairing?.paired_devices) return;
  if (snapshot.desk.mode === 'follow' || $('settings-dialog').open) { lastTouch = performance.now(); return; }
  if (!idle && performance.now() - lastTouch >= (snapshot.overhead.idle_minutes || 5) * 60000) {
    idle = true; expanded = false; document.body.dataset.controls = 'closed';
    $('controls-toggle').setAttribute('aria-expanded', 'false');
    render(snapshot);
  }
}, 1000);
const AIRLINE_PALETTE = {ACA:'#b8493d', WJA:'#246e75', POE:'#514b7c', PTR:'#514b7c', UAL:'#245da0',
  AAL:'#52677b', DAL:'#843549', SWA:'#315c9c', BAW:'#354980', AFR:'#395782',
  KLM:'#27758d', JBU:'#32658c', UAE:'#98702c', FLE:'#886131', TSC:'#3e7297',
  DLH:'#3c4b77', QTR:'#803b60', THY:'#b44235'};
function cardColour(s, a) {
  return s.settings.airline_colours[a?.airline_icao] || (a?.airline_icao === 'PTR' ? s.settings.airline_colours.POE : null) || AIRLINE_PALETTE[a?.airline_icao] || '#796443';
}
function sheetColours(hex) {
  const c = hex.match(/[a-f0-9]{2}/gi).map(x => parseInt(x, 16));
  // Darken pale custom colours enough to keep cream lettering legible.
  const luminance = v => v.map(x => { x /= 255; return x <= .04045 ? x / 12.92 : ((x+.055)/1.055)**2.4; }).reduce((t,x,i) => t+x*[.2126,.7152,.0722][i],0);
  while (luminance(c) > .15) for (let i=0; i<3; i++) c[i] = Math.floor(c[i]*.94);
  return [c, c.map(x => Math.round(x*.69))].map(v => '#' + v.map(x => x.toString(16).padStart(2,'0')).join(''));
}

const markers = new Map();          // aircraft id -> {marker, key}
const planePath = 'M14 1L17 11 26 16 26 19 17 17 17 24 21 26 21 28 14 26 7 28 7 26 11 24 11 17 2 19 2 16 11 11Z';
const NEUTRAL = '#56687a';
const TILE_URL = 'https://tile.openstreetmap.org/{z}/{x}/{y}.png';
const remPx = () => parseFloat(getComputedStyle(document.documentElement).fontSize) || 16;
let artworkAspect = 3;
function fitAircraftFrame() {
  const holder = $('card-art');
  if (!holder.clientWidth) return;
  const height = Math.ceil((holder.clientWidth - remPx()*.5) / artworkAspect + remPx()*1.4);
  if (holder.style.height !== height+'px') holder.style.height = height+'px';
}
new ResizeObserver(fitAircraftFrame).observe($('card-art'));

function note(message) { $('message').textContent = message || ''; }
async function api(path, body, method = 'POST') {
  const response = await fetch('/api/' + path, body === undefined ? {} : {
    method, headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)
  });
  const value = await response.json();
  if (!response.ok) {
    if (response.status === 401) showPair();
    const detail = typeof value.detail === 'string' ? value.detail : value.detail?.map(x => x.msg).join('; ');
    throw new Error(detail || 'Could not complete that request');
  }
  return value;
}
function showPair() {
  connected = false;
  stream?.close();
  $('pairing').hidden = false; $('app').hidden = true;
}

/* ---------------- map ---------------- */
function setMapView(lat, lon, zoom) {
  suppressMap = true;
  try { map.setView([lat, lon], zoom, {animate: false}); }
  finally { suppressMap = false; }
}
function mapChanged() {
  if (suppressMap || !snapshot) return;
  clearTimeout(viewTimer);
  viewTimer = setTimeout(async () => {
    const c = map.getCenter();
    const view = {latitude: Math.max(-85, Math.min(85, c.lat)), longitude: ((c.lng + 180) % 360 + 360) % 360 - 180, zoom: map.getZoom()};
    try { await api('map-view', view); } catch (e) { note(e.message); }
  }, 150);
}
function makeTiles() {
  // Browser HTTP cache handles tiles. The service worker never caches/prefetches them.
  // The soft "paper" and "evening" looks are CSS colour filters (see style.css), so one free
  // tile source serves both themes.
  tiles = L.tileLayer(TILE_URL, {maxZoom: 15, keepBuffer: 1,
    attribution: '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'}).addTo(map);
  tiles.on('tileerror', () => note('Map tiles unavailable. Aircraft data and controls remain separate.'));
}
function makeMap() {
  map = L.map('map', {zoomControl: false, minZoom: 3, maxZoom: 15, worldCopyJump: true, zoomSnap: .25, zoomDelta: .5, touchZoom: true, bounceAtZoomLimits: false, zoomAnimation: true, markerZoomAnimation: true, attributionControl: true});
  map.attributionControl.setPrefix(false);
  setMapView(43.45, -80.49, 9);
  makeTiles();
  routeLayer = L.layerGroup().addTo(map);
  doneLine = L.polyline([], {weight: 6, opacity: .95, lineCap: 'round', interactive: false});
  aheadLine = L.polyline([], {weight: 4, opacity: .85, dashArray: '2 11', lineCap: 'round', interactive: false});
  map.on('moveend zoomend', mapChanged);
  map.on('zoomend', updateLabels);
  new ResizeObserver(() => {
    suppressMap = true;
    try { map.invalidateSize({pan: false, animate: false}); } finally { suppressMap = false; }
  }).observe($('map'));
}
function updateLabels() {
  $('map').classList.toggle('no-labels', !map || map.getZoom() < 9 || markers.size > 30);
}

/* ---------------- plane markers ---------------- */
function planeIcon(a, colour, selected, px) {
  const wrapper = document.createElement('div');
  const button = document.createElement('button');
  button.type = 'button'; button.setAttribute('aria-label', 'Select ' + (a.callsign || a.id));
  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  svg.setAttribute('viewBox', '0 0 28 29');
  svg.style.transform = `rotate(${a.heading_deg || 0}deg)`;
  const path = document.createElementNS(svg.namespaceURI, 'path');
  path.setAttribute('d', planePath); path.setAttribute('fill', colour);
  path.setAttribute('stroke', '#fff'); path.setAttribute('stroke-width', '1.8'); path.setAttribute('paint-order', 'stroke');
  svg.append(path); button.append(svg);
  const label = document.createElement('span'); label.className = 'plane-label';
  label.textContent = a.callsign || a.registration || '';
  if (label.textContent) button.append(label);
  button.style.setProperty('--plane', colour);
  wrapper.append(button);
  return L.divIcon({html: wrapper, className: 'plane-icon' + (a.stale ? ' stale' : '') + (selected ? ' sel' : ''),
                    iconSize: [px, px], iconAnchor: [px / 2, px / 2]});
}
function syncMarkers(s, visible) {
  const px = Math.round(remPx() * 3.3);
  const ids = new Set();
  for (const a of visible) {
    ids.add(a.id);
    const colour = s.settings.airline_colours[a.airline_icao] || (a.airline_icao === 'PTR' ? s.settings.airline_colours.POE : null) || NEUTRAL;
    const selected = a.id === s.desk.aircraft_id;
    const key = [colour, Math.round((a.heading_deg || 0) / 4), a.stale, selected, px, a.callsign].join('|');
    let entry = markers.get(a.id);
    if (!entry) {
      const marker = L.marker([a.latitude, a.longitude], {keyboard: false}).addTo(map);
      marker.on('click', () => { if (snapshot?.desk.aircraft_id !== a.id || !panelVisible(snapshot)) command('detail', a.id); });
      entry = {marker, key: null}; markers.set(a.id, entry);
    }
    entry.marker.setLatLng([a.latitude, a.longitude]);
    if (entry.key !== key) { entry.marker.setIcon(planeIcon(a, colour, selected, px)); entry.key = key; }
    entry.marker.setZIndexOffset(selected ? 1000 : 0);
  }
  for (const [id, entry] of markers) if (!ids.has(id)) { map.removeLayer(entry.marker); markers.delete(id); }
  updateLabels();
}

/* ---------------- follow mode: the flight arc ---------------- */
function airportIcon(code) {
  const wrap = document.createElement('div');
  const dot = document.createElement('i'), tag = document.createElement('b');
  tag.textContent = code; wrap.append(dot, tag);
  return L.divIcon({html: wrap, className: 'apt-icon', iconSize: [0, 0]});
}
function drawRoute(route, colour, theme) {
  routeLayer.clearLayers();
  if (!route) return;
  doneLine.setStyle({color: colour}).setLatLngs(route.done);
  aheadLine.setStyle({color: theme === 'dusk' ? '#9db3c6' : '#8a96a3'}).setLatLngs(route.ahead);
  routeLayer.addLayer(aheadLine).addLayer(doneLine);
  for (const end of [route.origin, route.destination]) {
    const near = (end === route.origin ? route.done[0] : route.ahead[route.ahead.length - 1]);
    routeLayer.addLayer(L.marker(near, {icon: airportIcon(end.iata || end.icao || ''), interactive: false, keyboard: false}));
  }
}

/* ---------------- flight panel ---------------- */
const metric = (value, unit) => value == null ? '—' : Math.round(value).toLocaleString() + (unit ? ' ' + unit : '');
function metricCell(value, label) {
  const div = document.createElement('div'), strong = document.createElement('strong'), small = document.createElement('small');
  strong.textContent = value; small.textContent = label; div.append(strong, small);
  return div;
}
function renderCard(s, current, info) {
  const units = s.settings.units === 'metric';
  const colour = cardColour(s, current);
  const [sheet, sheet2] = sheetColours(colour);
  $('flight-card').style.setProperty('--sheet', sheet);
  $('flight-card').style.setProperty('--sheet2', sheet2);
  $('flight-card').style.setProperty('--livery', colour);
  $('card-airline').textContent = info?.airline || current?.registration || 'Aircraft';
  $('card-callsign').textContent = current?.callsign || current?.registration || s.desk.aircraft_id;
  const typeLine = info?.type_name || current?.aircraft_type || '';
  $('card-type').textContent = current?.registration && info?.airline ? `${typeLine}${typeLine ? ' · ' : ''}${current.registration}` : typeLine;
  const entry = chooseArtwork(artCatalog, current?.aircraft_type, info?.category, current?.airline_icao);
  const wanted = entry.asset + entry.caption;
  if (wanted !== artKey) {
    artKey = wanted;
    const holder = $('card-art'); holder.replaceChildren();
    const ns = 'http://www.w3.org/2000/svg';
    const figure = document.createElementNS(ns,'svg');
    const bounds = entry.bounds || [0,0,entry.width || 1100,entry.height || 360];
    artworkAspect = bounds[2] / bounds[3];
    figure.setAttribute('viewBox',bounds.join(' '));
    figure.setAttribute('preserveAspectRatio','xMidYMid meet');
    figure.setAttribute('role','img'); figure.setAttribute('aria-label',entry.alt);
    const title = document.createElementNS(ns,'title'); title.textContent = entry.description || entry.alt;
    const image = document.createElementNS(ns,'image'); image.setAttribute('href',entry.asset);
    image.setAttribute('width',entry.width || 1100); image.setAttribute('height',entry.height || 360);
    image.setAttribute('aria-hidden','true');
    const caption = document.createElement('small'); caption.textContent = entry.caption;
    image.addEventListener('load',() => {
      if (!reducedMotion()) figure.animate([{opacity:0,transform:'translateY(5px)'},{opacity:1,transform:'none'}],{duration:260,easing:'ease-out'});
    });
    image.addEventListener('error',() => {
      if (image.dataset.fallback) return;
      image.dataset.fallback='true';
      const fallback=artCatalog.DEFAULT;
      if (fallback) {
        figure.setAttribute('viewBox',fallback.bounds.join(' '));
        image.setAttribute('width',fallback.width); image.setAttribute('height',fallback.height);
        artworkAspect=fallback.bounds[2]/fallback.bounds[3]; fitAircraftFrame();
      }
      image.setAttribute('href','/media/default-aircraft.png');
      figure.setAttribute('aria-label','Representative aircraft illustration'); caption.textContent='AIRCRAFT ILLUSTRATION';
    });
    figure.append(title,image); holder.append(figure,caption); fitAircraftFrame();
  }
  const route = info?.route;
  $('card-route').hidden = !route;
  if (route) {
    const pct = Math.round(route.progress * 100);
    $('route-from').textContent = route.origin.iata || route.origin.icao || '';
    $('route-to').textContent = route.destination.iata || route.destination.icao || '';
    $('route-from-city').textContent = route.origin.city || route.origin.name;
    $('route-to-city').textContent = route.destination.city || route.destination.name;
    $('journey').style.setProperty('--p', pct);
    const togo = units ? Math.round(route.remaining_nm * 1.852) + ' km' : route.remaining_nm.toLocaleString() + ' nm';
    const landed = current && current.altitude_ft === 0 && pct >= 90;
    $('route-note').textContent = landed ? `Arrived · ${route.destination.city || route.destination.iata}` : `${togo} to go · ${pct}% of the way`;
  }
  $('card-data').replaceChildren(
    metricCell(!current ? '—' : current.altitude_ft === 0 ? 'On ground' : metric(current.altitude_ft == null ? null : current.altitude_ft * (units ? .3048 : 1), units ? 'm' : 'ft'), 'Altitude'),
    metricCell(current ? metric(current.speed_kt == null ? null : current.speed_kt * (units ? 1.852 : 1), units ? 'km/h' : 'kt') : '—', 'Speed'),
    metricCell(current?.aircraft_type || '—', 'Type'));
  $('card-status').textContent = !current ? 'No current position. Waiting for coverage; this does not mean the flight has landed.' :
    `${current.source === 'demo' ? 'Synthetic demonstration · ' : ''}${current.stale ? 'Position stale · ' : ''}Seen ${Math.round(current.age_seconds)}s ago`;
  $('follow').textContent = s.desk.mode === 'follow' ? 'Stop following' : 'Follow this flight ↗';
  $('follow').disabled = !current || current.stale;
}

/* ---------------- main render ---------------- */
function render(s) {
  const previous = snapshot;
  snapshot = s; connected = true;
  if ($('settings-dialog').open && JSON.stringify(s.settings) === settingsAtOpen) settingsRevision = s.revision;
  const presets = s.settings.presets || [];
  if (JSON.stringify(presets) !== presetKey) {
    presetKey = JSON.stringify(presets);
    const places=document.querySelector('.places');
    places.replaceChildren(...presets.map(p=>{const b=document.createElement('button'); b.textContent='✈ '+p.name; b.onclick=()=>goPlace(p.latitude,p.longitude,p.zoom); return b;}));
  }
  if (s.artwork_revision !== artworkRevision) {
    artworkRevision=s.artwork_revision;
    api('artwork').then(result=>{artCatalog=result.catalog; artKey=null; if(snapshot)renderCard(snapshot,snapshot.aircraft.find(a=>a.id===snapshot.desk.aircraft_id),snapshot.selected_info); portalHooks.notify?.(snapshot);}).catch(()=>{});
  }
  if (s.desk.mode === 'follow' || previous && (previous.desk.mode !== s.desk.mode || previous.desk.aircraft_id !== s.desk.aircraft_id)) {
    idle = false; lastTouch = performance.now();
    if (s.desk.mode === 'map' || previous?.desk.aircraft_id !== s.desk.aircraft_id) expanded = false;
  }
  $('pairing').hidden = true; $('app').hidden = false;
  document.body.dataset.theme = s.settings.theme;
  if (!map) makeMap();
  $('connection').textContent = s.feed.status === 'demo' ? 'Demo' : s.feed.status === 'live' ? 'Live' : s.feed.status;
  $('source').textContent = s.attribution.name.toUpperCase();
  $('art-data-credit').textContent = s.attribution.name;
  // Required provider credit stays visible without navigating away from the kiosk.
  if (s.feed.message) note(s.feed.message);
  const mode = s.desk.mode, selectedId = s.desk.aircraft_id;
  const current = s.aircraft.find(a => a.id === selectedId);
  const info = s.selected_info;
  $('flight-view').classList.toggle('selected', panelVisible(s));
  $('flight-card').hidden = !panelVisible(s);

  // Following shows only that flight (lighter on the Pi, and calmer to look at).
  const visible = mode === 'follow' ? s.aircraft.filter(a => a.id === selectedId) : s.aircraft;
  syncMarkers(s, visible);
  $('mode').textContent = mode === 'follow' ? 'FOLLOWING' : `YOUR SKY · ${s.aircraft.length}`;

  if (mode !== 'map') {
    renderCard(s, current, info);
    $('flight-card').style.setProperty('--livery', cardColour(s,current));
  }

  // Apply the new panel geometry before fitting a following route.
  presentArt();
  const route = mode === 'follow' && current && !current.stale ? info?.route : null;
  drawRoute(route, cardColour(s,current), s.settings.theme);

  if (mode === 'follow' && current && !current.stale) {
    const key = selectedId + ':' + panelVisible(s) + (route ? route.origin.icao + route.destination.icao : '');
    if (route && key !== fitKey) {
      map.invalidateSize({pan: false, animate: false});
      suppressMap = true;
      try { map.fitBounds(L.latLngBounds([...route.done, ...route.ahead]), {paddingTopLeft: [remPx() * 2.5, remPx() * 4.8], paddingBottomRight: [remPx() * 5.2, remPx() * 3.6], maxZoom: 10, animate: false}); }
      finally { suppressMap = false; }
      fitKey = key;
    } else if (!route) {
      fitKey = key;
      map.invalidateSize({pan: false, animate: false});   // the map shrinks when the panel opens
      setMapView(current.latitude, current.longitude, lastMode !== 'follow' ? Math.max(10, map.getZoom()) : map.getZoom());
    }
  } else {
    fitKey = null;
    if (mode === 'detail' && current && centeredFor !== selectedId) {
      centeredFor = selectedId;
      map.invalidateSize({pan: false, animate: false});
      setMapView(current.latitude, current.longitude, Math.max(9, map.getZoom()));
    } else if (mode === 'map') {
      centeredFor = null;
      const nextKey = JSON.stringify(s.map_view);
      if (s.map_view && nextKey !== viewKey) setMapView(s.map_view.latitude, s.map_view.longitude, s.map_view.zoom);
      else if (!viewKey && s.settings.latitude != null) setMapView(s.settings.latitude, s.settings.longitude, 11);
      viewKey = nextKey || 'default';
    }
  }
  lastMode = mode; lastSelected = selectedId;

  if (idle && s.overhead?.aircraft) {
    renderCard(s, s.overhead.aircraft, s.overhead.info);
    $('card-status').textContent = 'Nearest airborne flight · ' + s.attribution.name;
  }
  presentArt();
  if (previous?.desk.mode === 'map' && mode !== 'map' && !idle && !reducedMotion()) {
    panelMotion?.cancel();
    panelMotion = $('flight-card').animate([
      {opacity:0,transform:matchMedia('(orientation:landscape)').matches ? 'translateX(24px)' : 'translateY(28px)'},
      {opacity:1,transform:'none'}
    ],{duration:300,easing:'cubic-bezier(.2,.8,.2,1)'});
  }
  if (document.body.dataset.controls === 'open') renderList(s);
  $('count').textContent = `${s.aircraft.length} aircraft`;
  const angle = s.display.confirmed_angle;
  for (const button of document.querySelectorAll('[data-angle]')) button.setAttribute('aria-pressed',String(Number(button.dataset.angle) === angle));
  portalHooks.notify?.(s);
  if (DISPLAY) syncDeskPairing(s);
  $('orientation-status').textContent = 'Saved: ' + (angle === 90 || angle === 270 ? 'Landscape' : 'Portrait') + (angle === 180 || angle === 270 ? ' · reversed' : '');
}
function renderList(s) {
  const units = s.settings.units === 'metric';
  $('aircraft-list').replaceChildren(...s.aircraft.map(a => {
    const button = document.createElement('button'); button.className = 'flight-chip';
    button.style.setProperty('--plane', s.settings.airline_colours[a.airline_icao] || (a.airline_icao === 'PTR' ? s.settings.airline_colours.POE : null) || NEUTRAL);
    button.textContent = a.callsign || a.registration || a.id;
    const sub = document.createElement('small');
    sub.textContent = a.altitude_ft == null ? `${a.aircraft_type || 'Aircraft'} · altitude unavailable`
      : `${a.aircraft_type || 'Aircraft'} · ${a.stale ? 'Position stale' : metric(a.altitude_ft * (units ? .3048 : 1), units ? 'm' : 'ft')}`;
    button.append(sub); button.onclick = () => command('detail', a.id);
    return button;
  }));
}

async function command(mode, aircraft_id = null, panel_open = true) {
  // Reopening the tracked aircraft must not cancel tracking.
  if (mode === 'detail' && snapshot?.desk.mode === 'follow' && snapshot.desk.aircraft_id === aircraft_id) mode = 'follow';
  if (mode !== 'map') {
    document.body.dataset.controls = DISPLAY ? 'closed' : 'open';
    $('controls-toggle').setAttribute('aria-expanded','false');
  }
  try { render(await api('desk', {mode, aircraft_id, panel_open})); } catch (e) { note(e.message); }
}
async function connect() {
  render(await api('snapshot'));
  stream?.close(); stream = new EventSource('/api/events');
  stream.addEventListener('snapshot', e => render(JSON.parse(e.data)));
  stream.onerror = () => { connected = false; $('connection').textContent = 'Reconnecting'; note('Connection interrupted. Showing the last received state.'); };
  stream.onopen = () => { connected = true; note(''); };
}

/* ---------------- controls ---------------- */
$('pair-form').onsubmit = async e => {
  e.preventDefault();
  try { await api('pair', {code: $('pair-code').value, device_name:$('device-name')?.value.trim() || 'Phone'}); $('pair-code').value = ''; await connect(); }
  catch (error) { $('pair-error').textContent = error.message; }
};
$('search-form').onsubmit = async e => {
  e.preventDefault(); const button = e.currentTarget.querySelector('button'); button.disabled = true;
  try {
    const result = await api('search?q=' + encodeURIComponent($('query').value));
    if (!result.aircraft.length) { note(result.message); return; }
    if (result.aircraft.length === 1) { note(''); await command('follow', result.aircraft[0].id); }
    else note('Several aircraft matched. Select the correct one from the aircraft list.');
  } catch (error) { note(error.message); } finally { button.disabled = false; }
};
async function goPlace(latitude, longitude, zoom) {
  try {
    await command('map');
    await api('map-view', {latitude, longitude, zoom});
    setMapView(latitude, longitude, zoom);
  } catch (error) { note(error.message); }
}
$('place-ykf').onclick = () => goPlace(43.46056, -80.38056, 11);
$('place-yyz').onclick = () => goPlace(43.6777, -79.6248, 10);
$('map-all').onclick = () => command('map');
$('map-home').onclick = async () => {  // back to the map, centred on home
  await command('map');
  const s = snapshot?.settings;
  if (s?.latitude != null) { await api('map-view', {latitude: s.latitude, longitude: s.longitude, zoom: 10}).catch(() => {}); setMapView(s.latitude, s.longitude, 10); }
};
$('zoom-in').onclick = () => map?.zoomIn();
$('zoom-out').onclick = () => map?.zoomOut();
function closePanel() {
  expanded = false;
  if (snapshot?.desk.mode === 'follow') command('follow', snapshot.desk.aircraft_id, false);
  else command('map');
}
$('card-close').onclick = closePanel;
$('follow').onclick = async () => {
  if (snapshot.desk.mode === 'follow') {
    // Explicit stop bypasses the reopen shortcut in command().
    try { render(await api('desk', {mode:'detail', aircraft_id:snapshot.desk.aircraft_id, panel_open:true})); } catch(e) { note(e.message); }
  } else command('follow', snapshot.desk.aircraft_id);
};

function addAirlineColour(code, colour) {
  const label = document.createElement('label'), input = document.createElement('input');
  label.textContent = code; input.type = 'color'; input.value = colour; input.dataset.airline = code;
  const remove = document.createElement('button'); remove.type = 'button'; remove.textContent = '×';
  remove.setAttribute('aria-label', 'Remove ' + code); remove.onclick = () => { label.remove(); settingsDirty = true; };
  label.append(input, remove); $('colour-settings').append(label);
}
$('add-airline').onclick = () => {
  const code = $('new-airline').value.trim().toUpperCase();
  if (!/^[A-Z]{3}$/.test(code)) { $('settings-error').textContent = 'Enter a three-letter airline ICAO code.'; return; }
  if ([...$('colour-settings').querySelectorAll('input')].some(x => x.dataset.airline === code)) { $('settings-error').textContent = 'That airline is already in the list.'; return; }
  addAirlineColour(code, $('new-colour').value); $('new-airline').value = ''; $('settings-error').textContent = ''; settingsDirty = true;
};
$('settings-open').onclick = () => {
  if (!snapshot) return;
  settingsRevision = snapshot.revision; settingsAtOpen = JSON.stringify(snapshot.settings); settingsDirty = false;
  const form = $('settings-form');
  for (const [key, value] of Object.entries(snapshot.settings)) if (form.elements[key]) form.elements[key].value = value ?? '';
  $('colour-settings').replaceChildren();
  for (const [code, colour] of Object.entries(snapshot.settings.airline_colours)) addAirlineColour(code, colour);
  const credits = $('artwork-credits'); credits.replaceChildren();
  for (const [type, entry] of Object.entries(artCatalog)) {
    const line = document.createElement('p'); line.textContent = type + ': ' + entry.credit + '. ' + entry.source + ' · ' + entry.license;
    credits.append(line);
  }
  portalHooks.load?.(snapshot);
  $('settings-error').textContent = ''; $('settings-dialog').showModal();
};
$('settings-form').addEventListener('input', () => { settingsDirty = true; });
$('settings-form').addEventListener('change', () => { settingsDirty = true; });
$('settings-close').onclick = () => {
  if (settingsDirty) $('settings-form').requestSubmit();
  else $('settings-dialog').close();
};
$('settings-form').onsubmit = async e => {
  e.preventDefault(); const form = e.currentTarget, settings = {...snapshot.settings};
  for (const key of ['name', 'theme', 'units', 'provider']) settings[key] = form.elements[key].value;
  if (settings.provider === 'adsbfi' && (form.elements.latitude.value === '' || form.elements.longitude.value === '')) { $('settings-error').textContent = 'Add both map-centre coordinates to use live data, then tap Save.'; return; }
  for (const key of ['radius_nm', 'poll_seconds']) settings[key] = Number(form.elements[key].value);
  for (const key of ['latitude', 'longitude']) settings[key] = form.elements[key].value === '' ? null : Number(form.elements[key].value);
  settings.airline_colours = Object.fromEntries([...$('colour-settings').querySelectorAll('input')].map(i => [i.dataset.airline, i.value]));
  try {
    if(portalHooks.save) Object.assign(settings, portalHooks.save());
    render(await api('settings', {expected_revision: settingsRevision, settings}, 'PUT')); settingsDirty = false; $('settings-dialog').close(); note('Shared settings saved.'); }
  catch (error) { $('settings-error').textContent = error.message; }
};
for (const button of document.querySelectorAll('[data-angle]')) button.onclick = async () => {
  const buttons = [...document.querySelectorAll('[data-angle]')];
  for (const b of buttons) b.disabled = true;
  $('orientation-status').textContent = 'Saving orientation…';
  try {
    await api('display/rotation', {angle: Number(button.dataset.angle)});
    render(await api('snapshot')); if(JSON.stringify(snapshot.settings)===settingsAtOpen) settingsRevision = snapshot.revision;
  } catch (error) { $('settings-error').textContent = error.message; }
  finally { for (const b of buttons) b.disabled = false; }
};
$('logout').onclick = async () => { await api('logout', {}); $('settings-dialog').close(); showPair(); };
setInterval(() => {
  if (!connected && snapshot) for (const e of markers.values()) e.marker.setOpacity(.35);
}, 1000);
addEventListener('resize', () => { for (const e of markers.values()) e.key = null; });  // re-size marker icons
if ('serviceWorker' in navigator && window.isSecureContext) {
  navigator.serviceWorker.register('/sw.js').then(() => { $('pwa-status').textContent = 'App shell available offline'; }).catch(() => { $('pwa-status').textContent = 'Browser mode'; });
} else $('pwa-status').textContent = 'Browser portal · HTTPS needed for full PWA';
fetch('/media/catalog.json').then(r => r.ok ? r.json() : {}).then(c => { artCatalog = c; }).catch(() => {}).then(() => connect()).catch(e => { if (!snapshot) { showPair(); if (!e.message.includes('Pair')) $('pair-error').textContent = e.message; } });

let kioskPairing, kioskPairingBusy=false;
async function syncDeskPairing(s) {
  const need = !s.pairing?.paired_devices || (s.pairing?.show_until || 0) > Date.now()/1000;
  const screen=$('desk-pairing');
  if(!screen) return;
  screen.hidden=!need; $('app').hidden=need;
  if(need && !kioskPairingBusy) {
    kioskPairingBusy=true;
    try {
      kioskPairing=await api('kiosk/pairing');
      $('desk-code').textContent=kioskPairing.code;
      $('desk-portal-url').textContent=kioskPairing.portal_url;
      $('desk-pair-back').hidden=!s.pairing?.paired_devices;
    } catch(e) { $('desk-code').textContent='Connecting…'; }
    finally{kioskPairingBusy=false;}
  }
}
if(DISPLAY) {
  $('pair-form').hidden=true;
  $('pairing').querySelector('p').textContent='Connecting to your desk. No code needs to be entered here.';
  if($('desk-pair-back')) $('desk-pair-back').onclick=async()=>{await api('pairing/hide',{});};
  const pairButton=document.createElement('button');pairButton.type='button';pairButton.textContent='Pair another phone';
  pairButton.onclick=async()=>{$('settings-dialog').close();await api('pairing/show',{});};
  $('logout').hidden=true;$('logout').before(pairButton);
}
export {api, render, command, goPlace};
