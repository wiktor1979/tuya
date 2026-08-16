import sqlite3
import time
import pandas as pd

DB_FILE = "/data/tuya_telemetry.db"

# ID urządzeń Tuya
HEAT_PUMP_DEV_ID = "bf874f7ae72aca1fc23op0"
METER_DEV_ID = "licznik123"  # Podmień na rzeczywiste ID licznika

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
    
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_code_time ON telemetry (code, timestamp)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_dev_time ON telemetry (device_id, timestamp)')
    
    conn.commit()
    conn.close()


def save_properties_to_db(dev_id: str, properties: list, event_time: int = None) -> bool:
    """Zapisuje dynamiczną listę parametrów z ramki Tuya do bazy SQLite."""
    if dev_id not in (HEAT_PUMP_DEV_ID, METER_DEV_ID):
        return False

    if not event_time:
        event_time = int(time.time())

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    is_running = False
    if dev_id == HEAT_PUMP_DEV_ID:
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
            is_running = (row and row[0] is not None and row[0] > 0)
        else:
            is_running = (comp_freq_val > 0)

    records_to_insert = []
    for item in properties:
        code = item.get("code")
        raw_val = item.get("value")

        if code is None or raw_val is None:
            continue

        # Ignorujemy skoki ac_vol dla pompy w trakcie postoju sprężarki
        if dev_id == HEAT_PUMP_DEV_ID and code == "ac_vol" and not is_running:
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


# --- FUNKCJE DLA DASHBOARDU ---

def get_latest_status(device_id: str) -> dict:
    """Pobiera najnowszy stan parametrów dla danego urządzenia."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT code, val_num, val_str 
        FROM telemetry t1
        WHERE device_id = ? AND timestamp = (
            SELECT MAX(timestamp) FROM telemetry t2 
            WHERE t2.device_id = t1.device_id AND t2.code = t1.code
        )
    ''', (device_id,))
    rows = cursor.fetchall()
    conn.close()
    
    return {code: (val_num if val_num is not None else val_str) for code, val_num, val_str in rows}


def get_pivoted_telemetry(device_id: str, start_time: int, end_time: int) -> pd.DataFrame:
    """Pobiera dane i przekształca je do postaci tabeli czasowej (kluczowe dla Plotly)."""
    conn = sqlite3.connect(DB_FILE)
    query = '''
        SELECT timestamp, code, val_num 
        FROM telemetry 
        WHERE device_id = ? AND timestamp BETWEEN ? AND ? AND val_num IS NOT NULL
        ORDER BY timestamp ASC
    '''
    df = pd.read_sql_query(query, conn, params=(device_id, start_time, end_time))
    conn.close()

    if df.empty:
        return pd.DataFrame()

    df['datetime'] = pd.to_datetime(df['timestamp'], unit='s')
    pivot_df = df.pivot_table(index='datetime', columns='code', values='val_num', aggfunc='last')
    return pivot_df
