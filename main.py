import os
import sys
from dotenv import load_dotenv

# Dodanie ścieżki do modułów app
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.services.tuya_client import TuyaPulsarClient, MultiAccountTuyaClient, get_tuya_accounts
from app.services.database import init_db, save_properties_to_db

# Wczytanie zmiennych środowiskowych z pliku .env
load_dotenv()


def main():
    # Inicjalizacja struktury bazy danych SQLite przy starcie
    init_db()

    # Pobierz skonfigurowane konta Tuya
    accounts = get_tuya_accounts()
    
    if not accounts:
        print("BŁĄD: Brak skonfigurowanych kont Tuya!", flush=True)
        print("Skonfiguruj zmienne środowiskowe:", flush=True)
        print("  - TUYA_ACCESS_ID i TUYA_ACCESS_KEY (pojedyncze konto)", flush=True)
        print("  - lub TUYA_ACCOUNTS_JSON (wiele kont w formacie JSON)", flush=True)
        return

    print(f"Znaleziono {len(accounts)} skonfigurowanych kont Tuya.", flush=True)

    if len(accounts) == 1:
        # Pojedyncze konto - użyj prostszego klienta
        print("Uruchamianie w trybie pojedynczego konta...", flush=True)
        client = TuyaPulsarClient(accounts[0])
        client.connect()
        
        print("Oczekiwanie na zdarzenia z pompy ciepła (z włączonym filtrem Deadband)...\n", flush=True)
        
        try:
            client.listen(save_properties_to_db)
        except KeyboardInterrupt:
            print("Zatrzymano nasłuchiwanie.")
        finally:
            client.close()
    else:
        # Wiele kont - użyj klienta wielokontowego
        print("Uruchamianie w trybie wielu kont...", flush=True)
        multi_client = MultiAccountTuyaClient()
        
        for account in accounts:
            multi_client.add_account(account)
        
        try:
            multi_client.start_listening(save_properties_to_db)
        except KeyboardInterrupt:
            print("Zatrzymano nasłuchiwanie.")
        finally:
            multi_client.close_all()


if __name__ == "__main__":
    main()
