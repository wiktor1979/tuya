# TODO - Plan rozwoju projektu Heat Pump Monitor

## 1. Zaawansowane analizy efektywności
- [ ] Wykres zależności COP od temperatury zewnętrznej
- [ ] Analiza pracy grzałek elektrycznych (częstotliwość, czas pracy, wpływ na COP)
- [ ] Kalkulator kosztów eksploatacji (integracja z taryfami energetycznymi)
- [ ] Szacowanie rzeczywistego SCOP w różnych okresach grzewczych
- [ ] Analiza efektywności w funkcji obciążenia cieplnego budynku

## 2. Predykcja i inteligencja (AI/ML)
- [ ] Prognozowanie zużycia energii na podstawie danych historycznych i pogody
- [ ] Wykrywanie anomalii w pracy pompy (np. spadki wydajności, nietypowe cykle)
- [ ] Rekomendacje optymalizacyjne (np. sugerowane zmiany ustawień)
- [ ] Modelowanie zużycia w oparciu o prognozę pogody
- [ ] Automatyczne wykrywanie trendów degradacji wydajności

## 3. Integracje i automatyzacja
- [ ] Eksport danych do Home Assistant (REST API / MQTT)
- [ ] Powiadomienia (Telegram, Email, Push) w przypadku:
  - Awarii / błędów pompy
  - Spadku COP poniżej progu
  - Ekstremalnych warunków pracy
- [ ] Integracja z systemami fotowoltaicznymi (analiza nadwyżek energii)
- [ ] Webhooki dla zdarzeń krytycznych
- [ ] Integracja z Google Sheets / Excel Online

## 4. Ulepszenia wizualne i UX
- [ ] Responsywny dashboard mobilny (dostosowanie layoutu Streamlit)
- [ ] Mapa cieplna (heatmap) aktywności pompy w ciągu doby/tygodnia
- [ ] Porównania okresów (YoY - rok do roku, MoM - miesiąc do miesiąca)
- [ ] Kalkulator zwrotu z inwestycji (ROI) na podstawie rzeczywistych danych
- [ ] Tryb ciemny/jasny dla dashboardu
- [ ] Eksport raportów PDF z podsumowaniem okresu grzewczego
- [ ] Widgety do osadzenia na innych stronach (iframe)

## 5. Rozszerzenie danych pogodowych
- [ ] Pobieranie archiwalnych danych pogodowych dla pełnych sezonów grzewczych
- [ ] Wykresy korelacji z liczbą stopniodni (HDD - Heating Degree Days)
- [ ] Integracja z dodatkowymi źródłami danych pogodowych (alternatywy dla Open-Meteo)
- [ ] Prognoza pogody na 7-14 dni w kontekście planowanej pracy pompy
- [ ] Wizualizacja wpływu nasłonecznienia na pracę pompy

## 6. Ulepszenia techniczne
- [ ] Testy jednostkowe dla modułów kalkulacyjnych
- [ ] Konteneryzacja Docker dla łatwiejszego wdrożenia
- [ ] Monitoring wydajności aplikacji (logging, metryki)
- [ ] Wersjonowanie konfiguracji i backup bazy danych
- [ ] Dokumentacja API dla zewnętrznych integracji
- [ ] Multi-user support z autentykacją

## Priorytety
### Wysoki priorytet (krótkoterminowe)
1. Wykres zależności COP od temperatury zewnętrznej
2. Powiadomienia o awariach i niskim COP
3. Responsywny dashboard mobilny
4. Analiza pracy grzałek elektrycznych

### Średni priorytet (średnioterminowe)
1. Kalkulator kosztów eksploatacji
2. Integracja z Home Assistant
3. Porównania okresów (YoY/MoM)
4. Archiwalne dane pogodowe i HDD

### Niski priorytet (długoterminowe)
1. Modele ML do predykcji
2. Kalkulator ROI
3. Raporty PDF
4. Multi-user support

---
*Data utworzenia: 2025*
*Ostatnia aktualizacja: 2025*
