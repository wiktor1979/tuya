import os
import json
import logging
import time
import base64
import hashlib
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


from Crypto.Cipher import AES

def decrypt_tuya_gcm(encrypted_base64_str: str, access_key: str) -> dict:
    """
    Deszyfruje ładunek Tuya Message Queue zaszyfrowany algorytmem AES-GCM.
    """
    # 1. Przygotowanie klucza: MD5(access_key) obcięty do 16 bajtów (AES-128)
    key = hashlib.md5(access_key.encode('utf-8')).hexdigest()[8:24].encode('utf-8')
    
    # 2. Dekodowanie ciągu Base64 do postaci surowych bajtów
    raw_data = base64.b64decode(encrypted_base64_str)
    
    # 3. Wyciągnięcie elementów struktury AES-GCM:
    # Standardowo w Tuya: IV (12 bajtów) + Ciphertext + Tag (16 bajtów)
    iv = raw_data[:12]
    tag = raw_data[-16:]
    ciphertext = raw_data[12:-16]
    
    # 4. Inicjalizacja szyfru AES w trybie GCM
    cipher = AES.new(key, AES.MODE_GCM, nonce=iv)
    
    # 5. Odszyfrowanie i weryfikacja tagu autentyczności
    decrypted_bytes = cipher.decrypt_and_verify(ciphertext, tag)
    
    # 6. Parsowanie zdekodowanego napisu UTF-8 do słownika JSON
    return json.loads(decrypted_bytes.decode('utf-8'))


def save_data(device_id, timestamp, status_list):
    print(f"\n[ODEBRANO DANE] Urządzenie: {device_id} | Czas: {timestamp}", flush=True)
    for item in status_list:
        code = item.get("code")
        val = item.get("value")
        print(f"  -> {code} = {val}", flush=True)
        logging.info(f"Zapisano parametr {code} = {val}")

def message_handler(msg):
    try:
        if isinstance(msg, str):
            payload = json.loads(msg)
        else:
            payload = msg

        # Jeśli pakiet zawiera zaszyfrowane dane w polu "data"
        if "data" in payload and isinstance(payload["data"], str):
            encrypted_str = payload["data"]
            
            try:
                # Próba deszyfrowania nowszym algorytmem AES-GCM
                decrypted_payload = decrypt_tuya_gcm(encrypted_str, ACCESS_KEY)
            except Exception:
                # Fallback: domyślny dekoder Tuya (AES-ECB)
                from tuya_connector.pulsar import decrypt_data
                decrypted_str = decrypt_data(encrypted_str, ACCESS_KEY)
                decrypted_payload = json.loads(decrypted_str)

            payload = decrypted_payload

        dev_id = payload.get("devId")
        status = payload.get("status", [])
        t = payload.get("dataId") or payload.get("t")

        if dev_id and status:
            save_data(dev_id, t, status)

    except Exception as e:
        logging.error(f"Błąd deszyfrowania/przetwarzania ramki AES-GCM: {e}")

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
