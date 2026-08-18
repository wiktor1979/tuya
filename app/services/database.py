"""Warstwa dostępu do bazy danych."""
import sqlite3
from typing import Optional, List, Tuple
from app.config import DB_FILE, HEAT_PUMP_DEV_ID, MANUAL_METER_DEV_ID, TEMP_CODES


def init_db() -> None:
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


def save_manual_energy_reading(reading_val: float, timestamp_sec: int) -> Tuple[bool, str]:
    """
    Zapisuje ręczny odczyt z fizycznego licznika energii.
    Zabezpiecza przed wysłaniem pustych danych, ujemnych oraz duplikatów.
    """
    if reading_val is None or reading_val <= 0:
        return False, "Wartość licznika musi być większa od zera."

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    # Zabezpieczenie 1: Dokładnie ten sam znacznik czasu
    cursor.execute('''
        SELECT id FROM telemetry
        WHERE device_id = ? AND timestamp = ? AND code = 'energy_kwh'
    ''', (MANUAL_METER_DEV_ID, timestamp_sec))
    if cursor.fetchone():
        conn.close()
        return False, "Wpis z wybraną datą i godziną już istnieje."

    # Zabezpieczenie 2: Identyczny stan licznika dla sąsiadującego wpisu
    cursor.execute('''
        SELECT val_num FROM telemetry
        WHERE device_id = ? AND code = 'energy_kwh'
        ORDER BY ABS(timestamp - ?) ASC LIMIT 1
    ''', (MANUAL_METER_DEV_ID, timestamp_sec))
    closest = cursor.fetchone()
    if closest and closest[0] is not None and abs(closest[0] - reading_val) < 0.0001:
        conn.close()
        return False, "Taka wartość licznika została już wcześniej zarejestrowana."

    cursor.execute('''
        INSERT INTO telemetry (timestamp, device_id, code, val_num, val_str)
        VALUES (?, ?, 'energy_kwh', ?, NULL)
    ''', (timestamp_sec, MANUAL_METER_DEV_ID, float(reading_val)))

    conn.commit()
    conn.close()
    return True, "Odczyt został pomyślnie zapisany."


def update_manual_energy_reading(rec_id: int, new_val: float, timestamp_sec: int) -> Tuple[bool, str]:
    """Aktualizuje istniejący wpis ręczny wyłącznie dla device_id = MANUAL_METER_DEV_ID."""
    if new_val is None or new_val <= 0:
        return False, "Wartość licznika musi być większa od zera."

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    cursor.execute('''
        UPDATE telemetry
        SET timestamp = ?, val_num = ?
        WHERE id = ? AND device_id = ? AND code = 'energy_kwh'
    ''', (timestamp_sec, float(new_val), rec_id, MANUAL_METER_DEV_ID))
    
    updated = cursor.rowcount > 0
    conn.commit()
    conn.close()
    
    if updated:
        return True, "Wpis został zaktualizowany."
    return False, "Nie znaleziono wskazanego wpisu do edycji."


def delete_manual_energy_reading(rec_id: int) -> bool:
    """Usuwa wpis ręczny z bazy danych."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        DELETE FROM telemetry 
        WHERE id = ? AND device_id = ? AND code = 'energy_kwh'
    ''', (rec_id, MANUAL_METER_DEV_ID))
    deleted = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return deleted


def save_properties_to_db(dev_id: str, properties: list, event_time: Optional[int] = None) -> bool:
    """Zapisuje dynamiczną listę parametrów z ramki Tuya do bazy SQLite."""
    # Akceptuj wszystkie urządzenia - nie filtruj po sztywnym ID
    # Dzięki temu można obsługiwać wiele pomp z różnych kont Tuya

    if not event_time:
        import time
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
