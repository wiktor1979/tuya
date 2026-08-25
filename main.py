import time
import threading

from app.services.tuya_client import TuyaPulsarClient, MultiAccountTuyaClient, get_tuya_accounts
from app.services.database import init_db, save_properties_to_db, save_weather_data
from app.config import LATITUDE, LONGITUDE, LOCATION_NAME


def fetch_weather_loop():
    """Wątek pobierający dane pogodowe z API Open-Meteo co godzinę."""
    import requests
    
    print(f"Uruchomiono wątek pogodowy dla lokalizacji: {LOCATION_NAME} ({LATITUDE}, {LONGITUDE})", flush=True)
    
    while True:
        try:
            url = "https://api.open-meteo.com/v1/forecast"
            params = {
                "latitude": LATITUDE,
                "longitude": LONGITUDE,
                "current": ["temperature_2m", "relative_humidity_2m", "wind_speed_10m", "precipitation"],
                "timezone": "auto"
            }
            
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            current = data.get("current", {})
            
            timestamp = int(time.time())
            temperature = current.get("temperature_2m")
            humidity = current.get("relative_humidity_2m")
            windspeed = current.get("wind_speed_10m")
            precipitation = current.get("precipitation")
            
            if temperature is not None:
                save_weather_data(
                    timestamp=timestamp,
                    temperature=temperature,
                    humidity=humidity or 0.0,
                    windspeed=windspeed or 0.0,
                    precipitation=precipitation or 0.0,
                    latitude=LATITUDE,
                    longitude=LONGITUDE
                )
                print(f"Zapisano dane pogodowe: temp={temperature}°C", flush=True)
            else:
                print("Błąd: Brak danych temperatury w odpowiedzi API", flush=True)
                
        except requests.exceptions.RequestException as e:
            print(f"Błąd połączenia z Open-Meteo: {e}", flush=True)
        except Exception as e:
            print(f"Nieoczekiwany błąd w wątku pogodowym: {e}", flush=True)
        
        # Czekaj 1 godzinę przed następnym pobraniem
        time.sleep(3600)


def main():
    # Inicjalizacja struktury bazy danych SQLite przy starcie
    init_db()

    # Uruchom wątek pogodowy
    weather_thread = threading.Thread(target=fetch_weather_loop, daemon=True)
    weather_thread.start()

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
