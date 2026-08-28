"""Powiadomienia Telegram — alerty krytyczne i raport dzienny."""
import time
import threading
import requests
from typing import List, Dict, Optional
from datetime import datetime, timedelta

from app.config import (
    TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, TELEGRAM_ENABLED,
    HEAT_PUMP_DEV_ID, DB_FILE,
)
from app.services.analytics import decode_fault_bitmap


# --- Throttle: zapobiega spamowaniu identycznymi alertami ---
_last_alert_time: Dict[str, float] = {}
ALERT_COOLDOWN_SEC = 600  # min 10 minut między identycznymi alertami


def send_telegram(message: str, parse_mode: str = "Markdown") -> bool:
    """
    Wysyła wiadomość na Telegram przez Bot API.
    
    Returns:
        True jeśli wysłano pomyślnie, False w razie błędu.
    """
    if not TELEGRAM_ENABLED:
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": parse_mode,
    }

    try:
        resp = requests.post(url, json=payload, timeout=10)
        if resp.status_code == 200:
            return True
        else:
            print(f"[Telegram] Błąd HTTP {resp.status_code}: {resp.text[:200]}", flush=True)
            return False
    except requests.exceptions.RequestException as e:
        print(f"[Telegram] Błąd połączenia: {e}", flush=True)
        return False


def _should_send_alert(alert_key: str) -> bool:
    """Sprawdza czy alert nie jest throttlowany (cooldown 10 min)."""
    now = time.time()
    last = _last_alert_time.get(alert_key, 0)
    if now - last < ALERT_COOLDOWN_SEC:
        return False
    _last_alert_time[alert_key] = now
    return True


# --- Alerty krytyczne (natychmiast) ---

def send_fault_alert(device_id: str, fault_codes: List[str], fault_bitmap: int) -> bool:
    """Wysyła natychmiastowy alert o awarii pompy."""
    alert_key = f"fault:{device_id}:{fault_bitmap}"
    if not _should_send_alert(alert_key):
        return False

    codes_str = ", ".join(fault_codes)
    msg = (
        f"🚨 *AWARIA POMPY CIEPŁA*\n"
        f"Urządzenie: `{device_id}`\n"
        f"Kody błędów: *{codes_str}*\n"
        f"Bitmapa: {fault_bitmap}\n"
        f"Czas: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    )
    sent = send_telegram(msg)
    if sent:
        print(f"[Telegram] Wyslano alert awarii: {codes_str} ({device_id})", flush=True)
    return sent


def send_fault_resolved(device_id: str, resolved_codes: List[str]) -> bool:
    """Wysyła informację o rozwiązaniu awarii."""
    alert_key = f"resolved:{device_id}:{','.join(resolved_codes)}"
    if not _should_send_alert(alert_key):
        return False

    codes_str = ", ".join(resolved_codes)
    msg = (
        f"✅ *Awaria rozwiązana*\n"
        f"Urządzenie: `{device_id}`\n"
        f"Rozwiązane kody: *{codes_str}*\n"
        f"Czas: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    )
    sent = send_telegram(msg)
    if sent:
        print(f"[Telegram] Wyslano info o rozwiazaniu: {codes_str} ({device_id})", flush=True)
    return sent


def send_communication_lost(device_id: str, minutes_silent: int) -> bool:
    """Wysyła alert o utracie komunikacji z pompą."""
    alert_key = f"comm_lost:{device_id}"
    if not _should_send_alert(alert_key):
        return False

    msg = (
        f"📡 *Utrata komunikacji*\n"
        f"Urządzenie: `{device_id}`\n"
        f"Brak danych od: *{minutes_silent} min*\n"
        f"Czas: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    )
    sent = send_telegram(msg)
    if sent:
        print(f"[Telegram] Wyslano alert utraty komunikacji: {minutes_silent} min ({device_id})", flush=True)
    return sent


# --- Raport dzienny (ważne + informacyjne) ---

def build_daily_report(device_id: str) -> Optional[str]:
    """
    Buduje raport dzienny na podstawie danych z bazy.
    Używa tych samych funkcji co dashboard (process_telemetry, compute_daily_stats).
    
    Returns:
        Tekst raportu Markdown lub None jeśli brak danych.
    """
    from app.services.database import db_cursor, get_fault_history, get_setting
    from app.services.data_loader import process_telemetry, compute_daily_stats
    from app.config import SERVER_TIMEZONE_OFFSET
    import pandas as pd
    import sqlite3

    # Kalibracja — te same wartości co sidebar (persystowane w settings)
    cos_phi = float(get_setting("cos_phi", "1.00"))
    standby_power_w = int(get_setting("standby_power_w", "15"))
    active_power_w = int(get_setting("active_power_w", "130"))

    today = datetime.now().date()
    yesterday = today - timedelta(days=1)
    
    # Zakres: od 00:00 wczoraj do 00:00 dziś (czas lokalny użytkownika)
    offset_sec = -SERVER_TIMEZONE_OFFSET * 3600
    ts_start = int(datetime(yesterday.year, yesterday.month, yesterday.day).timestamp()) + offset_sec
    ts_end = int(datetime(today.year, today.month, today.day).timestamp()) + offset_sec

    # Załaduj dane z bazy
    conn = sqlite3.connect(DB_FILE)
    df_raw = pd.read_sql_query(
        "SELECT datetime(timestamp, 'unixepoch', 'localtime') as czas, code, val_num, val_str "
        "FROM telemetry WHERE device_id = ? AND timestamp >= ? AND timestamp < ? ORDER BY timestamp ASC",
        conn, params=(device_id, ts_start, ts_end)
    )
    conn.close()

    if df_raw.empty:
        return None

    # Przetwórz identycznie jak dashboard
    df_pivot = process_telemetry(df_raw, -SERVER_TIMEZONE_OFFSET, cos_phi, standby_power_w, active_power_w, "5min")
    if df_pivot is None or df_pivot.empty:
        return None

    daily = compute_daily_stats(df_pivot, -SERVER_TIMEZONE_OFFSET)
    if daily.empty:
        return None

    # Weź dane za wczoraj (powinien być 1 wiersz)
    row = daily.iloc[0]
    scop = row.get("SCOP_realny")
    e_el = row.get("E_el_total", 0)
    comp_starts = int(row.get("comp_start", 0))
    hours_work = row.get("dt_hours_work", 0)
    defrost_count = int(row.get("defrost_start", 0))

    # Awarie z fault_log za wczoraj
    with db_cursor() as cursor:
        pass  # potrzebne aby otworzyć kontekst
    fault_history = get_fault_history(device_id, limit=100)
    faults_yesterday = []
    for _, ts, code, bitmap, resolved, resolved_at in fault_history:
        if ts_start <= ts < ts_end:
            status = "rozwiazana" if resolved else "AKTYWNA"
            faults_yesterday.append(f"{code} ({status})")

    # --- Budowanie raportu ---
    local_yesterday = (datetime.now() + timedelta(hours=-SERVER_TIMEZONE_OFFSET) - timedelta(days=1)).date()
    date_str = local_yesterday.strftime("%Y-%m-%d")
    lines = [f"📊 *Raport dzienny — {date_str}*", f"Urządzenie: `{device_id}`", ""]

    # SCOP dzienny
    if scop is not None and scop > 0.5:
        scop_icon = "✅" if scop >= 3.1 else "⚠️"
        lines.append(f"{scop_icon} SCOP dzienny: *{scop:.2f}*")
    else:
        lines.append("SCOP dzienny: _brak danych_")

    # Zużycie energii
    if e_el > 0:
        lines.append(f"⚡ Zużycie energii: *{e_el:.2f} kWh*")
    else:
        lines.append("⚡ Zużycie energii: _brak danych_")

    # Czas pracy sprężarki
    lines.append(f"⏱ Czas pracy: *{hours_work:.1f} h*")

    # Starty sprężarki
    takt_icon = "⚠️" if comp_starts > 12 else ""
    lines.append(f"🔄 Starty: *{comp_starts}* {takt_icon}")

    # Defrosty
    lines.append(f"❄️ Defrosty: *{defrost_count}*")

    # Awarie
    if faults_yesterday:
        lines.append("")
        for fault_str in faults_yesterday:
            lines.append(f"🚨 {fault_str}")
    else:
        lines.append("✅ Brak awarii")

    return "\n".join(lines)


def send_daily_report(device_id: str) -> bool:
    """Generuje i wysyła raport dzienny dla urządzenia."""
    report = build_daily_report(device_id)
    if report is None:
        print(f"[Telegram] Brak danych do raportu dziennego ({device_id})", flush=True)
        return False

    sent = send_telegram(report)
    if sent:
        print(f"[Telegram] Wyslano raport dzienny ({device_id})", flush=True)
    return sent
