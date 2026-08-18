import os
import sys
from dotenv import load_dotenv

# Dodanie ścieżki do modułów app
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.services.tuya_client import TuyaPulsarClient
from app.services.database import init_db, save_properties_to_db

# Wczytanie zmiennych środowiskowych z pliku .env
load_dotenv()


def main():
    # Inicjalizacja struktury bazy danych SQLite przy starcie
    init_db()

    print("Łączenie z serwerem Tuya Pulsar (EU)...", flush=True)
    
    client = TuyaPulsarClient()
    client.connect()
    
    print("Oczekiwanie na zdarzenia z pompy ciepła (z włączonym filtrem Deadband)...\n", flush=True)
    
    try:
        client.listen(save_properties_to_db)
    except KeyboardInterrupt:
        print("Zatrzymano nasłuchiwanie.")
    finally:
        client.close()


if __name__ == "__main__":
    main()
