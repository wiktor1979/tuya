"""Klient Tuya Pulsar - obsługa połączenia i deszyfrowanie."""
import json
import base64
import hashlib
import time
from typing import Optional, Dict, Any
from Crypto.Cipher import AES
import pulsar

from app.config import (
    TUYA_ACCESS_ID, TUYA_ACCESS_KEY, PULSAR_SERVER_EU, 
    MQ_ENV_PROD, TEMP_CODES, THRESHOLDS, MAX_HEARTBEAT_SEC
)


class DeadbandFilter:
    """Filtr deadband dla telemetrii."""
    
    def __init__(self):
        self.last_saved_val: Dict[str, Any] = {}
        self.last_saved_time: Dict[str, float] = {}
    
    def should_save(self, code: str, new_val: Any) -> bool:
        """Decyduje, czy dana wartość parametru powinna zostać zapisana do bazy."""
        now = time.time()
        
        # 1. Pierwszy odczyt w historii -> zapisz
        if code not in self.last_saved_val:
            self.last_saved_val[code] = new_val
            self.last_saved_time[code] = now
            return True
        
        # 2. Heartbeat: upłynęło 5 minut od ostatniego zapisu tego parametru -> zapisz
        if (now - self.last_saved_time[code]) >= MAX_HEARTBEAT_SEC:
            self.last_saved_val[code] = new_val
            self.last_saved_time[code] = now
            return True

        old_val = self.last_saved_val[code]

        # 3. BARDZO WAŻNE: Jeśli wartość jest DOKŁADNIE taka sama -> IGNORUJ
        if new_val == old_val:
            return False

        # 4. Sprawdzanie progu dla rzeczywistych liczb (z wykluczeniem booleanów!)
        if isinstance(new_val, (int, float)) and not isinstance(new_val, bool):
            if isinstance(old_val, (int, float)) and not isinstance(old_val, bool):
                threshold = THRESHOLDS.get(code, 0.0)
                
                # Jeśli różnica jest mniejsza niż próg -> IGNORUJ
                if abs(new_val - old_val) < threshold:
                    return False

        # 5. Jeśli wartość się zmieniła i przeszła próg -> ZAPISZ
        self.last_saved_val[code] = new_val
        self.last_saved_time[code] = now
        return True


def get_authentication(access_id: str, access_key: str) -> pulsar.AuthenticationBasic:
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


def decrypt_message(pulsar_message: pulsar.Message, access_key: str) -> str:
    """Wyciąga dane z ramki Pulsar i wywołuje deszyfrowanie."""
    payload = pulsar_message.data().decode('utf-8')
    decrypt_model = pulsar_message.properties().get("em")
    
    data_json = json.loads(payload)
    encrypt_data = data_json['data']
    return decrypt_by_aes(encrypt_data, access_key, decrypt_model)


def message_id(msg_id: pulsar.MessageId) -> str:
    """Formatuje ID wiadomości Pulsar."""
    return f"{msg_id.ledger_id()}:{msg_id.entry_id()}:{msg_id.partition()}:{msg_id.batch_index()}"


class TuyaPulsarClient:
    """Klient do obsługi połączenia z Tuya Pulsar."""
    
    def __init__(self):
        if not TUYA_ACCESS_ID or not TUYA_ACCESS_KEY:
            raise ValueError("Brak kluczy TUYA_ACCESS_ID / TUYA_ACCESS_KEY w pliku .env!")
        
        self.filter = DeadbandFilter()
        self.client: Optional[pulsar.Client] = None
        self.consumer: Optional[pulsar.Consumer] = None
    
    def connect(self) -> None:
        """Łączy się z serwerem Tuya Pulsar."""
        print("Łączenie z serwerem Tuya Pulsar (EU)...", flush=True)

        self.client = pulsar.Client(
            PULSAR_SERVER_EU,
            authentication=get_authentication(TUYA_ACCESS_ID, TUYA_ACCESS_KEY),
            tls_allow_insecure_connection=True,
        )

        topic = f"{TUYA_ACCESS_ID}/out/{MQ_ENV_PROD}"
        subscription_name = f"{TUYA_ACCESS_ID}-sub"

        self.consumer = self.client.subscribe(
            topic,
            subscription_name,
            consumer_type=pulsar.ConsumerType.Failover
        )

        print(f"Połączono pomyślnie! Subskrypcja tematu: {topic}", flush=True)
        print("Oczekiwanie na zdarzenia z pompy ciepła (z włączonym filtrem Deadband)...\n", flush=True)
    
    def handle_parsed_payload(self, decrypted_json_str: str, save_callback) -> None:
        """Przetwarza odszyfrowaną wiadomość i zapisuje dane przez callback."""
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

                    if self.filter.should_save(code, check_val):
                        filtered_status_list.append(item)

                if filtered_status_list:
                    is_saved = save_callback(dev_id, filtered_status_list, event_time)
                    
                    if is_saved:
                        saved_codes = [f"{i['code']}={i['value']}" for i in filtered_status_list]
                        print(f"[{time.strftime('%H:%M:%S')}] Zapisano ({len(filtered_status_list)}/{len(status_list)}): {', '.join(saved_codes)}", flush=True)

        except Exception as e:
            print(f"Błąd przetwarzania/zapisu ramki: {e}", flush=True)
    
    def listen(self, save_callback) -> None:
        """Nasłuchuje wiadomości z Pulsar i przetwarza je."""
        if not self.consumer:
            raise RuntimeError("Najpierw wywołaj connect()")
        
        while True:
            try:
                pulsar_message = self.consumer.receive()
                decrypted_msg = decrypt_message(pulsar_message, TUYA_ACCESS_KEY)
                
                self.handle_parsed_payload(decrypted_msg, save_callback)
                
                self.consumer.acknowledge_cumulative(pulsar_message)
            except pulsar.Interrupted:
                print("Zatrzymano nasłuchiwanie.")
                break
            except Exception as e:
                print(f"Błąd podczas przetwarzania ramki: {e}", flush=True)
    
    def close(self) -> None:
        """Zamyka połączenie z Pulsar."""
        if self.client:
            self.client.close()
