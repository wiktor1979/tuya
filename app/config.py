"""Konfiguracja aplikacji - zmienne środowiskowe i stałe."""
import os
from dotenv import load_dotenv
from typing import List, Dict, Optional, Any

load_dotenv()

# Konfiguracja Tuya Pulsar (EU) - obsługa wielu kont
# Format: lista słowników z kluczami: access_id, access_key, devices (lista ID urządzeń)
TUYA_ACCOUNTS: List[Dict[str, Any]] = []

# Pobierz konfigurację z environment variables (dla wstecznej kompatybilności)
single_access_id = os.environ.get("TUYA_ACCESS_ID")
single_access_key = os.environ.get("TUYA_ACCESS_KEY")
single_device_ids = os.environ.get("TUYA_DEVICE_IDS", "")

if single_access_id and single_access_key:
    # Pojedyncze konto - skonwertuj do formatu listy
    device_list = [d.strip() for d in single_device_ids.split(",") if d.strip()]
    TUYA_ACCOUNTS.append({
        "access_id": single_access_id,
        "access_key": single_access_key,
        "devices": device_list
    })

# Sprawdź czy istnieje konfiguracja dla wielu kont (TUYA_ACCOUNTS_JSON)
accounts_json = os.environ.get("TUYA_ACCOUNTS_JSON")
if accounts_json:
    import json
    try:
        parsed_accounts = json.loads(accounts_json)
        if isinstance(parsed_accounts, list):
            TUYA_ACCOUNTS = parsed_accounts
    except json.JSONDecodeError:
        pass

MQ_ENV_PROD = "event"
PULSAR_SERVER_EU = "pulsar+ssl://mqe.tuyaeu.com:7285/"

# Baza danych
DB_FILE = "/data/tuya_telemetry.db"

# Domyślne ID urządzenia (dla wstecznej kompatybilności)
HEAT_PUMP_DEV_ID = "bf874f7ae72aca1fc23op0"
MANUAL_METER_DEV_ID = "licznikRęczny"

# Kody parametrów będących temperaturami (wymagają podziału przez 10)
TEMP_CODES = {
    "in_water_temp", "out_water_temp", "tank_temp", 
    "amb_temp", "disc_temp", "back_temp", "tidr",
    "cool_temp_set", "heat_temp_set", "hot_water_temp_set",
    "heat_temp_set_z2", "cool_temp_set_z2",
    "auto_heat_temp_set_z1", "auto_heat_temp_set_z2", "auto_cool_temp_set_z2",
    "idr_temp_set",
}

# Konfiguracja histerezy dynamicznej
# Format: 'nazwa_parametru': { 'active': próg_gdy_pompa_pracuje, 'idle': próg_gdy_pompa_stoi, 'last_value': None }
# UWAGA: Wartości temperatur (TEMP_CODES) są dzielone przez 10 PRZED sprawdzeniem progu,
# więc progi dla temperatur są w °C (nie w surowych jednostkach x10).
# Np. active=0.2 oznacza zapis gdy zmiana >= 0.2°C.

HISTERESIS_CONFIG = {
    # Temperatury hydrauliczne (progi w °C)
    "out_water_temp": {"active": 0.2, "idle": 0.5, "last_value": None},
    "in_water_temp":  {"active": 0.2, "idle": 0.5, "last_value": None},
    "tank_temp":      {"active": 0.2, "idle": 0.5, "last_value": None},

    # Temperatury otoczenia i wewnętrzne (progi w °C)
    "amb_temp":       {"active": 0.5, "idle": 0.8, "last_value": None},
    "tidr":           {"active": 0.5, "idle": 0.5, "last_value": None},

    # Temperatury układu chłodniczego (progi w °C)
    "disc_temp":      {"active": 0.5, "idle": 1.5, "last_value": None},
    "back_temp":      {"active": 0.5, "idle": 1.5, "last_value": None},

    # Energia i zasilanie (surowe wartości — NIE dzielone przez 10)
    "ac_curr":        {"active": 2.0, "idle": 5.0, "last_value": None},
    "ac_vol":         {"active": 2.0, "idle": 3.0, "last_value": None},

    # Praca układu mechanicznego (surowe wartości)
    "comp_freq":      {"active": 2.0, "idle": 1.0, "last_value": None},
    "flow_rate":      {"active": 2.0, "idle": 1.0, "last_value": None},
    "dc_fan1":        {"active": 15.0, "idle": 50.0, "last_value": None},
    "dc_fan2":        {"active": 50.0, "idle": 50.0, "last_value": None},
    
    # Elektroniczne zawory rozprężne (EEV) (surowe wartości)
    "m_eev":          {"active": 5.0, "idle": 20.0, "last_value": None},
    "a_eev":          {"active": 5.0, "idle": 20.0, "last_value": None},
}

MAX_HEARTBEAT_SEC = 300  # Wymuś zapis co najmniej raz na 5 minut

# Konfiguracja lokalizacji dla danych pogodowych (Open-Meteo)
LATITUDE = float(os.environ.get("LATITUDE", 51.7592))  # Łódź
LONGITUDE = float(os.environ.get("LONGITUDE", 19.4560))  # Łódź
LOCATION_NAME = os.environ.get("LOCATION_NAME", "Łódź")

# Konfiguracja powiadomień Telegram (opcjonalne — brak = wyłączone)
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
TELEGRAM_ENABLED = bool(TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID)
DAILY_REPORT_HOUR = int(os.environ.get("DAILY_REPORT_HOUR", 21))  # godzina raportu dziennego (czas lokalny)
SERVER_TIMEZONE_OFFSET = int(os.environ.get("SERVER_TIMEZONE_OFFSET", 0))  # przesunięcie serwera vs czas lokalny (np. -2 gdy serwer UTC, użytkownik UTC+2)

# Metadane parametrów pompy — na podstawie oficjalnej specyfikacji modelu Tuya (model 0000043th5)
PARAM_INFO = {
    # Temperatury hydrauliczne
    "in_water_temp": {"label": "Powrót CO", "desc": "Temperatura wody powracającej z instalacji grzewczej"},
    "out_water_temp": {"label": "Zasilanie CO", "desc": "Temperatura wody wychodzącej na dom"},
    "tank_temp": {"label": "Woda CWU", "desc": "Temperatura wody w zasobniku ciepłej wody użytkowej"},
    "amb_temp": {"label": "Temp. zewnętrzna", "desc": "Temperatura powietrza na zewnątrz budynku"},

    # Temperatury układu chłodniczego
    "disc_temp": {"label": "Tłoczenie sprężarki", "desc": "Temperatura gazu na wylocie sprężarki"},
    "back_temp": {"label": "Powrót do sprężarki", "desc": "Temperatura czynnika na ssaniu sprężarki"},
    "tidr": {"label": "Temp. pokojowa", "desc": "Temperatura wewnętrzna pomieszczenia — czujnik pokojowy"},

    # Nastawy temperatur
    "heat_temp_set": {"label": "Nastawa CO Z1", "desc": "Zadana temperatura zasilania — tryb grzania, strefa 1"},
    "cool_temp_set": {"label": "Nastawa chłodzenia Z1", "desc": "Zadana temperatura — tryb chłodzenia, strefa 1"},
    "hot_water_temp_set": {"label": "Nastawa CWU", "desc": "Zadana temperatura wody użytkowej"},
    "auto_temp_set": {"label": "Nastawa auto", "desc": "Zadana temperatura — tryb automatyczny"},
    "heat_temp_set_z2": {"label": "Nastawa CO Z2", "desc": "Zadana temperatura zasilania — tryb grzania, strefa 2 / podłogówka"},
    "cool_temp_set_z2": {"label": "Nastawa chłodzenia Z2", "desc": "Zadana temperatura — tryb chłodzenia, strefa 2"},
    "auto_heat_temp_set_z1": {"label": "Auto CO Z1", "desc": "Zadana temp. grzania Z1 w trybie auto"},
    "auto_heat_temp_set_z2": {"label": "Auto CO Z2", "desc": "Zadana temp. grzania Z2 w trybie auto"},
    "auto_cool_temp_set_z2": {"label": "Auto chłodzenie Z2", "desc": "Zadana temp. chłodzenia Z2 w trybie auto"},
    "idr_temp_set": {"label": "Nastawa temp. pokojowej", "desc": "Zadana temperatura pomieszczenia"},

    # Parametry elektryczne i mechaniczne
    "ac_vol": {"label": "Napięcie AC", "desc": "Napięcie zasilania sieciowego, jednostka: V"},
    "ac_curr": {"label": "Prąd AC", "desc": "Natężenie prądu pobieranego, skala ×0.1 A"},
    "comp_freq": {"label": "Częstotliwość sprężarki", "desc": "Aktualna częstotliwość pracy sprężarki, max 120 Hz"},
    "flow_rate": {"label": "Przepływ", "desc": "Przepływ wody w obiegu hydraulicznym, skala ×0.1 m³/h"},
    "m_eev": {"label": "Zawór EEV główny", "desc": "Pozycja głównego elektronicznego zaworu rozprężnego, 0-480 kroków"},
    "a_eev": {"label": "Zawór EEV dodatkowy", "desc": "Pozycja dodatkowego elektronicznego zaworu rozprężnego, 0-480 kroków"},
    "dc_fan1": {"label": "Wentylator DC 1", "desc": "Obroty wentylatora DC jednostki zewnętrznej, 0-1000 RPM"},
    "dc_fan2": {"label": "Wentylator DC 2", "desc": "Obroty drugiego wentylatora DC, 0-1000 RPM"},
    "ac_fan": {"label": "Wentylator AC", "desc": "Status wentylatora AC: close / low_spd / high_spd"},

    # Flagi binarne i statusy
    "switch": {"label": "Włącznik", "desc": "Główny wyłącznik pompy"},
    "defrost": {"label": "Odszranianie", "desc": "Cykl automatycznego odszraniania parownika"},
    "freeze": {"label": "Ochrona antyzamrożeniowa", "desc": "Flaga aktywacji ochrony przed zamarzaniem"},
    "valve": {"label": "Zawór 3-drożny", "desc": "Stan zaworu 3-drożnego przełączającego CO/CWU"},
    "pump_sta": {"label": "Pompa obiegowa", "desc": "Status pompy obiegowej wody"},
    "protect_flag": {"label": "Flaga ochrony", "desc": "Aktywna ochrona urządzenia"},
    "fault_flag": {"label": "Flaga awarii", "desc": "Znacznik wystąpienia usterki"},
    "mute": {"label": "Tryb cichy", "desc": "Tryb Silent — ograniczona moc"},
    "holiday_sw": {"label": "Tryb urlopowy", "desc": "Funkcja Holiday — obniżona temperatura"},

    # Tryb pracy i strefy
    "work_mode": {"label": "Tryb pracy", "desc": "Tryb pracy pompy: cool, heat, auto, hot_water, cool_hot_water, heat_hot_water, auto_dhw"},
    "zone_select": {"label": "Aktywna strefa", "desc": "Która strefa żąda grzania: 0=brak, 1=Z1, 2=Z2, 3=obie"},
    "mode_valid": {"label": "Aktywny tryb", "desc": "Bitmaska aktywnych trybów pracy 0-7"},
    "auto_run_tar_mode": {"label": "Cel trybu auto", "desc": "Status read-only: co pompa faktycznie robi w trybie auto — 0=chłodzenie, 1=ogrzewanie"},

    # Konfiguracja termostatów i stref
    "twc_type": {"label": "Typ termostatu", "desc": "Typ termostatu: 0-3"},
    "no_twc_doble_zone": {"label": "Podział stref bez termostatu", "desc": "Czy dzielić na strefy bez termostatu: 0=nie, 1=tak"},
    "no_twc_szone_run_type": {"label": "Praca 1-strefowa bez termostatu", "desc": "Tryb pracy jednej strefy bez termostatu 0-3"},
    "no_twc_dzone_run_type": {"label": "Praca 2-strefowa bez termostatu", "desc": "Tryb pracy dwóch stref bez termostatu 0-7"},
    "twc_szone_run_type": {"label": "Praca 1-strefowa z termostatem", "desc": "Tryb pracy jednej strefy z termostatem 0-1"},
    "twc_dzone_run_type": {"label": "Praca 2-strefowa z termostatem", "desc": "Tryb pracy dwóch stref z termostatem 0-3"},

    # Fault — bitmapa kodów błędów E01-E16, P01-P14
    "fault": {"label": "Kody błędów", "desc": "Bitmapa błędów: E01-E16 (bit 0-15), P01-P14 (bit 16-29). 0 = brak błędów"},
}

# Mapowanie bitów fault na kody błędów (z oficjalnej specyfikacji)
FAULT_BITMAP_LABELS = [
    "E01", "E02", "E03", "E04", "E05", "E06", "E07", "E08",
    "E09", "E10", "E11", "E12", "E13", "E14", "E15", "E16",
    "P01", "P02", "P03", "P04", "P05", "P06", "P07", "P08",
    "P09", "P10", "P11", "P12", "P13", "P14",
]


def get_param_label(code: str) -> str:
    """Zwraca etykietę parametru z kodem w nawiasie."""
    info = PARAM_INFO.get(code)
    return f"{info['label']} ({code})" if info else code
