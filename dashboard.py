import streamlit as st
import time
import plotly.express as px
import db  # Odwołanie do spójnego pliku db.py

st.set_page_config(page_title="Telemetria Pompy Ciepła", layout="wide")

# Automatyczna inicjalizacja bazy
db.init_db()

st.title("⚡ Monitoring Pompy Ciepła i Licznika")

# Ustawienia paska bocznego
st.sidebar.header("Zakres Czasu")
time_range = st.sidebar.selectbox(
    "Wybierz okres:",
    ["Ostatnie 6 godzin", "Ostatnie 24 godziny", "Ostatnie 3 dni", "Ostatnie 7 dni"]
)

hours_map = {
    "Ostatnie 6 godzin": 6,
    "Ostatnie 24 godziny": 24,
    "Ostatnie 3 dni": 72,
    "Ostatnie 7 dni": 168
}

now = int(time.time())
start_time = now - (hours_map[time_range] * 3600)

# --- PANEL STATUSU (KPI) ---
st.subheader("📊 Aktualny Stan Pompy Ciepła")
hp_status = db.get_latest_status(db.HEAT_PUMP_DEV_ID)

if hp_status:
    col1, col2, col3, col4, col5 = st.columns(5)

    comp_freq = hp_status.get("comp_freq", 0)
    is_running = comp_freq > 0 if isinstance(comp_freq, (int, float)) else False

    col1.metric("Stan pracy", "PRACA" if is_running else "POSTÓJ", f"{comp_freq} Hz")
    
    in_t = hp_status.get('in_water_temp', None)
    out_t = hp_status.get('out_water_temp', None)
    
    col2.metric("Temp. Powrotu (In)", f"{in_t} °C" if in_t is not None else "--")
    col3.metric("Temp. Zasilania (Out)", f"{out_t} °C" if out_t is not None else "--")
    
    if isinstance(in_t, (int, float)) and isinstance(out_t, (int, float)):
        delta_t = round(out_t - in_t, 1)
    else:
        delta_t = "--"
    col4.metric("Delta T (Out - In)", f"{delta_t} °C")
    
    col5.metric("Temp. Zewnętrzna", f"{hp_status.get('amb_temp', '--')} °C")
else:
    st.warning("Brak aktualnych odczytów z pompy ciepła.")

st.divider()

# --- WYKRESY TEMPERATUR I PRACY ---
st.subheader("📈 Wykresy Czasowe Pompy Ciepła")
df_hp = db.get_pivoted_telemetry(db.HEAT_PUMP_DEV_ID, start_time, now)

if not df_hp.empty:
    # 1. Wykres temperatur
    temp_cols = [c for c in ["in_water_temp", "out_water_temp", "tank_temp", "amb_temp"] if c in df_hp.columns]
    if temp_cols:
        fig_temp = px.line(df_hp, x=df_hp.index, y=temp_cols, title="Temperatury (°C)")
        fig_temp.update_layout(hovermode="x unified", xaxis_title="Czas", yaxis_title="°C")
        st.plotly_chart(fig_temp, use_container_width=True)

    # 2. Wykres sprężarki
    if "comp_freq" in df_hp.columns:
        fig_freq = px.area(df_hp, x=df_hp.index, y="comp_freq", title="Częstotliwość Sprężarki (Hz)")
        fig_freq.update_layout(hovermode="x unified", xaxis_title="Czas", yaxis_title="Hz")
        st.plotly_chart(fig_freq, use_container_width=True)
else:
    st.info("Brak danych pompy ciepła w wybranym przedziale czasowym.")

st.divider()

# --- DANIE Z LICZNIKA ENERGII ---
st.subheader("⚡ Odczyty Licznika Energii")
df_meter = db.get_pivoted_telemetry(db.METER_DEV_ID, start_time, now)

if not df_meter.empty:
    st.line_chart(df_meter)
else:
    st.info("Brak danych z licznika energii w wybranym przedziale czasowym.")
