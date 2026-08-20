# System Monitorowania Pompy Ciepła Tuya

Aplikacja do monitorowania pompy ciepła z wykorzystaniem API Tuya Pulsar (EU) z zaawansowaną diagnostyką i integracją pogodową.

## Struktura projektu

```
/workspace
├── app/                          # Główny pakiet aplikacji
│   ├── __init__.py
│   ├── config.py                 # Konfiguracja i stałe
│   ├── models/                   # Modele danych
│   │   ├── __init__.py
│   │   └── telemetry.py          # Modele telemetryczne
│   ├── services/                 # Usługi biznesowe
│   │   ├── __init__.py
│   │   ├── database.py           # Warstwa dostępu do bazy (z poolingiem, WAL, indeksami)
│   │   ├── tuya_client.py        # Klient Tuya Pulsar z filtrem deadband
│   │   ├── calculator.py         # Kalkulator COP/SCOP
│   │   ├── exporter.py           # Eksport CSV
│   │   └── analytics.py          # Zaawansowana diagnostyka i analiza
│   └── ui/                       # Komponenty UI
│       └── __init__.py
├── main.py                       # Skrypt zbieracza danych (z wątkiem pogodowym)
├── dashboard.py                  # Dashboard Streamlit (6 zakładek)
├── db.py                         # Warstwa kompatybilności wstecznej
├── requirements.txt              # Zależności Python
├── Dockerfile                    # Kontener Docker
├── fly.toml                      # Konfiguracja Fly.io
└── start.sh                      # Skrypt startowy
```

## Architektura

Projekt został poddany refaktoryzacji zgodnie z zasadą pojedynczej odpowiedzialności (SRP):

- **config.py** - Centralne miejsce na zmienne środowiskowe i stałe konfiguracji
- **models/** - Definicje struktur danych (dataclasses)
- **services/** - Logika biznesowa podzielona na niezależne moduły:
  - `database.py` - Operacje CRUD na SQLite z connection pooling, trybem WAL i optymalnymi indeksami
  - `tuya_client.py` - Komunikacja z Tuya Pulsar, deszyfrowanie AES-GCM/ECB, filtr deadband z `__slots__`
  - `calculator.py` - Obliczenia wydajności (COP, SCOP, energia)
  - `exporter.py` - Eksport danych do CSV
  - `analytics.py` - Zaawansowana diagnostyka: wykrywanie cykli krótkich, analiza inwertera, szacowanie COP, korelacja pogodowa
- **ui/** - Komponenty interfejsu użytkownika
- **db.py** - Warstwa kompatybilności dla istniejących importów
- **main.py** - Główny skrypt zbieracza z wątkiem pogodowym (Open-Meteo API)

### Optymalizacje wydajności

- **Connection Pooling**: Thread-local storage połączeń SQLite
- **Tryb WAL**: Lepsza współbieżność zapisu/odczytu
- **Cache SQLite**: 64MB cache dla redukcji operacji dyskowych
- **Indeksy**: 
  - `idx_dev_code_time` - dla zapytań filtrowanych po urządzeniu i kodzie
  - `idx_time_desc` - dla zapytań sortowanych malejąco po czasie
- **Kontekst menedżer**: Automatyczne commit/zamykanie kursorów
- **`__slots__`**: Redukcja zużycia pamięci o ~40-50% w filtrze deadband

## Instalacja

```bash
pip install -r requirements.txt
```

## Uruchomienie

### Zbieracz danych (collector)
```bash
python main.py
```

### Obsługa wielu pomp ciepła na różnych kontach Tuya

Aplikacja obsługuje monitorowanie wielu pomp ciepła z różnych kont Tuya.

### Konfiguracja dla pojedynczego konta

W pliku `.env` ustaw:

```bash
TUYA_ACCESS_ID=twoje_access_id
TUYA_ACCESS_KEY=twoje_access_key
TUYA_DEVICE_IDS=bf874f7ae72aca1fc23op0,drugie_urzadzenie_id
```

### Konfiguracja dla wielu kont

Użyj zmiennej `TUYA_ACCOUNTS_JSON` zamiast powyższych:

```bash
TUYA_ACCOUNTS_JSON=[
  {
    "access_id": "konto1_access_id",
    "access_key": "konto1_access_key",
    "devices": ["device_id_1", "device_id_2"]
  },
  {
    "access_id": "konto2_access_id", 
    "access_key": "konto2_access_key",
    "devices": ["device_id_3"]
  }
]
```

Gdzie:
- `access_id` i `access_key` to dane z Twojego konta Tuya IoT Platform
- `devices` to opcjonalna lista ID urządzeń do monitorowania (jeśli pominięta, monitorowane są wszystkie urządzenia na koncie)

### Uruchomienie

```bash
python main.py
```

Aplikacja automatycznie wykryje liczbę skonfigurowanych kont i uruchomi odpowiedni tryb pracy.

## Dashboard
```bash
streamlit run dashboard.py --server.port 8501
```

Dashboard zawiera 6 zakładek:
1. **Panel Główny** - Podstawowe metryki i status systemu
2. **Bilans Energetyczny & SCOP** - Bilans energetyczny i zużycie
3. **Diagnostyka Pompy** - Zaawansowana analiza: cykle krótkie, praca inwertera, czasy trybów, rekomendacje
4. **Kontekst Pogodowy** - Korelacja temperatury zewnętrznej z pracą pompy, wykresy zależności
5. **Fizyczny Licznik Energii** - Zarządzanie ręcznymi odczytami licznika
6. **Eksport Danych** - Eksport danych do CSV

### Docker
```bash
docker build -t heat-pump-monitor .
docker run -p 8501:8501 heat-pump-monitor
```

## Zmienne środowiskowe

Wymagany plik `.env` (pojedyncze konto):
```
TUYA_ACCESS_ID=twoj_access_id
TUYA_ACCESS_KEY=twoj_access_key
TUYA_DEVICE_IDS=bf874f7ae72aca1fc23op0  # opcjonalnie, lista ID urządzeń oddzielonych przecinkami
```

Alternatywnie dla wielu kont Tuya:
```
TUYA_ACCOUNTS_JSON=[
  {
    "access_id": "konto1_access_id",
    "access_key": "konto1_access_key",
    "devices": ["device_id_1", "device_id_2"]
  },
  {
    "access_id": "konto2_access_id", 
    "access_key": "konto2_access_key",
    "devices": ["device_id_3"]
  }
]
```

Dodatkowe zmienne opcjonalne:
```
LATITUDE=51.7592  # Szerokość geograficzna dla danych pogodowych (domyślnie Łódź)
LONGITUDE=19.4560  # Długość geograficzna dla danych pogodowych
LOCATION_NAME="Łódź"  # Nazwa lokalizacji
```

## Funkcje

### Podstawowe
- ✅ Pobieranie telemetrii z Tuya Pulsar (EU)
- ✅ Deszyfrowanie AES-GCM/ECB
- ✅ Filtr Deadband (redukcja szumu, zoptymalizowany z `__slots__`)
- ✅ Zapis do SQLite z indeksami i connection poolingiem
- ✅ Ręczne wpisy licznika energii
- ✅ Obliczanie COP i SCOP (CO/CWU)
- ✅ Bilans energetyczny [kWh]
- ✅ Wykrywanie cykli defrost
- ✅ Eksport danych do CSV
- ✅ Dashboard Streamlit z wykresami Plotly

### Zaawansowana Diagnostyka
- 🔍 **Wykrywanie cykli krótkich** - Analiza częstotliwości startów pompy
- 🔍 **Analiza pracy inwertera** - Ocena modulacji mocy i stabilności
- 🔍 **Szacowanie COP** - Estymacja współczynnika wydajności na podstawie danych
- 🔍 **Czasy trybów pracy** - Statystyki czasu pracy CO vs CWU
- 🔍 **Korelacja pogodowa** - Zależność między temperaturą zewnętrzną a zużyciem energii
- 🔍 **Automatyczne rekomendacje** - Sugestie optymalizacji pracy pompy
- 🔍 **Szacowanie strat energii** - Identyfikacja nieefektywnych okresów pracy
- 🔍 **Analiza efektywności modulacji** - Ocena pracy inwertera przy zmiennym obciążeniu

### Integracja Pogodowa
- 🌤️ **Open-Meteo API** - Automatyczne pobieranie danych co godzinę
- 🌤️ **Dane historyczne** - Temperatura, opady, zachmurzenie, wiatr
- 🌤️ **Kontekst dla analiz** - Powiązanie warunków pogodowych z pracą pompy
- 🌤️ **Prognoza wpływu** - Jak temperatura zewnętrzna wpływa na COP

## Rozwój

Projekt jest przygotowany do dalszego rozwoju:
- Dodawanie testów jednostkowych (`tests/`)
- Migracje bazy danych (Alembic)
- CI/CD (GitHub Actions)
- Alerty (Telegram, e-mail)
- Integracje smart home (Home Assistant)
- Machine Learning do predykcji zużycia energii
- Panel administracyjny do zarządzania wieloma instalacjami
