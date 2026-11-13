"""Nearest fresh airborne aircraft above a private observer location."""
import math
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field

class Observer(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    idle_minutes: int = Field(default=5, ge=1, le=60)

def distance_nm(lat1, lon1, lat2, lon2):
    a, b = math.radians(lat1), math.radians(lat2)
    dlat, dlon = b-a, math.radians(lon2-lon1)
    h = math.sin(dlat/2)**2 + math.cos(a)*math.cos(b)*math.sin(dlon/2)**2
    return 3440.065 * 2 * math.asin(math.sqrt(min(1, max(0, h))))

def nearest_airborne(rows, observer: Optional[Observer], now):
    if observer is None:
        return None, None
    eligible = [(distance_nm(observer.latitude, observer.longitude, a.latitude, a.longitude), a.id, a)
                for a in rows if 0 <= now-a.observed_at <= 45 and a.altitude_ft is not None and a.altitude_ft > 0]
    eligible = [row for row in eligible if row[0] <= 50]
    if not eligible:
        return None, None
    distance, _, aircraft = min(eligible, key=lambda row: (row[0], row[1]))
    return aircraft, distance
