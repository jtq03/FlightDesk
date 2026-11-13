# Flight Desk

A personal, touch-first live aircraft display for Raspberry Pi 5 and the official 5-inch Touch Display 2, with a shared phone remote.

The Pi owns the live flight state. Multiple paired phones can search, select and follow flights, edit airline colours and locations, manage artwork, and adjust display settings. The remote is an installable PWA served over a private Tailscale HTTPS connection.

## Privacy

This repository contains source and credited built-in illustrations only. Pairing codes, sessions, the private home position and uploaded images live in protected directories on the Pi and are never committed here.

## Runtime

Python/FastAPI, SQLite and a buildless JavaScript/Leaflet frontend. The desk is `/display`; the phone remote is `/portal`. Live data comes from adsb.fi; address search is a user-triggered OpenStreetMap Nominatim lookup.

Implementation, tests and setup notes follow in the next commit.
