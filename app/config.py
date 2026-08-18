"""Konfiguracja aplikacji - zmienne środowiskowe i stałe."""
import os
from dotenv import load_dotenv
from typing import List, Dict, Optional

load_dotenv()

# Konfiguracja Tuya Pulsar (EU) - obsługa wielu kont
# Format: lista słowników z kluczami: access_id, access_key, devices (lista ID urządzeń)
TUYA_ACCOUNTS: List[Dict[str, any]] = []

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
    "cool_temp_set", "heat_temp_set", "hot_water_temp_set"
}

# Progi zmian dla poszczególnych parametrów (Deadband)
THRESHOLDS = {
    "out_water_temp": 0.2,
    "in_water_temp": 0.2,
    "tank_temp": 0.3,
    "amb_temp": 0.5,
    "ac_curr": 0.1,
    "ac_vol": 3.0,
    "comp_freq": 1.0,
    "flow_rate": 1.0,
    "disc_temp": 0.5,
    "back_temp": 0.5
}

MAX_HEARTBEAT_SEC = 300  # Wymuś zapis co najmniej raz na 5 minut

# Metadane parametrów pompy
PARAM_INFO = {
    "in_water_temp": {"label": "Powrót CO", "desc": "Temperatura wody powracającej z instalacji grzewczej"},
    "out_water_temp": {"label": "Zasilanie CO", "desc": "Temperatura wody wychodzącej na dom"},
    "tank_temp": {"label": "Woda CWU", "desc": "Temperatura wody w zasobniku ciepłej wody użytkowej"},
    "amb_temp": {"label": "Temp. zewnętrzna", "desc": "Temperatura powietrza na zewnątrz budynku"},
    "disc_temp": {"label": "Tłoczenie sprężarki", "desc": "Temperatura gazy na wylocie/tłoczeniu sprężarki (Discharge)"},
    "back_temp": {"label": "Powrót do sprężarki", "desc": "Temperatura czynnika na powrocie do sprężarki (Suction)"},
    "tidr": {"label": "Temp. ssania", "desc": "Temperatura czujnika ssania / wymiennika chłodniczego"},
    "heat_temp_set": {"label": "Nastawa CO", "desc": "Docelowa zadana temperatura dla trybu ogrzewania CO"},
    "cool_temp_set": {"label": "Nastawa Chłodzenia", "desc": "Docelowa zadana temperatura dla trybu chłodzenia"},
    "hot_water_temp_set": {"label": "Nastawa CWU", "desc": "Docelowa zadana temperatura dla wody użytkowej"},
    "ac_vol": {"label": "Napięcie AC", "desc": "Napięcie zasilania sieciowego AC podawane do jednostki"},
    "ac_curr": {"label": "Prąd AC", "desc": "Natężenie prądu pobieranego przez urządzenie"},
    "comp_freq": {"label": "Częstotliwość sprężarki", "desc": "Aktualna częstotliwość pracy sprężarki (Hz)"},
    "flow_rate": {"label": "Przepływ", "desc": "Przepływ wody w obiegu hydraulicznym"},
    "m_eev": {"label": "Zawór EEV główny", "desc": "Pozycja otwarcia głównego elektronicznego zaworu rozprężnego"},
    "valve": {"label": "Zawór 3-drożny", "desc": "Stan zaworu przełączającego (0 = CO, 1 = CWU)"},
    "defrost": {"label": "Odszranianie", "desc": "Cykl automatycznego odszraniania parownika"}
}
