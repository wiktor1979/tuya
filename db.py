import sqlite3
import time

DB_FILE = "tuya_telemetry.db"

# TUTAJ WPROWADŹ ID SWOJEJ POMPY CIEPŁA
HEAT_PUMP_DEV_ID = "bf874f7ae72aca1fc23op0"

# Kody parametrów będących temperaturami (wymagają podziału przez 10)
TEMP_CODES = {
    "in_water_temp", "out_water_temp", "tank_temp", 
    "amb_temp", "disc_temp", "back_temp", "tidr",
    "cool_temp_set", "heat_temp_set", "hot_water_temp_set"
}

def init_db():
    """Tworzy tabelę telemetry oraz indeksy wyszukiwania."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS telemetry (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp INTEGER NOT NULL,
            device_id TEXT NOT NULL,
            code TEXT NOT NULL,
            val_num REAL,
            val_str TEXT
        )
    ''')
    
    # Indeksy drastycznie przyspieszają zapytania do wykresów
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_code_time ON telemetry (code, timestamp)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_dev_time ON telemetry (device_id, timestamp)')
    
    conn.commit()
    conn.close()


def save_properties_to_db(dev_id: str, properties: list, event_time: int = None) -> bool:
    """Zapisuje dynamiczną listę parametrów z ramki Tuya do bazy SQLite. 
       Zwraca True, jeśli zapisano dane, w przeciwnym razie False."""
    
    # --- FILTR 1: Jeśli to nie nasza pompa, przerywamy i zwracamy False ---
    if dev_id != HEAT_PUMP_DEV_ID:
        return False

    if not event_time:
        event_time = int(time.time())

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    # Sprawdzamy w bieżącej paczce lub bazie, czy sprężarka faktycznie pracuje (comp_freq > 0)
    comp_freq_val = None
    for item in properties:
        if item.get("code") == "comp_freq":
            comp_freq_val = item.get("value")
            break

    # Jeśli w tej konkretnej ramce nie ma comp_freq, sprawdzamy ostatni znany stan w bazie
    if comp_freq_val is None:
        cursor.execute('''
            SELECT val_num FROM telemetry 
            WHERE device_id = ? AND code = 'comp_freq' 
            ORDER BY timestamp DESC LIMIT 1
        ''', (dev_id,))
        row = cursor.fetchone()
        if row and row[0] is not None:
            comp_freq_val = row[0]
        else:
            comp_freq_val = 0

    is_running = (comp_freq_val is not None and comp_freq_val > 0)

    records_to_insert = []

    for item in properties:
        code = item.get("code")
        raw_val = item.get("value")

        if code is None or raw_val is None:
            continue

        # --- FILTR 2: Jeśli pompa nie pracuje, ignorujemy ciągłe skoki napięcia sieciowego ---
        if code == "ac_vol" and not is_running:
            continue

        val_num = None
        val_str = None

        # Konwersja i kategoryzacja wartości (liczba vs tekst/boolean)
        if code in TEMP_CODES and isinstance(raw_val, (int, float)):
            val_num = round(raw_val / 10.0, 1)
        elif isinstance(raw_val, (int, float)) and not isinstance(raw_val, bool):
            val_num = float(raw_val)
        else:
            val_str = str(raw_val)

        records_to_insert.append((event_time, dev_id, code, val_num, val_str))

    if records_to_insert:
        cursor.executemany('''
            INSERT INTO telemetry (timestamp, device_id, code, val_num, val_str)
            VALUES (?, ?, ?, ?, ?)
        ''', records_to_insert)
        conn.commit()
        conn.close()
        return True  # Sukces - dane zostały zapisane

    conn.close()
    return False