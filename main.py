import os
import json
import logging
from tuya_iot import (
    TuyaOpenPulsar,
    TuyaCloudPulsarTopic,
    TuyaLogging
)

TuyaLogging.configure()

# Pobieranie danych z bezpiecznych zmiennych środowiskowych w Render
ACCESS_ID = os.environ.get("TUYA_ACCESS_ID")
ACCESS_KEY = os.environ.get("TUYA_ACCESS_KEY")
ENDPOINT = TuyaCloudPulsarTopic.EU

def save_data(device_id, timestamp, status_list):
    print(f"\n[ODEBRANO ZDARZENIE] Urządzenie: {device_id} | Czas: {timestamp}")
    for item in status_list:
        code = item.get("code")
        val = item.get("value")
        print(f"  -> Parametr: {code} = {val}")
        
        # TUTAJ DODAJ ZAPIS (np. wysyłanie danych do zewnętrznej bazy lub webhooka)

def message_handler(msg):
    try:
        payload = json.loads(msg)
        dev_id = payload.get("devId")
        status = payload.get("status", [])
        t = payload.get("dataId")
        if dev_id and status:
            save_data(dev_id, t, status)
    except Exception as e:
        logging.error(f"Błąd przetwarzania: {e}")

def main():
    if not ACCESS_ID or not ACCESS_KEY:
        raise ValueError("Brak zdefiniowanych kluczy TUYA_ACCESS_ID / TUYA_ACCESS_KEY w środowisku!")

    pulsar = TuyaOpenPulsar(ACCESS_ID, ACCESS_KEY, ENDPOINT, TuyaCloudPulsarTopic.PROD)
    pulsar.add_message_listener(message_handler)
    print("Uruchamianie serwisu Tuya na Render.com...")
    pulsar.start()

if __name__ == "__main__":
    main()
