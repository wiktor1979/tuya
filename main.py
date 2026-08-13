import os
import json
import base64
import hashlib
import pulsar
import time
from Crypto.Cipher import AES
from dotenv import load_dotenv
from db import init_db, save_properties_to_db

# Wczytanie zmiennych środowiskowych z pliku .env
load_dotenv()

ACCESS_ID = os.environ.get("TUYA_ACCESS_ID")
ACCESS_KEY = os.environ.get("TUYA_ACCESS_KEY")

# Konfiguracja środowiska i serwera EU Tuya
MQ_ENV_PROD = "event"
PULSAR_SERVER_EU = "pulsar+ssl://mqe.tuyaeu.com:7285/"

# Słowniki do pamiętania ostatnich zapisanych wartości i czasów
last_saved_val = {}
last_saved_time = {}

# Kody parametrów będących temperaturami (wymagają podziału przez 10 do realnej wartości °C)
TEMP_CODES = {
    "in_water_temp", "out_water_temp", "tank_temp", 
    "amb_temp", "disc_temp", "back_temp", "tidr",
    "cool_temp_set", "heat_temp_set", "hot_water_temp_set"
}

# Progi zmian dla poszczególnych parametrów (Deadband)
THRESHOLDS = {
    "out_water_temp": 0.2,  # Zapisz gdy zmiana >= 0.2 °C
    "in_water_temp": 0.2,
    "tank_temp": 0.3,
    "amb_temp": 0.5,
    "ac_curr": 0.1,         # Zapisz gdy zmiana prądu >= 0.1 A
    "ac_vol": 3.0,          # Zapisz gdy zmiana napięcia >= 3.0 V
    "comp_freq": 1.0,       # Zapisz gdy zmiana częstotliwości >= 1 Hz
    "flow_rate": 1.0,        # Zapisz gdy zmiana surowej wartości przepływu
    "disc_temp": 0.5,       # 
    "back_temp": 0.5       # 
}

MAX_HEARTBEAT_SEC = 300  # Wymuś zapis co najmniej raz na 5 minut (300 s)


def should_save(code: str, new_val):
    """
    Decyduje, czy dana wartość parametru powinna zostać zapisana do bazy.
    Flagi i parametry bez zmian są natychmiast odrzucane.
    """
    now = time.time()
    
    # 1. Pierwszy odczyt w historii -> zapisz
    if code not in last_saved_val:
        last_saved_val[code] = new_val
        last_saved_time[code] = now
        return True
    
    # 2. Heartbeat: upłynęło 5 minut od ostatniego zapisu tego parametru -> zapisz
    if (now - last_saved_time[code]) >= MAX_HEARTBEAT_SEC:
        last_saved_val[code] = new_val
        last_saved_time[code] = now
        return True

    old_val = last_saved_val[code]

    # 3. BARDZO WAŻNE: Jeśli wartość jest DOKŁADNIE taka sama -> IGNORUJ
    if new_val == old_val:
        return False

    # 4. Sprawdzanie progu dla rzeczywistych liczb (z wykluczeniem booleanów!)
    if isinstance(new_val, (int, float)) and not isinstance(new_val, bool):
        if isinstance(old_val, (int, float)) and not isinstance(old_val, bool):
            threshold = THRESHOLDS.get(code, 0.0)
            
            # Jeśli różnica jest mniejsza niż próg (np. zmiana o 0.1°C przy progu 0.2°C) -> IGNORUJ
            if abs(new_val - old_val) < threshold:
                return False

    # 5. Jeśli wartość się zmieniła i przeszła próg (lub jest tozmiana tekstu/booleana) -> ZAPISZ
    last_saved_val[code] = new_val
    last_saved_time[code] = now
    return True


def get_authentication(access_id: str, access_key: str):
    """Generuje autoryzację MD5 wymaganą przez serwer Pulsar Tuya."""
    md5_access_key = hashlib.md5(access_key.encode('utf-8')).hexdigest()
    combined = access_id + md5_access_key
    md5_combined = hashlib.md5(combined.encode('utf-8')).hexdigest()
    
    password = '"' + md5_combined[8:24] + '"}'
    user_name = '{{"username": "{}","password"'.format(access_id)
    return pulsar.AuthenticationBasic(user_name, password, "auth1")


def decrypt_by_gcm(raw_bytes: bytes, key_bytes: bytes) -> str:
    """Deszyfrowanie AES-GCM."""
    nonce = raw_bytes[:12]
    ciphertext = raw_bytes[12:-16]
    auth_tag = raw_bytes[-16:]
    aes_cipher = AES.new(key_bytes, AES.MODE_GCM, nonce)
    return aes_cipher.decrypt_and_verify(ciphertext, auth_tag).decode('utf-8')


def decrypt_by_ecb(raw_bytes: bytes, key_bytes: bytes) -> str:
    """Deszyfrowanie AES-ECB."""
    cipher = AES.new(key_bytes, AES.MODE_ECB)
    decrypted_data = cipher.decrypt(raw_bytes)
    res_str = decrypted_data.decode('utf-8')
    return res_str.replace('\r', '').replace('\n', '').replace('\f', '')


def decrypt_by_aes(raw: str, key: str, decrypt_model: str) -> str:
    """Wybiera odpowiedni algorytm deszyfrowania."""
    raw_bytes = base64.b64decode(raw)
    key_bytes = key[8:24].encode('utf-8')

    if decrypt_model == "aes_gcm":
        return decrypt_by_gcm(raw_bytes, key_bytes)
    else:
        return decrypt_by_ecb(raw_bytes, key_bytes)


def decrypt_message(pulsar_message, access_key: str):
    """Wyciąga dane z ramki Pulsar i wywołuje deszyfrowanie."""
    payload = pulsar_message.data().decode('utf-8')
    decrypt_model = pulsar_message.properties().get("em")
    
    data_json = json.loads(payload)
    encrypt_data = data_json['data']
    return decrypt_by_aes(encrypt_data, access_key, decrypt_model)


def message_id(msg_id) -> str:
    return f"{msg_id.ledger_id()}:{msg_id.entry_id()}:{msg_id.partition()}:{msg_id.batch_index()}"


def handle_parsed_payload(decrypted_json_str: str):
    try:
        data = json.loads(decrypted_json_str)
        biz_data = data.get("bizData", {}) if isinstance(data.get("bizData"), dict) else {}
        
        dev_id = biz_data.get("devId") or data.get("devId")
        status_list = (
            biz_data.get("properties") or 
            biz_data.get("status") or 
            data.get("status") or []
        )
        
        raw_ts = data.get("ts") or biz_data.get("ts")
        event_time = int(raw_ts / 1000) if raw_ts else int(time.time())

        if dev_id and status_list:
            filtered_status_list = []

            for item in status_list:
                code = item.get("code")
                val = item.get("value")

                # Przeliczenie wartości do testu (temperatury / 10)
                check_val = val
                if code in TEMP_CODES and isinstance(val, (int, float)) and not isinstance(val, bool):
                    check_val = val / 10.0

                if should_save(code, check_val):
                    filtered_status_list.append(item)

            if filtered_status_list:
                # Wywołanie z uwzględnieniem sprawdzenia, czy faktycznie zapisano
                is_saved = save_properties_to_db(dev_id, filtered_status_list, event_time)
                
                if is_saved:
                    saved_codes = [f"{i['code']}={i['value']}" for i in filtered_status_list]
                    print(f"[{time.strftime('%H:%M:%S')}] Zapisano ({len(filtered_status_list)}/{len(status_list)}): {', '.join(saved_codes)}", flush=True)

    except Exception as e:
        print(f"Błąd przetwarzania/zapisu ramki: {e}", flush=True)


def main():
    # Inicjalizacja struktury bazy danych SQLite przy starcie
    init_db()

    if not ACCESS_ID or not ACCESS_KEY:
        raise ValueError("Brak kluczy TUYA_ACCESS_ID / TUYA_ACCESS_KEY w pliku .env!")

    print("Łączenie z serwerem Tuya Pulsar (EU)...", flush=True)

    client = pulsar.Client(
        PULSAR_SERVER_EU,
        authentication=get_authentication(ACCESS_ID, ACCESS_KEY),
        tls_allow_insecure_connection=True,
    )

    topic = f"{ACCESS_ID}/out/{MQ_ENV_PROD}"
    subscription_name = f"{ACCESS_ID}-sub"

    consumer = client.subscribe(
        topic,
        subscription_name,
        consumer_type=pulsar.ConsumerType.Failover
    )

    print(f"Połączono pomyślnie! Subskrypcja tematu: {topic}", flush=True)
    print("Oczekiwanie na zdarzenia z pompy ciepła (z włączonym filtrem Deadband)...\n", flush=True)

    while True:
        try:
            pulsar_message = consumer.receive()
            decrypted_msg = decrypt_message(pulsar_message, ACCESS_KEY)
            
            # Przetwarzanie z filtracją
            handle_parsed_payload(decrypted_msg)
            
            # Potwierdzenie odbioru
            consumer.acknowledge_cumulative(pulsar_message)
        except pulsar.Interrupted:
            print("Zatrzymano nasłuchiwanie.")
            break
        except Exception as e:
            print(f"Błąd podczas przetwarzania ramki: {e}", flush=True)

    client.close()


if __name__ == "__main__":
    main()