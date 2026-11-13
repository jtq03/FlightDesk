"""A rights-aware media boundary; remote photo integration is a separate adapter.

Registered local images can be added without changing UI/API contracts. Unknown
aircraft never inherit a photograph of another registration by accident.
"""
from .aircraft_types import describe_type
import json
import re
from pathlib import Path


class MediaCatalog:
    def __init__(self, root: Path):
        self.root = root

    def resolve(self, aircraft):
        catalog = self.root / 'media' / 'catalog.json'
        entries = json.loads(catalog.read_text()) if catalog.exists() else {}
        category = describe_type(aircraft.aircraft_type)[1]
        branded = 'POE_' + (aircraft.aircraft_type or '') if aircraft.airline_icao in {'POE','PTR'} else None
        for key, accuracy in [(aircraft.id, 'exact_aircraft'), (branded, 'aircraft_type'), (aircraft.aircraft_type, 'aircraft_type'),
                              ('class_' + category, 'aircraft_class'), ('DEFAULT', 'generic')]:
            item = entries.get(key) if key else None
            if not item:
                continue
            asset = item.get('asset', '')
            if not re.fullmatch(r'/media/[A-Za-z0-9_-]+\.(jpg|png|webp|svg)', asset):
                continue
            if not (self.root / asset.lstrip('/')).is_file() or not item.get('credit'):
                continue
            return {'kind': item.get('kind', 'photograph'), 'accuracy': accuracy,
                    'asset': asset, 'credit': item['credit'], 'alt': item.get('alt', aircraft.aircraft_type or 'Aircraft')}
        return {'kind': 'illustration', 'accuracy': 'generic', 'asset': '/aircraft.svg',
                'credit': 'Flight Desk · generic aircraft illustration', 'alt': 'Stylised passenger aircraft illustration'}
