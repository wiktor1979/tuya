import sqlite3
import time

DB_FILE = "/data/tuya_telemetry.db"
HEAT_PUMP_DEV_ID = "bf874f7ae72aca1fc23op0"

TEMP_CODES = {
    "in_water_temp", "out_water_temp", "tank_temp", 
    "amb_temp", "disc_temp", "back_temp", "tidr",
    "cool_temp_set", "heat_temp_set", "hot_water_temp_set"
}

def init_db():
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
    
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_code_time ON telemetry (code, timestamp)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_dev_time ON telemetry (device_id, timestamp)')
    
    conn.commit()
    conn.close()


def save_manual_reading(device_id: str, code: str, val_num: float, timestamp: int = None) -> bool:
    """Zapisuje ręczny odczyt z formularza bezpośrednio do tabeli telemetry."""
    if timestamp is None:
        timestamp = int(time.time())

    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO telemetry (timestamp, device_id, code, val_num, val_str)
            VALUES (?, ?, ?, ?, NULL)
        ''', (timestamp, device_id, code, float(val_num)))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"Błąd zapisu odczytu ręcznego: {e}")
        return False


def save_properties_to_db(dev_id: str, properties: list, event_time: int = None) -> bool:
    if dev_id != HEAT_PUMP_DEV_ID:
        return False

    if not event_time:
        event_time = int(time.time())

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    comp_freq_val = None
    for item in properties:
        if item.get("code") == "comp_freq":
            comp_freq_val = item.get("value")
            break

    if comp_freq_val is None:
        cursor.execute('''
            SELECT val_num FROM telemetry 
            WHERE device_id = ? AND code = 'comp_freq' 
            ORDER BY timestamp DESC LIMIT 1
        ''', (dev_id,))
        row = cursor.fetchone()
        comp_freq_val = row[0] if (row and row[0] is not None) else 0

    is_running = (comp_freq_val is not None and comp_freq_val > 0)
    records_to_insert = []

    for item in properties:
        code = item.get("code")
        raw_val = item.get("value")

        if code is None or raw_val is None:
            continue

        if code == "ac_vol" and not is_running:
            continue

        val_num = None
        val_str = None

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
        return True

    conn.close()
    return False
