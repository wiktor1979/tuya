import os
import json
import logging
import time
from tuya_connector import (
    TuyaOpenPulsar,
    TuyaCloudPulsarTopic,
)

# Konfiguracja logów
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)

# Pobieranie kluczy z Secrets Fly.io
ACCESS_ID = os.environ.get("TUYA_ACCESS_ID")
ACCESS_KEY = os.environ.get("TUYA_ACCESS_KEY")

# Endpoint Pulsar dla Europy (domyślny port WSS Tuya)
MQ_ENDPOINT = "wss://mqe.tuyaeu.com:8285/"

def save_data(device_id, timestamp, status_list):
    print(f"\n[ODEBRANO DANE] Urządzenie: {device_id} | Czas: {timestamp}")
    for item in status_list:
        code = item.get("code")
        val = item.get("value")
        print(f"  -> {code} = {val}")

def message_handler(msg):
    try:
        payload = json.loads(msg)
        dev_id = payload.get("devId")
        status = payload.get("status", [])
        t = payload.get("dataId")
        
        if dev_id and status:
            save_data(dev_id, t, status)
    except Exception as e:
        logging.error(f"Błąd przetwarzania wiadomości: {e}")

def main():
    if not ACCESS_ID or not ACCESS_KEY:
        raise ValueError("Brak zdefiniowanych kluczy TUYA_ACCESS_ID / TUYA_ACCESS_KEY w Secrets!")

    logging.info("Inicjalizacja połączenia TuyaOpenPulsar...")

    # Prawidłowa klasa z tuya-connector-python
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

    # Podtrzymanie pętli głównego wątku
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        open_pulsar.stop()

if __name__ == "__main__":
    main()
