# Flight Desk

A personal live aircraft display for a Raspberry Pi 5 and the official 5-inch Touch Display 2, with a shared phone remote.

## Use it

- The desk opens `/display` in its local kiosk. It authenticates itself automatically.
- With no paired phones, the desk shows a six-digit pairing code and its portal address.
- Open `/portal` on a phone, name the phone, and enter the code shown on the desk.
- Pair a second phone using the same code. Each phone has an independent session and can be unpaired separately.
- Search a flight, then tap **Follow**. The desk and all phones receive shared state over server-sent events.
- Close a following card to leave more room for its map. Reopen the plane to see its card; Home, airport shortcuts or Stop following ends tracking.

## Control tower

Phone settings include theme, measurement units, map centre, refresh interval (minimum 10 seconds), coverage range, up to eight location shortcuts, the home point used for nearest-overhead art, airline colours and an aircraft image library. Waterloo and Pearson are the default shortcuts.

Address search is an explicit OpenStreetMap Nominatim lookup, never keystroke autocomplete. Coordinates work without using geocoding. Uploaded PNG/JPEG/WebP images are validated, resized and re-encoded without EXIF/GPS metadata. Restore original resets an artwork override. The model, Porter edition, class and universal fallback entries are listed in the library.

## Private phone access and PWA

The live PWA is served by the Pi over private Tailscale Serve HTTPS. Phones must be connected to the same private Tailscale network (or be explicitly shared access). This works away from home while the Pi is online. Public Funnel is not required.

Open the Pi's HTTPS `/portal` address in Safari and choose Share → Add to Home Screen on iPhone, or Install/Add to Home Screen in a supported Android browser. An ordinary home-Wi-Fi HTTP address can be used as a browser portal; full service-worker/PWA support needs HTTPS.

GitHub Pages does not run this Python server or bridge into a home network. The repository stores the source; the Pi's secure URL is the app to install.

## Run locally

Python 3.11+ recommended (the Pi uses 3.13).

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
FLIGHTDESK_STATE=.state .venv/bin/python -m uvicorn flightdesk.app:app --host 127.0.0.1 --port 8765
```

The default provider is explicitly labelled demonstration data. To enable adsb.fi, save a map centre in settings and select Live. Live service coverage and flight-number resolution are limited by the provider; flights without positions or verified endpoints are not fabricated.

For a physical Pi kiosk, set `FLIGHTDESK_DISPLAY_OUTPUT=DSI-2`. `FLIGHTDESK_HOSTS` is an explicit comma-separated allowlist of localhost and the device's LAN/private HTTPS hostnames. `FLIGHTDESK_PORTAL_URL` sets the address shown on the pairing screen. The app must run behind a trusted loopback reverse proxy for HTTPS forwarded headers, never trust arbitrary forwarded headers.

Private observer config from an earlier installation is migrated once into the protected state database. User state and uploaded artwork live outside this source checkout. Session cookies are HTTP-only and same-site; API writes reject cross-origin requests. Pairing attempts and image sizes are bounded.

## Test

```sh
PYTHONPATH=. .venv/bin/python -m pytest tests -q
```

Tests cover authentication boundaries, independent phone revocation, shared follow state, physical orientation persistence, settings/observer/preset persistence, image validation and restoration, live provider parsing and overhead selection.

## Artwork and attribution

Built-in aircraft illustrations and license/source credits are in `web/media/catalog.json`, also visible in settings. Generated Porter and neutral aircraft studies are representative illustrations, not photographs of an observed registration. Map data © OpenStreetMap contributors. Live position data: adsb.fi. Route information is shown only when known and plausible.

No pairing codes, sessions, private home coordinates, personal uploads or Tailscale keys are included in this repository.
