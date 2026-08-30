"""Podstrona: Baza Wiedzy — opisy i analizy dotyczące wydajności pompy ciepła."""
import streamlit as st

from app.ui.styles import inject_css
from app.ui.sidebar import render_sidebar

# --- KONFIGURACJA STRONY ---
st.set_page_config(page_title="Baza Wiedzy — Pompa Ciepła", layout="wide", page_icon="📚")
inject_css()

st.markdown(
    '<h3 style="margin:0;padding:0.2rem 0;">📚 Baza Wiedzy</h3>',
    unsafe_allow_html=True,
)

# --- PANEL BOCZNY ---
settings = render_sidebar()

# --- TREŚĆ ---

st.info("""
**Analiza opłacalności pompy ciepła vs kocioł gazowy — Łódź**

Dla instalacji hybrydowej w Łodzi analiza liczby dni, w których praca pompy ciepła będzie tańsza od kotła gazowego, opiera się na granicznym progu opłacalności COP = 3,07 oraz historycznym rozkładzie temperatur w sezonie grzewczym.

Większość sezonu grzewczego w Łodzi (trwającego średnio ok. 200–210 dni) przypada na łagodne temperatury, co sprzyja pracy pompy ciepła.

---

**Rozkład dni grzewczych w Łodzi według temperatur**

Na podstawie wieloletnich danych meteorologicznych średni rozkład temperatur w sezonie grzewczym wygląda następująco:

- **Powyżej +3°C** (okresy przejściowe — jesień, wiosna): ok. 135–145 dni (ok. 65–70% sezonu)
- **Od 0°C do +3°C**: ok. 30–35 dni (ok. 15% sezonu)
- **Poniżej 0°C** (mrozy): ok. 30–40 dni (ok. 15–20% sezonu)

---

**Podział dni pracy: Pompa ciepła vs Kocioł gazowy**

Liczba dni, w których dany agregat jest tańszy, zależy bezpośrednio od temperatury zasilania instalacji c.o.:

🔵 **Instalacja podłogowa (zasilanie 30–35°C):**
- Pompa tańsza (COP > 3,07): przy temperaturze zewnętrznej powyżej **-3°C**
- Czas pracy pompy: ok. **185–195 dni** w roku (ok. 90% sezonu)
- Czas pracy kotła: ok. **15–20 dni** w roku (tylko podczas fal mrozów poniżej -3°C)

🟡 **Instalacja mieszana / średniotemperaturowa (zasilanie 40–45°C):**
- Pompa tańsza (COP > 3,07): przy temperaturze zewnętrznej powyżej **+2°C do +3°C**
- Czas pracy pompy: ok. **140–150 dni** w roku (ok. 70% sezonu)
- Czas pracy kotła: ok. **55–65 dni** w roku (głównie w najzimniejszych miesiącach)

🔴 **Instalacja grzejnikowa (zasilanie 50–55°C):**
- Pompa tańsza (COP > 3,07): przy temperaturze zewnętrznej powyżej **+5°C**
- Czas pracy pompy: ok. **110–120 dni** w roku (ok. 55% sezonu)
- Czas pracy kotła: ok. **85–95 dni** w roku

---

**Kluczowy wniosek ekologiczno-ekonomiczny**

Warto pamiętać o różnicy między liczbą dni a realnym zużyciem energii:

- W instalacji mieszanej kocioł pracujący przez około 30% dni w roku pokrywa aż **50–60% rocznego zapotrzebowania na ciepło**, ponieważ zapotrzebowanie budynku na moc rośnie liniowo wraz ze spadkiem temperatury.
- Pompa ciepła idealnie sprawdza się w okresach przejściowych, pracując przez większość dni w roku na niskim obciążeniu.
- Dla automatyki sterującej w Łodzi optymalny punkt przełączenia źródła (bivalencji) przy instalacji mieszanej warto ustawić w okolicach **+2°C**.

---

**⚠️ Wpływ oblodzenia na wydajność**

Przy temperaturach bliskich 0°C (zakres od -3°C do +3°C) i dużej wilgotności powietrza — co jest częste w Polsce środkowej — dochodzi do intensywnego oblodzenia parownika pompy ciepła. Wymusza to częste cykle odszraniania (defrost), podczas których:

- Pompa **odwraca obieg** — zamiast grzać dom, pobiera ciepło z instalacji CO żeby roztopić lód na parowniku
- Energia elektryczna jest zużywana, ale **ciepło nie trafia do budynku** (a nawet jest z niego zabierane)
- SCOP realny znacząco spada — straty defrostu mogą obniżyć SCOP o **0.3–0.8** w porównaniu z SCOP nominalnym

To szczególnie istotne w Łodzi, gdzie zakres 0°C do +3°C stanowi ok. 15% sezonu grzewczego (30–35 dni), ale ze względu na częste defrosty te dni mogą generować **nieproporcjonalnie wysokie koszty** eksploatacji.
""")
