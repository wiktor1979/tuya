import os
import json
import logging
import time
from tuya_connector import (
    TuyaOpenPulsar,
    TuyaCloudPulsarTopic,
    TuyaLogging
)

# Włączenie rozszerzonych logów SDK Tuya dla diagnostyki
TuyaLogging.configure()

# Konfiguracja logów głównych
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)

ACCESS_ID = os.environ.get("TUYA_ACCESS_ID")
ACCESS_KEY = os.environ.get("TUYA_ACCESS_KEY")

# Używamy stałej z biblioteki dla regionu Europy (EU)
MQ_ENDPOINT = TuyaCloudPulsarTopic.EU

def save_data(device_id, timestamp, status_list):
    print(f"\n[ODEBRANO DANE] Urządzenie: {device_id} | Czas: {timestamp}", flush=True)
    for item in status_list:
        code = item.get("code")
        val = item.get("value")
        print(f"  -> {code} = {val}", flush=True)
        logging.info(f"Zapisano parametr {code} = {val}")

def message_handler(msg):
    try:
        # 1. Dekodowanie / Odszyfrowanie pakietu danych wywołaniem metody dekodującej Tuya
        # Wiadomość trafia tu jako zaszyfrowany string lub obiekt danych
        if isinstance(msg, str):
            payload = json.loads(msg)
        else:
            payload = msg

        # Jeśli treść jest zaszyfrowana w polu "data", dekodujemy ją za pomocą ACCESS_KEY
        if "data" in payload and isinstance(payload["data"], str):
            from tuya_connector.pulsar import decrypt_data
            decrypted_str = decrypt_data(payload["data"], ACCESS_KEY)
            payload = json.loads(decrypted_str)

        # 2. Wyciąganie właściwych pól ze zdarzenia
        dev_id = payload.get("devId")
        status = payload.get("status", [])
        t = payload.get("dataId") or payload.get("t")

        if dev_id and status:
            save_data(dev_id, t, status)
        else:
            logging.debug(f"Odebrano pakiet bez zmian stanu: {payload}")

    except Exception as e:
        logging.error(f"Błąd przetwarzania/dekodowania wiadomości: {e}")

def main():
    if not ACCESS_ID or not ACCESS_KEY:
        raise ValueError("Brak zdefiniowanych kluczy TUYA_ACCESS_ID / TUYA_ACCESS_KEY w Secrets!")

    logging.info("Inicjalizacja połączenia TuyaOpenPulsar...")

    open_pulsar = TuyaOpenPulsar(
        ACCESS_ID,
        ACCESS_KEY,
        MQ_ENDPOINT,
        TuyaCloudPulsarTopic.PROD
    )
    
    # Dodanie słuchacza zdarzeń
    open_pulsar.add_message_listener(message_handler)
    
    # Start nasłuchiwania w tle
    open_pulsar.start()
    logging.info("Serwis wystartował pomyślnie na Fly.io. Nasłuchiwanie zdarzeń...")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        open_pulsar.stop()

if __name__ == "__main__":
    main()
