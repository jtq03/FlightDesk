"""Aircraft type and airline reference data for the flight panel.

Types are ICAO type designators (what ADS-B reports, e.g. C172, A21N, B77W).
Each maps to a friendly name and an art category; the browser draws the matching
side-profile illustration. Unknown types fall back to a neutral airliner when the
type looks like a jet, otherwise to a plain label with no invented name.
"""
from typing import Optional

# category: single_high, single_low, twin_prop, turboprop, regional, narrow,
#           wide_twin, wide_quad, bizjet, helicopter
TYPES = {
    # Light single-engine, high wing
    'C150': ('Cessna 150', 'single_high'), 'C152': ('Cessna 152', 'single_high'),
    'C172': ('Cessna 172 Skyhawk', 'single_high'), 'C175': ('Cessna 175', 'single_high'),
    'C177': ('Cessna 177 Cardinal', 'single_high'), 'C182': ('Cessna 182 Skylane', 'single_high'),
    'C185': ('Cessna 185 Skywagon', 'single_high'), 'C206': ('Cessna 206', 'single_high'),
    'C210': ('Cessna 210 Centurion', 'single_high'), 'C208': ('Cessna 208 Caravan', 'single_high'),
    'P28A': ('Piper Cherokee', 'single_low'), 'P28B': ('Piper Cherokee 235', 'single_low'),
    'P28R': ('Piper Arrow', 'single_low'), 'PA28': ('Piper Cherokee', 'single_low'),
    'PA32': ('Piper Cherokee Six', 'single_low'), 'P32R': ('Piper Lance', 'single_low'),
    'PA46': ('Piper Malibu', 'single_low'), 'SR20': ('Cirrus SR20', 'single_low'),
    'SR22': ('Cirrus SR22', 'single_low'), 'S22T': ('Cirrus SR22T', 'single_low'),
    'BE35': ('Beechcraft Bonanza', 'single_low'), 'BE36': ('Beechcraft Bonanza A36', 'single_low'),
    'M20P': ('Mooney M20', 'single_low'), 'M20T': ('Mooney M20 Turbo', 'single_low'),
    'DA40': ('Diamond DA40', 'single_low'), 'TB20': ('Socata TB-20', 'single_low'),
    'PC12': ('Pilatus PC-12', 'single_low'), 'TBM9': ('Daher TBM 900', 'single_low'),
    'TBM8': ('Daher TBM 850', 'single_low'),
    # Light twins
    'BE58': ('Beechcraft Baron', 'twin_prop'), 'BE55': ('Beechcraft Baron 55', 'twin_prop'),
    'PA34': ('Piper Seneca', 'twin_prop'), 'PA44': ('Piper Seminole', 'twin_prop'),
    'DA42': ('Diamond DA42', 'twin_prop'), 'DA62': ('Diamond DA62', 'twin_prop'),
    'C310': ('Cessna 310', 'twin_prop'), 'C340': ('Cessna 340', 'twin_prop'),
    'C421': ('Cessna 421', 'twin_prop'), 'AEST': ('Piper Aerostar', 'twin_prop'),
    # Turboprop airliners and commuters
    'DH8A': ('De Havilland Dash 8-100', 'turboprop'), 'DH8B': ('De Havilland Dash 8-200', 'turboprop'),
    'DH8C': ('De Havilland Dash 8-300', 'turboprop'), 'DH8D': ('De Havilland Dash 8 Q400', 'turboprop'),
    'AT43': ('ATR 42', 'turboprop'), 'AT45': ('ATR 42-500', 'turboprop'),
    'AT72': ('ATR 72', 'turboprop'), 'AT76': ('ATR 72-600', 'turboprop'),
    'B190': ('Beechcraft 1900', 'turboprop'), 'BE20': ('Beechcraft King Air 200', 'turboprop'),
    'BE9L': ('Beechcraft King Air 90', 'turboprop'), 'BE10': ('Beechcraft King Air 100', 'turboprop'),
    'B350': ('Beechcraft King Air 350', 'turboprop'), 'SW4': ('Fairchild Metroliner', 'turboprop'),
    'SF34': ('Saab 340', 'turboprop'), 'JS32': ('Jetstream 32', 'turboprop'),
    'DHC6': ('De Havilland Twin Otter', 'turboprop'), 'DHC2': ('De Havilland Beaver', 'single_high'),
    'DHC3': ('De Havilland Otter', 'single_high'), 'E120': ('Embraer Brasilia', 'turboprop'),
    'C441': ('Cessna Conquest', 'turboprop'), 'P180': ('Piaggio Avanti', 'turboprop'),
    # Regional jets
    'E170': ('Embraer 170', 'regional'), 'E75S': ('Embraer 175', 'regional'),
    'E75L': ('Embraer 175', 'regional'), 'E190': ('Embraer 190', 'regional'),
    'E195': ('Embraer 195', 'regional'), 'E290': ('Embraer E190-E2', 'regional'),
    'E295': ('Embraer E195-E2', 'regional'), 'E135': ('Embraer ERJ-135', 'regional'),
    'E145': ('Embraer ERJ-145', 'regional'), 'CRJ2': ('Bombardier CRJ-200', 'regional'),
    'CRJ7': ('Bombardier CRJ-700', 'regional'), 'CRJ9': ('Bombardier CRJ-900', 'regional'),
    'CRJX': ('Bombardier CRJ-1000', 'regional'), 'BCS1': ('Airbus A220-100', 'regional'),
    'BCS3': ('Airbus A220-300', 'regional'),
    # Narrow-body airliners
    'A318': ('Airbus A318', 'narrow'), 'A319': ('Airbus A319', 'narrow'),
    'A320': ('Airbus A320', 'narrow'), 'A321': ('Airbus A321', 'narrow'),
    'A19N': ('Airbus A319neo', 'narrow'), 'A20N': ('Airbus A320neo', 'narrow'),
    'A21N': ('Airbus A321neo', 'narrow'),
    'B731': ('Boeing 737-100', 'narrow'), 'B732': ('Boeing 737-200', 'narrow'),
    'B733': ('Boeing 737-300', 'narrow'), 'B734': ('Boeing 737-400', 'narrow'),
    'B735': ('Boeing 737-500', 'narrow'), 'B736': ('Boeing 737-600', 'narrow'),
    'B737': ('Boeing 737-700', 'narrow'), 'B738': ('Boeing 737-800', 'narrow'),
    'B739': ('Boeing 737-900', 'narrow'), 'B37M': ('Boeing 737 MAX 7', 'narrow'),
    'B38M': ('Boeing 737 MAX 8', 'narrow'), 'B39M': ('Boeing 737 MAX 9', 'narrow'),
    'B3XM': ('Boeing 737 MAX 10', 'narrow'),
    'B752': ('Boeing 757-200', 'narrow'), 'B753': ('Boeing 757-300', 'narrow'),
    'MD80': ('McDonnell Douglas MD-80', 'narrow'), 'MD82': ('McDonnell Douglas MD-82', 'narrow'),
    'MD83': ('McDonnell Douglas MD-83', 'narrow'), 'MD88': ('McDonnell Douglas MD-88', 'narrow'),
    'MD90': ('McDonnell Douglas MD-90', 'narrow'), 'B712': ('Boeing 717', 'narrow'),
    # Wide-body twins
    'A332': ('Airbus A330-200', 'wide_twin'), 'A333': ('Airbus A330-300', 'wide_twin'),
    'A338': ('Airbus A330-800neo', 'wide_twin'), 'A339': ('Airbus A330-900neo', 'wide_twin'),
    'A359': ('Airbus A350-900', 'wide_twin'), 'A35K': ('Airbus A350-1000', 'wide_twin'),
    'B762': ('Boeing 767-200', 'wide_twin'), 'B763': ('Boeing 767-300', 'wide_twin'),
    'B764': ('Boeing 767-400', 'wide_twin'), 'B772': ('Boeing 777-200', 'wide_twin'),
    'B77L': ('Boeing 777-200LR', 'wide_twin'), 'B77W': ('Boeing 777-300ER', 'wide_twin'),
    'B773': ('Boeing 777-300', 'wide_twin'), 'B778': ('Boeing 777-8', 'wide_twin'),
    'B779': ('Boeing 777-9', 'wide_twin'), 'B788': ('Boeing 787-8 Dreamliner', 'wide_twin'),
    'B789': ('Boeing 787-9 Dreamliner', 'wide_twin'), 'B78X': ('Boeing 787-10 Dreamliner', 'wide_twin'),
    # Wide-body quads
    'A343': ('Airbus A340-300', 'wide_quad'), 'A346': ('Airbus A340-600', 'wide_quad'),
    'A388': ('Airbus A380-800', 'wide_quad'), 'B744': ('Boeing 747-400', 'wide_quad'),
    'B748': ('Boeing 747-8', 'wide_quad'), 'B74S': ('Boeing 747SP', 'wide_quad'),
    # Business jets
    'LJ35': ('Learjet 35', 'bizjet'), 'LJ40': ('Learjet 40', 'bizjet'), 'LJ45': ('Learjet 45', 'bizjet'),
    'LJ60': ('Learjet 60', 'bizjet'), 'LJ75': ('Learjet 75', 'bizjet'),
    'C25A': ('Cessna Citation CJ2', 'bizjet'), 'C25B': ('Cessna Citation CJ3', 'bizjet'),
    'C25C': ('Cessna Citation CJ4', 'bizjet'), 'C510': ('Cessna Citation Mustang', 'bizjet'),
    'C525': ('Cessna CitationJet', 'bizjet'), 'C550': ('Cessna Citation II', 'bizjet'),
    'C560': ('Cessna Citation V', 'bizjet'), 'C56X': ('Cessna Citation Excel', 'bizjet'),
    'C680': ('Cessna Citation Sovereign', 'bizjet'), 'C68A': ('Cessna Citation Latitude', 'bizjet'),
    'C700': ('Cessna Citation Longitude', 'bizjet'), 'C750': ('Cessna Citation X', 'bizjet'),
    'CL30': ('Bombardier Challenger 300', 'bizjet'), 'CL35': ('Bombardier Challenger 350', 'bizjet'),
    'CL60': ('Bombardier Challenger 600', 'bizjet'), 'GLEX': ('Bombardier Global Express', 'bizjet'),
    'GL5T': ('Bombardier Global 5000', 'bizjet'), 'GL6T': ('Bombardier Global 6000', 'bizjet'),
    'GLF4': ('Gulfstream IV', 'bizjet'), 'GLF5': ('Gulfstream V', 'bizjet'),
    'GLF6': ('Gulfstream G650', 'bizjet'), 'G280': ('Gulfstream G280', 'bizjet'),
    'FA7X': ('Dassault Falcon 7X', 'bizjet'), 'FA50': ('Dassault Falcon 50', 'bizjet'),
    'F900': ('Dassault Falcon 900', 'bizjet'), 'F2TH': ('Dassault Falcon 2000', 'bizjet'),
    'E55P': ('Embraer Phenom 300', 'bizjet'), 'E50P': ('Embraer Phenom 100', 'bizjet'),
    'H25B': ('Hawker 800', 'bizjet'), 'PRM1': ('Beechcraft Premier I', 'bizjet'),
    'HDJT': ('Honda HA-420 HondaJet', 'bizjet'), 'EA50': ('Eclipse 500', 'bizjet'),
    'SF50': ('Cirrus Vision Jet', 'bizjet'),
    # Helicopters
    'R22': ('Robinson R22', 'helicopter'), 'R44': ('Robinson R44', 'helicopter'),
    'R66': ('Robinson R66', 'helicopter'), 'B06': ('Bell 206 JetRanger', 'helicopter'),
    'B407': ('Bell 407', 'helicopter'), 'B412': ('Bell 412', 'helicopter'),
    'B429': ('Bell 429', 'helicopter'), 'EC35': ('Airbus H135', 'helicopter'),
    'EC30': ('Airbus H130', 'helicopter'), 'EC45': ('Airbus H145', 'helicopter'),
    'AS50': ('Airbus AS350', 'helicopter'), 'A109': ('Leonardo AW109', 'helicopter'),
    'A139': ('Leonardo AW139', 'helicopter'), 'S76': ('Sikorsky S-76', 'helicopter'),
    'S92': ('Sikorsky S-92', 'helicopter'), 'H60': ('Sikorsky Black Hawk', 'helicopter'),
    'EN28': ('Enstrom 280', 'helicopter'), 'H500': ('MD 500', 'helicopter'),
}

AIRLINES = {
    'ACA': 'Air Canada', 'ROU': 'Air Canada Rouge', 'JZA': 'Air Canada Express', 'WJA': 'WestJet',
    'WEN': 'WestJet Encore', 'POE': 'Porter Airlines', 'PTR': 'Porter Airlines', 'TSC': 'Air Transat', 'FLE': 'Flair Airlines',
    'SWG': 'Sunwing', 'LYM': 'Lynx Air', 'PAL': 'PAL Airlines', 'CJT': 'Cargojet',
    'UAL': 'United Airlines', 'DAL': 'Delta Air Lines', 'AAL': 'American Airlines',
    'SWA': 'Southwest Airlines', 'JBU': 'JetBlue', 'ASA': 'Alaska Airlines', 'NKS': 'Spirit Airlines',
    'FFT': 'Frontier Airlines', 'SKW': 'SkyWest Airlines', 'RPA': 'Republic Airways',
    'ENY': 'Envoy Air', 'EDV': 'Endeavor Air', 'PDT': 'Piedmont Airlines', 'ASH': 'Mesa Airlines',
    'FDX': 'FedEx Express', 'UPS': 'UPS Airlines', 'GTI': 'Atlas Air', 'ABX': 'ABX Air',
    'BAW': 'British Airways', 'VIR': 'Virgin Atlantic', 'EIN': 'Aer Lingus', 'AFR': 'Air France',
    'KLM': 'KLM', 'DLH': 'Lufthansa', 'SWR': 'Swiss', 'AUA': 'Austrian', 'IBE': 'Iberia',
    'TAP': 'TAP Air Portugal', 'AZA': 'ITA Airways', 'SAS': 'Scandinavian Airlines',
    'FIN': 'Finnair', 'ICE': 'Icelandair', 'THY': 'Turkish Airlines', 'UAE': 'Emirates',
    'QTR': 'Qatar Airways', 'ETD': 'Etihad', 'SIA': 'Singapore Airlines', 'CPA': 'Cathay Pacific',
    'ANA': 'All Nippon Airways', 'JAL': 'Japan Airlines', 'KAL': 'Korean Air', 'AIC': 'Air India',
    'QFA': 'Qantas', 'ANZ': 'Air New Zealand', 'CSN': 'China Southern', 'CCA': 'Air China',
    'CES': 'China Eastern', 'ELY': 'El Al', 'ETH': 'Ethiopian Airlines', 'LAN': 'LATAM',
    'AVA': 'Avianca', 'CMP': 'Copa Airlines', 'AMX': 'Aeromexico', 'VOI': 'Volaris',
    'AMF': 'Ameriflight', 'LXJ': 'Flexjet', 'EJA': 'NetJets',
}

JETS = {'narrow', 'wide_twin', 'wide_quad', 'regional', 'bizjet'}


def describe_type(code: Optional[str]):
    """Return (friendly_name | None, art_category) for an ICAO type designator."""
    if not code:
        return None, 'narrow'
    code = code.upper()
    if code in TYPES:
        return TYPES[code]
    # Reasonable fallbacks by family prefix; names are left out rather than guessed.
    if code.startswith(('A3', 'A2')):
        return None, 'wide_twin' if code[:2] == 'A3' and code[2] in '3456' else 'narrow'
    if code.startswith('B7'):
        return None, 'wide_twin' if code[2] in '678' else 'narrow'
    if code.startswith('C1'):
        return None, 'single_high'
    if code.startswith(('PA', 'P2', 'SR', 'M2', 'BE3')):
        return None, 'single_low'
    return None, 'narrow'


def airline_name(icao: Optional[str]) -> Optional[str]:
    return AIRLINES.get(icao) if icao else None
