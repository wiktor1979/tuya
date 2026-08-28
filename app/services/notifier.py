"""Powiadomienia Telegram — alerty krytyczne i raport dzienny."""
import time
import threading
import requests
from typing import List, Dict, Optional
from datetime import datetime, timedelta

from app.config import (
    TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, TELEGRAM_ENABLED,
    HEAT_PUMP_DEV_ID,
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
        print(f"[Telegram] Wysłano alert awarii: {codes_str} ({device_id})", flush=True)
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
        print(f"[Telegram] Wysłano info o rozwiązaniu: {codes_str} ({device_id})", flush=True)
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
        print(f"[Telegram] Wysłano alert utraty komunikacji: {minutes_silent} min ({device_id})", flush=True)
    return sent


# --- Raport dzienny (ważne + informacyjne) ---

def build_daily_report(device_id: str) -> Optional[str]:
    """
    Buduje raport dzienny na podstawie danych z bazy.
    Zawiera: SCOP, zużycie energii, taktowanie, disc_temp, awarie, podsumowanie.
    
    Returns:
        Tekst raportu Markdown lub None jeśli brak danych.
    """
    # Import tu aby uniknąć circular import
    from app.services.database import db_cursor, get_fault_history
    from app.config import SERVER_TIMEZONE_OFFSET

    today = datetime.now().date()
    yesterday = today - timedelta(days=1)
    
    # Zakres: od 00:00 wczoraj do 00:00 dziś (czas lokalny użytkownika)
    # Serwer jest przesunięty o SERVER_TIMEZONE_OFFSET, więc kompensujemy
    offset_sec = -SERVER_TIMEZONE_OFFSET * 3600  # jeśli offset=-2, dodajemy +2h do UTC
    ts_start = int(datetime(yesterday.year, yesterday.month, yesterday.day).timestamp()) + offset_sec
    ts_end = int(datetime(today.year, today.month, today.day).timestamp()) + offset_sec

    with db_cursor() as cursor:
        # 1. Zużycie energii (przybliżone z ac_vol * ac_curr)
        cursor.execute('''
            SELECT 
                COUNT(*) as samples,
                AVG(val_num) as avg_comp_freq
            FROM telemetry
            WHERE device_id = ? AND code = 'comp_freq' 
                AND timestamp >= ? AND timestamp < ?
        ''', (device_id, ts_start, ts_end))
        comp_row = cursor.fetchone()
        total_samples = comp_row[0] if comp_row else 0

        if total_samples == 0:
            return None  # Brak danych za wczoraj

        avg_comp = comp_row[1] or 0

        # 2. Starty sprężarki (taktowanie)
        cursor.execute('''
            SELECT timestamp, val_num FROM telemetry
            WHERE device_id = ? AND code = 'comp_freq'
                AND timestamp >= ? AND timestamp < ?
            ORDER BY timestamp ASC
        ''', (device_id, ts_start, ts_end))
        freq_rows = cursor.fetchall()
        
        comp_starts = 0
        hours_work = 0.0
        prev_on = False
        prev_ts = None
        for ts, val in freq_rows:
            is_on = val is not None and val > 5
            if is_on and not prev_on:
                comp_starts += 1
            if is_on and prev_ts:
                hours_work += (ts - prev_ts) / 3600.0
            prev_on = is_on
            prev_ts = ts

        # 3. Max disc_temp
        cursor.execute('''
            SELECT MAX(val_num) FROM telemetry
            WHERE device_id = ? AND code = 'disc_temp'
                AND timestamp >= ? AND timestamp < ?
        ''', (device_id, ts_start, ts_end))
        max_disc_row = cursor.fetchone()
        max_disc = max_disc_row[0] if max_disc_row and max_disc_row[0] else None

        # 4. Średnia temp. zewnętrzna
        cursor.execute('''
            SELECT AVG(val_num) FROM telemetry
            WHERE device_id = ? AND code = 'amb_temp'
                AND timestamp >= ? AND timestamp < ?
        ''', (device_id, ts_start, ts_end))
        avg_amb_row = cursor.fetchone()
        avg_amb = avg_amb_row[0] if avg_amb_row and avg_amb_row[0] else None

        # 5. Przybliżone zużycie energii el.
        cursor.execute('''
            SELECT AVG(t1.val_num * t2.val_num) 
            FROM telemetry t1
            JOIN telemetry t2 ON t1.device_id = t2.device_id 
                AND t1.timestamp = t2.timestamp
            WHERE t1.device_id = ? AND t1.code = 'ac_vol' AND t2.code = 'ac_curr'
                AND t1.timestamp >= ? AND t1.timestamp < ?
        ''', (device_id, ts_start, ts_end))
        avg_power_row = cursor.fetchone()
        avg_power_va = avg_power_row[0] if avg_power_row and avg_power_row[0] else None
        
        # 6. Defrosty
        cursor.execute('''
            SELECT COUNT(*) FROM (
                SELECT timestamp, val_str,
                    LAG(val_str) OVER (ORDER BY timestamp) as prev_val
                FROM telemetry
                WHERE device_id = ? AND code = 'defrost'
                    AND timestamp >= ? AND timestamp < ?
            ) WHERE val_str = 'True' AND (prev_val = 'False' OR prev_val IS NULL)
        ''', (device_id, ts_start, ts_end))
        defrost_row = cursor.fetchone()
        defrost_count = defrost_row[0] if defrost_row else 0

    # 7. Awarie z fault_log za wczoraj
    fault_history = get_fault_history(device_id, limit=100)
    faults_yesterday = []
    for _, ts, code, bitmap, resolved, resolved_at in fault_history:
        if ts_start <= ts < ts_end:
            status = "rozwiązana" if resolved else "AKTYWNA"
            faults_yesterday.append(f"{code} ({status})")

    # --- Budowanie raportu ---
    # Data lokalna użytkownika (wczoraj wg jego strefy czasowej)
    local_yesterday = (datetime.now() + timedelta(hours=-SERVER_TIMEZONE_OFFSET) - timedelta(days=1)).date()
    date_str = local_yesterday.strftime("%Y-%m-%d")
    lines = [f"📊 *Raport dzienny — {date_str}*", f"Urządzenie: `{device_id}`", ""]

    # Praca sprężarki
    lines.append(f"⏱ Czas pracy sprężarki: *{hours_work:.1f} h*")
    lines.append(f"🔄 Starty sprężarki: *{comp_starts}*")
    if comp_starts > 0 and hours_work > 0:
        avg_run_min = (hours_work / comp_starts) * 60
        lines.append(f"📏 Śr. czas pracy/start: *{avg_run_min:.0f} min*")

    # Taktowanie
    if comp_starts > 12:
        lines.append(f"⚠️ *Taktowanie:* {comp_starts} startów/dzień (próg: 12)")

    # Temperatury
    if avg_amb is not None:
        lines.append(f"🌡 Śr. temp. zewnętrzna: *{avg_amb:.1f}°C*")
    if max_disc is not None:
        lines.append(f"🔥 Max temp. tłoczenia: *{max_disc:.1f}°C*")
        if max_disc >= 90:
            lines.append("⚠️ *Krytyczna temp. tłoczenia ≥90°C!*")

    # Energia (przybliżona)
    if avg_power_va and hours_work > 0:
        # P_el ≈ V * I * cos_phi / 10 (ac_curr ma skalę ×0.1)
        avg_p_kw = avg_power_va / 10.0 * 0.95 / 1000.0
        e_el_kwh = avg_p_kw * hours_work
        lines.append(f"⚡ Szacowane zużycie: *{e_el_kwh:.1f} kWh*")

    # Defrosty
    lines.append(f"❄️ Cykli odszraniania: *{defrost_count}*")

    # Awarie
    if faults_yesterday:
        lines.append("")
        lines.append("🚨 *Awarie:*")
        for fault_str in faults_yesterday:
            lines.append(f"  • {fault_str}")
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
        print(f"[Telegram] Wysłano raport dzienny ({device_id})", flush=True)
    return sent
