# System Monitorowania Pompy Ciepła Tuya

Aplikacja do monitorowania pompy ciepła z wykorzystaniem API Tuya Pulsar (EU).

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
│   │   ├── database.py           # Warstwa dostępu do bazy
│   │   ├── tuya_client.py        # Klient Tuya Pulsar
│   │   ├── calculator.py         # Kalkulator COP/SCOP
│   │   └── exporter.py           # Eksport CSV
│   └── ui/                       # Komponenty UI
│       └── __init__.py
├── main.py                       # Skrypt zbieracza danych
├── dashboard.py                  # Dashboard Streamlit
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
  - `database.py` - Operacje CRUD na SQLite
  - `tuya_client.py` - Komunikacja z Tuya Pulsar, deszyfrowanie AES
  - `calculator.py` - Obliczenia wydajności (COP, SCOP, energia)
  - `exporter.py` - Eksport danych do CSV
- **ui/** - Komponenty interfejsu użytkownika (w przygotowaniu)
- **db.py** - Warstwa kompatybilności dla istniejących importów

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

### Docker
```bash
docker build -t heat-pump-monitor .
docker run -p 8501:8501 heat-pump-monitor
```

## Zmienne środowiskowe

Wymagane plik `.env`:
```
TUYA_ACCESS_ID=twoj_access_id
TUYA_ACCESS_KEY=twoj_access_key
```

## Funkcje

- ✅ Pobieranie telemetrii z Tuya Pulsar (EU)
- ✅ Deszyfrowanie AES-GCM/ECB
- ✅ Filtr Deadband (redukcja szumu)
- ✅ Zapis do SQLite z indeksami
- ✅ Ręczne wpisy licznika energii
- ✅ Obliczanie COP i SCOP (CO/CWU)
- ✅ Bilans energetyczny [kWh]
- ✅ Wykrywanie cykli defrost
- ✅ Eksport danych do CSV
- ✅ Dashboard Streamlit z wykresami Plotly

## Rozwój

Projekt jest przygotowany do dalszego rozwoju:
- Dodawanie testów jednostkowych (`tests/`)
- Migracje bazy danych (Alembic)
- CI/CD (GitHub Actions)
- Alerty (Telegram, e-mail)
- Integracje smart home (Home Assistant)
