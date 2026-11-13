import re
from typing import Dict, Literal, Optional
from pydantic import BaseModel, ConfigDict, Field, model_validator


class Model(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)


class Place(Model):
    name: str = Field(min_length=1, max_length=24)
    latitude: float = Field(ge=-85, le=85)
    longitude: float = Field(ge=-180, le=180)
    zoom: float = Field(default=11, ge=3, le=15)


class HomePosition(Model):
    latitude: float = Field(ge=-85, le=85)
    longitude: float = Field(ge=-180, le=180)
    label: str = Field(default='Home', max_length=180)
    idle_minutes: int = Field(default=5, ge=1, le=60)


class Settings(Model):
    name: str = Field(default='Flight Desk', min_length=1, max_length=40)
    presets: list[Place] = Field(default_factory=lambda: [Place(name='Waterloo',latitude=43.46056,longitude=-80.38056,zoom=11), Place(name='Pearson',latitude=43.6777,longitude=-79.6248,zoom=10)], max_length=8)
    observer: Optional[HomePosition] = None
    provider: Literal['demo', 'adsbfi'] = 'demo'
    latitude: Optional[float] = Field(default=None, ge=-90, le=90)
    longitude: Optional[float] = Field(default=None, ge=-180, le=180)
    radius_nm: int = Field(default=40, ge=1, le=250)
    poll_seconds: int = Field(default=10, ge=10, le=120)
    units: Literal['aviation', 'metric'] = 'aviation'
    theme: Literal['paper', 'dusk'] = 'paper'
    airline_colours: Dict[str, str] = Field(default_factory=lambda: {
        'ACA': '#d96b54', 'WJA': '#397f83', 'POE': '#685d91'})

    @model_validator(mode='after')
    def check(self):
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError('Set both latitude and longitude, or leave both blank')
        if self.provider != 'demo' and self.latitude is None:
            raise ValueError('Set your map centre before enabling internet data')
        if len(self.airline_colours) > 100:
            raise ValueError('At most 100 airline colours')
        for code, colour in self.airline_colours.items():
            if not re.fullmatch(r'[A-Z]{3}', code) or not re.fullmatch(r'#[0-9a-fA-F]{6}', colour):
                raise ValueError('Use a three-letter ICAO airline code and a #RRGGBB colour')
        return self


class SettingsWrite(Model):
    expected_revision: int = Field(ge=0)
    settings: Settings


class Aircraft(Model):
    id: str
    callsign: Optional[str] = None
    registration: Optional[str] = None
    aircraft_type: Optional[str] = None
    airline_icao: Optional[str] = None
    latitude: float
    longitude: float
    altitude_ft: Optional[float] = None
    speed_kt: Optional[float] = None
    heading_deg: Optional[float] = None
    observed_at: float
    source: str
    route: Optional[dict] = None


class DeskCommand(Model):
    panel_open: bool = True
    mode: Literal['map', 'detail', 'follow']
    aircraft_id: Optional[str] = Field(default=None, pattern=r'^[0-9a-f]{6}$')

    @model_validator(mode='after')
    def check(self):
        if self.mode != 'map' and self.aircraft_id is None:
            raise ValueError('Choose an aircraft')
        if self.mode == 'map':
            self.aircraft_id = None
            self.panel_open = False
        elif self.mode == 'detail':
            self.panel_open = True
        return self


class RotationRequest(Model):
    angle: Literal[0, 90, 180, 270]


class RotationConfirm(Model):
    token: str = Field(min_length=20, max_length=100)


class PairRequest(Model):
    device_name: str = Field(default='Phone', min_length=1, max_length=40)
    code: str = Field(pattern=r'^\d{6}$')


class MapView(Model):
    latitude: float = Field(ge=-85, le=85)
    longitude: float = Field(ge=-180, le=180)
    zoom: float = Field(ge=2, le=15)
