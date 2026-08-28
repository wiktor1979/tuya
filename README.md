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
│   │   ├── data_loader.py        # Ładowanie i przetwarzanie danych dla dashboardu
│   │   ├── tuya_client.py        # Klient Tuya Pulsar z filtrem deadband
│   │   ├── exporter.py           # Eksport CSV
│   │   └── analytics.py          # Zaawansowana diagnostyka i analiza
│   └── ui/                       # Komponenty UI dashboardu
│       ├── __init__.py
│       ├── styles.py             # CSS i stałe wizualne (re-export PARAM_INFO z config)
│       ├── sidebar.py            # Panel boczny z ustawieniami
│       ├── tab_main.py           # Zakładka: Panel Główny
│       ├── tab_scop.py           # Zakładka: Bilans Energetyczny & SCOP
│       ├── tab_diagnostics.py    # Zakładka: Diagnostyka Pompy
│       ├── tab_weather.py        # Zakładka: Kontekst Pogodowy
│       ├── tab_meter.py          # Zakładka: Fizyczny Licznik Energii
│       ├── tab_export.py         # Zakładka: Eksport Danych
│       └── tab_heating_curve.py  # Zakładka: Doradca Krzywej Grzewczej
├── pages/                        # Podstrony Streamlit (multipage app)
│   └── 2_Analiza_Parametrow.py   # Analiza Parametrów: COP, Hydraulika, Sprężarka, Defrost
├── main.py                       # Skrypt zbieracza danych (z wątkiem pogodowym)
├── Panel.py                      # Dashboard Streamlit — strona główna (orkiestrator)
├── db.py                         # Warstwa kompatybilności wstecznej
├── requirements.txt              # Zależności Python
├── Dockerfile                    # Kontener Docker
├── fly.toml                      # Konfiguracja Fly.io
├── start.sh                      # Skrypt startowy (produkcja)
└── start_local.bat               # Skrypt startowy (lokalnie: pobiera bazę z Fly.io + Streamlit)
```

## Architektura

Projekt został poddany refaktoryzacji zgodnie z zasadą pojedynczej odpowiedzialności (SRP):

- **config.py** - Centralne miejsce na zmienne środowiskowe, stałe konfiguracji, metadane parametrów (PARAM_INFO)
- **models/** - Definicje struktur danych (dataclasses)
- **services/** - Logika biznesowa podzielona na niezależne moduły:
  - `database.py` - Operacje CRUD na SQLite z connection pooling, trybem WAL i optymalnymi indeksami
  - `data_loader.py` - Zapytania SQL i przetwarzanie danych dla dashboardu (COP, SCOP nominalny/realny, energia, straty defrostu, statystyki dzienne)
  - `tuya_client.py` - Komunikacja z Tuya Pulsar, deszyfrowanie AES-GCM/ECB, filtr deadband z dynamiczną histerezą
  - `exporter.py` - Eksport danych do CSV
  - `analytics.py` - Zaawansowana diagnostyka: wykrywanie cykli krótkich, analiza inwertera, szacowanie COP, korelacja pogodowa
- **ui/** - Modularny interfejs użytkownika (każda zakładka to osobny moduł):
  - `styles.py` - CSS, stałe wizualne (re-export PARAM_INFO i get_param_label z config.py)
  - `sidebar.py` - Panel boczny z konfiguracją (zakres czasu, kalibracja, koszty)
  - `tab_main.py` - Bieżące metryki i wykresy parametrów
  - `tab_scop.py` - Bilans energetyczny, SCOP nominalny vs realny (z defrostem), straty defrostu, statystyki dzienne
  - `tab_diagnostics.py` - Diagnostyka: cykle krótkie, inwerter, ostrzeżenia
  - `tab_weather.py` - Korelacja pogodowa, porównanie źródeł temperatury
  - `tab_meter.py` - Ręczne odczyty fizycznego licznika energii
  - `tab_export.py` - Eksport danych do CSV
  - `tab_heating_curve.py` - Doradca krzywej grzewczej: analiza duty cycle, rekomendacje zmiany nastaw
- **dashboard.py** - Lekki orkiestrator (~140 linii): ładuje dane, konfiguruje stronę, deleguje do zakładek. Auto-odświeżanie z countdown (60s pompa aktywna / 300s idle)
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

### Dynamiczna histereza deadband

Filtr zapisu do bazy (`DeadbandFilter`) redukuje liczbę rekordów bez utraty istotnych zmian:

- **Dwa progi na parametr**: `active` (sprężarka pracuje) i `idle` (sprężarka stoi) — wyższy próg w idle redukuje szum przy zachowaniu dokładności w trybie aktywnym
- **Heartbeat**: Wymusza zapis co 5 min nawet bez zmian (gwarantuje ciągłość danych)
- **Konfiguracja w `config.py`**: Np. `out_water_temp: active=0.2°C, idle=0.5°C`, `ac_vol: active=2V, idle=3V`
- **~300 rekordów/h** przy typowej pracy (zbalansowane między dokładnością a rozmiarem bazy)

### SCOP realny z defrostem

Algorytm oblicza dwa warianty SCOP:

- **SCOP nominalny**: Standardowe obliczenie E_th/E_el z wykluczeniem okresów defrostu (COP=NaN)
- **SCOP realny**: Uwzględnia straty defrostu — ujemny P_th (ciepło zabrane z obiegu) obniża bilans cieplny

Podczas defrostu (`defrost=True`):
- Cykl chłodniczy się odwraca → ΔT < 0 → P_th < 0
- Sprężarka nadal pobiera prąd (P_el > 0)
- SCOP realny = (E_th_nominalny + E_th_defrost) / E_el_total

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
streamlit run Panel.py --server.port 8501
```

### Uruchomienie lokalne (Windows)
```bash
start_local.bat
```
Skrypt pyta czy pobrać bazę z Fly.io, uruchamia migrację struktury i startuje Streamlit.

Dashboard zawiera 6 zakładek:
1. **Panel Główny** - Podstawowe metryki i status systemu
2. **Bilans Energetyczny & SCOP** - SCOP nominalny vs realny (z defrostem), straty energetyczne defrostu, bilans energii CO/CWU, tabela dzienna
3. **Diagnostyka Pompy** - Zaawansowana analiza: cykle krótkie, praca inwertera, czasy trybów, rekomendacje
4. **Kontekst Pogodowy** - Korelacja temperatury zewnętrznej z pracą pompy, wykresy zależności
5. **Fizyczny Licznik Energii** - Zarządzanie ręcznymi odczytami licznika
6. **Eksport Danych** - Eksport danych do CSV

### Podstrona: Analiza Parametrów (multipage)

Osobna podstrona dostępna z nawigacji bocznej, z 5 zakładkami opartymi o parametry monitoringowe wg kategorii:

1. **🔋 Wydajność COP** - COP chwilowy w czasie (z progami referencyjnymi i progiem opłacalności SCOP 3.1), SCOP realny z defrostem, scatter COP vs temp. zewnętrzna (trend lowess), SCOP dzienny (realny vs nominalny) z kolorowaniem wg progu opłacalności, alerty spadku wydajności
2. **💧 Hydraulika i ΔT** - Delta T zasilanie-powrót z zakresami normy (3-7°C CO, 5-10°C CWU), wykres przepływu, korelacja ΔT vs przepływ, alerty hydrauliczne
3. **⚙️ Sprężarka i Taktowanie** - Timeline ON/OFF z czasami cykli, histogram długości cykli (progi 30/60 min), starty/dobę (próg 15/20), modulacja częstotliwości
4. **❄️ Defrost i Obieg Chłodniczy** - Timeline defrostów, scatter defrost vs temp. zewn., odstępy między cyklami (próg 45 min), zawór EEV (m_eev/a_eev), wentylator DC Fan 1
5. **📈 Krzywa Grzewcza** - Doradca krzywej grzewczej: formularz nastaw (-10°C/+20°C), duty cycle sprężarki per bin temperaturowy, wykrywanie przyczyny zatrzymań (termostat vs pompa), korelacja nasłonecznienia, rekomendacja zmiany lewego/prawego końca krzywej

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
- ✅ Obliczanie COP i SCOP (CO/CWU) — nominalny i realny (z defrostem)
- ✅ Bilans energetyczny [kWh] z wyodrębnieniem strat defrostu
- ✅ Próg opłacalności SCOP 3.1 — wizualizacja na wykresach i KPI
- ✅ Wykrywanie cykli defrost i obliczanie strat cieplnych/elektrycznych
- ✅ Auto-odświeżanie dashboardu z countdown (60s aktywna / 300s idle)
- ✅ Eksport danych do CSV
- ✅ Dashboard Streamlit z wykresami Plotly
- ✅ Multipage Streamlit — oddzielna podstrona "Analiza Parametrów"

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
- 🌤️ **Open-Meteo API** - Automatyczne pobieranie danych co godzinę (temperatura, wilgotność, wiatr, opady, nasłonecznienie)
- 🌤️ **Dane historyczne** - Temperatura, opady, zachmurzenie, wiatr, radiacja słoneczna (direct + diffuse)
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
