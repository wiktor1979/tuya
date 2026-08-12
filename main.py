import os
import json
import logging
import time
import base64
from tuya_connector import (
    TuyaOpenPulsar,
    TuyaCloudPulsarTopic,
    TuyaLogging
)
from Crypto.Cipher import AES

# Włączenie rozszerzonych logów SDK Tuya dla diagnostyki
TuyaLogging.configure()

# Konfiguracja logów głównych
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)

ACCESS_ID = os.environ.get("TUYA_ACCESS_ID")
ACCESS_KEY = os.environ.get("TUYA_ACCESS_KEY")

# Endpoint Pulsar dla Europy
MQ_ENDPOINT = TuyaCloudPulsarTopic.EU


def decrypt_tuya_gcm(encrypted_base64_str: str, access_key: str) -> dict:
    """
    Deszyfruje ładunek Tuya Message Queue zaszyfrowany algorytmem AES-GCM.
    Kluczem jest pierwsze 16 bajtów ciągu ACCESS_KEY.
    """
    # 1. Przygotowanie klucza AES-128 (16 bajtów z ACCESS_KEY)
    key = access_key[:16].encode('utf-8')
    
    # 2. Dekodowanie z Base64 do surowych bajtów
    raw_data = base64.b64decode(encrypted_base64_str)
    
    # 3. Wyciągnięcie elementów struktury AES-GCM (IV 12B, TAG 16B)
    iv = raw_data[:12]
    tag = raw_data[-16:]
    ciphertext = raw_data[12:-16]
    
    # 4. Inicjalizacja szyfru i odszyfrowanie z weryfikacją
    cipher = AES.new(key, AES.MODE_GCM, nonce=iv)
    decrypted_bytes = cipher.decrypt_and_verify(ciphertext, tag)
    
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
        logging.info("Odebrano ramkę z Tuya WebSocket.")
        
        # 1. Parsowanie wiadomości nagłówkowej
        if isinstance(msg, str):
            payload = json.loads(msg)
        else:
            payload = msg

        # 2. Deszyfrowanie ładunku zawartego w polu "data"
        if "data" in payload and isinstance(payload["data"], str):
            encrypted_str = payload["data"]
            decrypted_payload = None
            
            # Próba 1: AES-GCM
            try:
                decrypted_payload = decrypt_tuya_gcm(encrypted_str, ACCESS_KEY)
                logging.info("Pomyślnie odszyfrowano wiadomość (AES-GCM).")
            except Exception as e_gcm:
                logging.warning(f"AES-GCM nie powiodło się ({e_gcm}), próba fallback do AES-ECB...")
                
                # Próba 2: Fallback do domyślnego AES-ECB z SDK Tuya
                try:
                    from tuya_connector.pulsar import decrypt_data
                    decrypted_str = decrypt_data(encrypted_str, ACCESS_KEY)
                    decrypted_payload = json.loads(decrypted_str)
                    logging.info("Pomyślnie odszyfrowano wiadomość (AES-ECB).")
                except Exception as e_ecb:
                    logging.error(f"Nie udało się odszyfrować wiadomości żaden z algorytmów: {e_ecb}")

            if decrypted_payload:
                payload = decrypted_payload

        # 3. Odczyt danych urządzenia
        dev_id = payload.get("devId") or payload.get("nodeId")
        status = payload.get("status", [])
        t = payload.get("dataId") or payload.get("t")

        if dev_id and status:
            save_data(dev_id, t, status)
        else:
            logging.info(f"Odebrano pakiet bez zmian stanu: {payload}")

    except Exception as e:
        logging.error(f"Błąd przetwarzania ramki wiadomości: {e}", exc_info=True)


def main():
    if not ACCESS_ID or not ACCESS_KEY:
        raise ValueError("Brak zdefiniowanych kluczy TUYA_ACCESS_ID / TUYA_ACCESS_KEY w Secrets Fly.io!")

    logging.info("Inicjalizacja połączenia TuyaOpenPulsar...")

    open_pulsar = TuyaOpenPulsar(
        ACCESS_ID,
        ACCESS_KEY,
        MQ_ENDPOINT,
        TuyaCloudPulsarTopic.PROD
    )
    
    open_pulsar.add_message_listener(message_handler)
    open_pulsar.start()
    logging.info("Serwis wystartował pomyślnie na Fly.io. Nasłuchiwanie zdarzeń...")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        open_pulsar.stop()


if __name__ == "__main__":
    main()
