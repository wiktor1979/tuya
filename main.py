import os
import json
import logging
import time
from tuya_sharing import (
    CustomerDeviceMsg,
    Manager,
    TuyaOpenPulsar,
    TuyaCloudPulsarTopic,
)

logging.basicConfig(level=logging.INFO)

ACCESS_ID = os.environ.get("TUYA_ACCESS_ID")
ACCESS_KEY = os.environ.get("TUYA_ACCESS_KEY")
ENDPOINT = TuyaCloudPulsarTopic.EU

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
        raise ValueError("Brak zdefiniowanych kluczy TUYA_ACCESS_ID / TUYA_ACCESS_KEY!")

    # Inicjalizacja klienta Pulsar w nowym SDK Tuya
    pulsar = TuyaOpenPulsar(
        ACCESS_ID, 
        ACCESS_KEY, 
        ENDPOINT, 
        TuyaCloudPulsarTopic.PROD
    )
    
    pulsar.add_message_listener(message_handler)
    print("Serwis Tuya wystartował na Fly.io...")
    pulsar.start()

    # Podtrzymanie działania głównego wątku
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pulsar.stop()

if __name__ == "__main__":
    main()
