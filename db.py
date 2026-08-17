import sqlite3
import time
from typing import Optional, List, Dict, Any

DB_FILE = "/data/tuya_telemetry.db"

# TUTAJ WPROWADŹ ID SWOJEJ POMPY CIEPŁA
HEAT_PUMP_DEV_ID = "bf874f7ae72aca1fc23op0"
MANUAL_METER_DEV_ID = "licznikRęczny"

# Kody parametrów będących temperaturami (wymagają podziału przez 10)
TEMP_CODES = {
    "in_water_temp",
    "out_water_temp",
    "tank_temp",
    "amb_temp",
    "disc_temp",
    "back_temp",
    "tidr",
    "cool_temp_set",
    "heat_temp_set",
    "hot_water_temp_set",
}


def init_db():
    """Tworzy tabelę telemetry oraz indeksy wyszukiwania."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS telemetry (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp INTEGER NOT NULL,
            device_id TEXT NOT NULL,
            code TEXT NOT NULL,
            val_num REAL,
            val_str TEXT
        )
        """
    )

    # Indeksy przyspieszające zapytania
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_code_time ON telemetry (code, timestamp)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_dev_time ON telemetry (device_id, timestamp)"
    )

    conn.commit()
    conn.close()


def save_manual_energy_reading(reading_val: float, timestamp_sec: int) -> bool:
    """
    Zapisuje ręczny odczyt z fizycznego licznika energii.
    Zabezpiecza przed zapisem duplikatów o tym samym czasie lub identycznej wartości pod rząd.
    """
    if reading_val is None or reading_val < 0:
        return False

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    # Sprawdzenie 1: czy dla tego dokładnego timestampu nie ma już wpisu
    cursor.execute(
        """
        SELECT id
        FROM telemetry
        WHERE device_id = ?
          AND timestamp = ?
          AND trim(code) = 'energy_kwh'
        """,
        (MANUAL_METER_DEV_ID, timestamp_sec),
    )

    if cursor.fetchone():
        conn.close()
        return False

    # Sprawdzenie 2: czy ostatnio wpisana wartość nie jest identyczna
    cursor.execute(
        """
        SELECT val_num
        FROM telemetry
        WHERE device_id = ?
          AND trim(code) = 'energy_kwh'
        ORDER BY timestamp DESC
        LIMIT 1
        """,
        (MANUAL_METER_DEV_ID,),
    )

    last_row = cursor.fetchone()
    if last_row and last_row[0] is not None and abs(last_row[0] - reading_val) < 0.0001:
        conn.close()
        return False

    cursor.execute(
        """
        INSERT INTO telemetry (timestamp, device_id, code, val_num, val_str)
        VALUES (?, ?, 'energy_kwh', ?, NULL)
        """,
        (timestamp_sec, MANUAL_METER_DEV_ID, float(reading_val)),
    )

    conn.commit()
    conn.close()
    return True


def save_properties_to_db(dev_id: str, properties: list, event_time: int = None) -> bool:
    """Zapisuje dynamiczną listę parametrów z ramki Tuya do bazy SQLite."""
    dev_id = str(dev_id).strip()

    if dev_id != HEAT_PUMP_DEV_ID:
        return False

    if not event_time:
        event_time = int(time.time())

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    # Sprawdź aktualny stan sprężarki, aby decydować o zapisie ac_vol
    comp_freq_val = None

    for item in properties:
        if not isinstance(item, dict):
            continue

        code = str(item.get("code", "")).strip()
        if code == "comp_freq":
            comp_freq_val = item.get("value")
            break

    if comp_freq_val is None:
        cursor.execute(
            """
            SELECT val_num
            FROM telemetry
            WHERE device_id = ?
              AND trim(code) = 'comp_freq'
            ORDER BY timestamp DESC
            LIMIT 1
            """,
            (dev_id,),
        )
        row = cursor.fetchone()

        if row and row[0] is not None:
            comp_freq_val = row[0]
        else:
            comp_freq_val = 0

    try:
        comp_freq_float = float(comp_freq_val)
    except Exception:
        comp_freq_float = 0.0

    is_running = comp_freq_float > 0.0

    records_to_insert = []

    for item in properties:
        if not isinstance(item, dict):
            continue

        code = str(item.get("code", "")).strip()
        raw_val = item.get("value")

        if not code or raw_val is None:
            continue

        # Nie zapisuj napięcia, gdy sprężarka nie pracuje
        # Zmniejsza to liczbę rekordów, a standby można później modelować mocą stałą
        if code == "ac_vol" and not is_running:
            continue

        val_num = None
        val_str = None

        if code in TEMP_CODES and isinstance(raw_val, (int, float)) and not isinstance(raw_val, bool):
            val_num = round(raw_val / 10.0, 1)
        elif isinstance(raw_val, (int, float)) and not isinstance(raw_val, bool):
            val_num = float(raw_val)
        else:
            val_str = str(raw_val)

        records_to_insert.append(
            (
                event_time,
                dev_id,
                code,
                val_num,
                val_str,
            )
        )

    if records_to_insert:
        cursor.executemany(
            """
            INSERT INTO telemetry (timestamp, device_id, code, val_num, val_str)
            VALUES (?, ?, ?, ?, ?)
            """,
            records_to_insert,
        )
        conn.commit()
        conn.close()
        return True

    conn.close()
    return False
