import sqlite3
from datetime import datetime, date, time as dtime, timedelta
import pandas as pd
import numpy as np
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
from db import (
    DB_FILE, 
    HEAT_PUMP_DEV_ID, 
    MANUAL_METER_DEV_ID,
    save_manual_energy_reading, 
    update_manual_energy_reading, 
    delete_manual_energy_reading
)
from app.services.analytics import (
    detect_short_cycles,
    analyze_inverter_performance,
    analyze_mode_runtime,
    correlate_weather_performance,
    generate_diagnostic_report
)
from app.services.database import get_db_connection, get_weather_data

# --- KONFIGURACJA STRONY ---
st.set_page_config(page_title="Monitor Pompy Ciepła", layout="wide", page_icon="🔥")

st.markdown("""
<style>
/* Wygląd kafelków metryk */
[data-testid="stMetric"] {
    background-color: #1E1E1E;
    border: 1px solid #333;
    border-radius: 10px;
    padding: 15px;
    box-shadow: 2px 2px 10px rgba(0,0,0,0.3);
}

/* Jasny kolor tekstu dla kafelków */
[data-testid="stMetricValue"] {
    color: #FFFFFF !important;
}

[data-testid="stMetricLabel"] {
    color: #CCCCCC !important;
}

[data-testid="stMetricDelta"] {
    color: #AAAAAA !important;
}

@media (max-width: 768px) {
    [data-testid="stHorizontalBlock"]:has([data-testid="stMetric"]) {
        display: grid !important;
        grid-template-columns: repeat(2, 1fr) !important;
        gap: 10px !important;
    }
    [data-testid="stMetricValue"] {
        font-size: 1.5rem !important;
    }
}
</style>
""", unsafe_allow_html=True)

st.title("🔥 Panel Monitorowania i Diagnostyki Pompy Ciepła")

# --- SŁOWNIK METADANYCH PARAMETRÓW POMPY ---
PARAM_INFO = {
    "in_water_temp": {"label": "Powrót CO", "desc": "Temperatura wody powracającej z instalacji grzewczej"},
    "out_water_temp": {"label": "Zasilanie CO", "desc": "Temperatura wody wychodzącej na dom"},
    "tank_temp": {"label": "Woda CWU", "desc": "Temperatura wody w zasobniku ciepłej wody użytkowej"},
    "amb_temp": {"label": "Temp. zewnętrzna", "desc": "Temperatura powietrza na zewnątrz budynku"},
    "disc_temp": {"label": "Tłoczenie sprężarki", "desc": "Temperatura gazu na wylocie/tłoczeniu sprężarki (Discharge)"},
    "back_temp": {"label": "Powrót do sprężarki", "desc": "Temperatura czynnika na powrocie do sprężarki (Suction)"},
    "tidr": {"label": "Temp. ssania", "desc": "Temperatura czujnika ssania / wymiennika chłodniczego"},
    "heat_temp_set": {"label": "Nastawa CO", "desc": "Docelowa zadana temperatura dla trybu ogrzewania CO"},
    "cool_temp_set": {"label": "Nastawa Chłodzenia", "desc": "Docelowa zadana temperatura dla trybu chłodzenia"},
    "hot_water_temp_set": {"label": "Nastawa CWU", "desc": "Docelowa zadana temperatura dla wody użytkowej"},
    "ac_vol": {"label": "Napięcie AC", "desc": "Napięcie zasilania sieciowego AC podawane do jednostki"},
    "ac_curr": {"label": "Prąd AC", "desc": "Natężenie prądu pobieranego przez urządzenie"},
    "comp_freq": {"label": "Częstotliwość sprężarki", "desc": "Aktualna częstotliwość pracy sprężarki (Hz)"},
    "flow_rate": {"label": "Przepływ", "desc": "Przepływ wody w obiegu hydraulicznym"},
    "m_eev": {"label": "Zawór EEV główny", "desc": "Pozycja otwarcia głównego elektronicznego zaworu rozprężnego"},
    "valve": {"label": "Zawór 3-drożny", "desc": "Stan zaworu przełączającego (0 = CO, 1 = CWU)"},
    "defrost": {"label": "Odszranianie", "desc": "Cykl automatycznego odszraniania parownika"}
}

def get_param_label(code: str) -> str:
    info = PARAM_INFO.get(code)
    return f"{info['label']} ({code})" if info else code

# --- PANEL BOCZNY ---
st.sidebar.header("⏱️ Zakres danych")
time_range_map = {
    "Ostatnie 6 godzin": 6,
    "1 dzień": 24,
    "Ostatnie 3 dni": 72,
    "Ostatnie 7 dni": 168,
    "Ostatnie 30 dni": 720
}
selected_range = st.sidebar.selectbox("Wybierz zakres czasu:", list(time_range_map.keys()), index=1)
hours_back = time_range_map[selected_range]

st.sidebar.header("📊 Optymalizacja wykresów")
resample_map = {
    "Brak (Surowe dane)": None,
    "Co 1 minuta": "1min",
    "Co 5 minut": "5min",
    "Co 15 minut": "15min"
}
selected_resample = st.sidebar.selectbox("Agregacja punktów:", list(resample_map.keys()), index=1)
resample_rule = resample_map[selected_resample]

# Sekcje zwinięte (domyślnie ukryte)
with st.sidebar.expander("⚙️ Kalkulator COP i Kalibracja"):
    cos_phi = st.slider("Współczynnik mocy (cos φ)", 0.80, 1.00, 1.00, 0.01)
    st.subheader("🛠️ Kalibracja strat mocy")
    standby_power_w = st.number_input("Pobór w spoczynku (elektronika) [W]", min_value=0, max_value=100, value=15, step=5)
    active_power_w = st.number_input("Pobór pracy (wentylator, pompa obieg.) [W]", min_value=0, max_value=300, value=130, step=10)

with st.sidebar.expander("🕐 Korekta czasu i Koszty"):
    time_offset_hours = st.slider(
        "Przesunięcie czasu (godziny)",
        min_value=-12,
        max_value=12,
        value=2,
        step=1,
        help="Dodaje przesunięcie do czasu serwera, aby wyświetlać prawidłowy czas lokalny"
    )
    st.subheader("💰 Cena energii elektrycznej")
    electricity_price = st.number_input(
        "Cena prądu [zł/kWh]",
        min_value=0.0,
        max_value=5.0,
        value=1.00,
        step=0.01,
        help="Cena energii elektrycznej używana do obliczeń kosztów eksploatacji pompy ciepła"
    )

def apply_time_correction(df: pd.DataFrame, offset_hours: int) -> pd.DataFrame:
    """Dodaje przesunięcie czasu do kolumny 'czas' w DataFrame."""
    if df is None or df.empty or 'czas' not in df.columns:
        return df
    df_corrected = df.copy()
    df_corrected['czas'] = pd.to_datetime(df_corrected['czas']) + pd.Timedelta(hours=offset_hours)
    return df_corrected

def load_pump_data(hours: int, all_time: bool = False, is_today: bool = False) -> pd.DataFrame:
    """Ładuje dane wyłącznie ze sterownika pompy ciepła."""
    conn = sqlite3.connect(DB_FILE)
    if all_time:
        query = f"""
            SELECT 
                datetime(timestamp, 'unixepoch', 'localtime') as czas,
                code, val_num, val_str
            FROM telemetry
            WHERE device_id = '{HEAT_PUMP_DEV_ID}'
            ORDER BY timestamp ASC
        """
    elif is_today:
        # Pobierz dane od 00:00 dzisiaj (czas lokalny)
        query = f"""
            SELECT 
                datetime(timestamp, 'unixepoch', 'localtime') as czas,
                code, val_num, val_str
            FROM telemetry
            WHERE device_id = '{HEAT_PUMP_DEV_ID}'
              AND date(timestamp, 'unixepoch', 'localtime') = date('now', 'localtime')
            ORDER BY timestamp ASC
        """
    else:
        query = f"""
            SELECT 
                datetime(timestamp, 'unixepoch', 'localtime') as czas,
                code, val_num, val_str
            FROM telemetry
            WHERE device_id = '{HEAT_PUMP_DEV_ID}'
              AND timestamp >= strftime('%s', 'now', '-{hours} hours')
            ORDER BY timestamp ASC
        """
    df_data = pd.read_sql_query(query, conn)
    conn.close()
    return df_data

def load_manual_readings() -> pd.DataFrame:
    """Ładuje całą historię odczytów z licznika ręcznego."""
    conn = sqlite3.connect(DB_FILE)
    query = f"""
        SELECT 
            id,
            timestamp,
            datetime(timestamp, 'unixepoch', 'localtime') as czas,
            val_num as stan_kwh
        FROM telemetry
        WHERE device_id = '{MANUAL_METER_DEV_ID}' AND code = 'energy_kwh'
        ORDER BY timestamp ASC
    """
    df_man = pd.read_sql_query(query, conn)
    conn.close()
    if not df_man.empty and 'czas' in df_man.columns:
        df_man["czas"] = pd.to_datetime(df_man["czas"])
        df_man = apply_time_correction(df_man, time_offset_hours)
    return df_man

if st.button("🔄 Odśwież dane"):
    st.rerun()

# Sprawdź czy wybrano zakres "1 dzień" - wtedy pobierz dane od 00:00 do teraz
is_today_range = (selected_range == "1 dzień")
df = load_pump_data(hours_back, is_today=is_today_range)
df_all_time = load_pump_data(hours_back, all_time=True)

# --- PRZETWARZANIE TELEMETRII POMPY ---
if not df.empty:
    df["val_combined"] = df["val_num"]
    bool_map = {
        "True": 1.0, "true": 1.0, "1": 1.0, "1.0": 1.0,
        "False": 0.0, "false": 0.0, "0": 0.0, "0.0": 0.0
    }
    mask_str = df["val_combined"].isna() & df["val_str"].notna()
    df.loc[mask_str, "val_combined"] = df.loc[mask_str, "val_str"].map(bool_map)

    df_pivot = df.pivot_table(index="czas", columns="code", values="val_combined", aggfunc="first").reset_index()
    df_pivot["czas"] = pd.to_datetime(df_pivot["czas"])
    df_pivot = apply_time_correction(df_pivot, time_offset_hours)
    df_pivot = df_pivot.sort_values("czas")

    needed_cols = ["out_water_temp", "in_water_temp", "flow_rate", "ac_vol", "ac_curr", "comp_freq", "disc_temp", "amb_temp", "valve", "heat_temp_set", "defrost"]
    for col in needed_cols:
        if col not in df_pivot.columns:
            df_pivot[col] = np.nan
        else:
            df_pivot[col] = df_pivot[col].ffill()

    df_pivot["valve"] = df_pivot["valve"].fillna(0).astype(float)

    if resample_rule:
        df_pivot = df_pivot.set_index("czas").resample(resample_rule).agg({
            "out_water_temp": "mean",
            "in_water_temp": "mean",
            "flow_rate": "mean",
            "ac_vol": "mean",
            "ac_curr": "mean",
            "comp_freq": "mean",
            "disc_temp": "mean",
            "amb_temp": "mean",
            "heat_temp_set": "last",
            "valve": "mean",
            "defrost": "max"
        }).reset_index()
        for col in needed_cols:
            df_pivot[col] = df_pivot[col].ffill()

    df_pivot["Tryb"] = np.where(df_pivot["valve"] >= 0.5, "CWU", "CO")

    # Obliczenia fizyczne
    curr_a = df_pivot["ac_curr"] / 10
    df_pivot["flow_m3h"] = df_pivot["flow_rate"] / 10.0
    df_pivot["delta_t"] = df_pivot["out_water_temp"] - df_pivot["in_water_temp"]

    raw_p_el_kw = (df_pivot["ac_vol"] * curr_a * cos_phi) / 1000.0
    is_active = raw_p_el_kw > 0.1
    correction_kw = (standby_power_w / 1000.0) + np.where(is_active, active_power_w / 1000.0, 0.0)
    
    df_pivot["P_el_kw"] = raw_p_el_kw + correction_kw
    df_pivot["P_th_kw"] = (df_pivot["flow_m3h"] * 4.186 * df_pivot["delta_t"]) / 3.6
    
    df_pivot["COP"] = np.where(is_active, df_pivot["P_th_kw"] / df_pivot["P_el_kw"], np.nan)
    invalid_mask = (df_pivot["P_th_kw"] <= 0) | (df_pivot["COP"] < 0.5) | (df_pivot["COP"] > 10.0)
    df_pivot.loc[invalid_mask, "COP"] = np.nan
    df_pivot.loc[df_pivot["P_th_kw"] < 0, "P_th_kw"] = 0.0

    df_pivot["dt_hours"] = df_pivot["czas"].diff().dt.total_seconds().fillna(0) / 3600.0
    
    if resample_rule:
        df_pivot["E_th_kwh"] = df_pivot["P_th_kw"] * df_pivot["dt_hours"]
        df_pivot["E_el_kwh"] = df_pivot["P_el_kw"] * df_pivot["dt_hours"]
    else:
        df_pivot["E_th_kwh"] = df_pivot["P_th_kw"].shift(1).fillna(0) * df_pivot["dt_hours"]
        df_pivot["E_el_kwh"] = df_pivot["P_el_kw"].shift(1).fillna(0) * df_pivot["dt_hours"]

    co_mask = (df_pivot["Tryb"] == "CO") & (~df_pivot["COP"].isna())
    cwu_mask = (df_pivot["Tryb"] == "CWU") & (~df_pivot["COP"].isna())

    e_th_co = df_pivot.loc[co_mask, "E_th_kwh"].sum()
    e_el_co = df_pivot.loc[co_mask, "E_el_kwh"].sum()
    scop_co = (e_th_co / e_el_co) if e_el_co > 0 else 0.0

    e_th_cwu = df_pivot.loc[cwu_mask, "E_th_kwh"].sum()
    e_el_cwu = df_pivot.loc[cwu_mask, "E_el_kwh"].sum()
    scop_cwu = (e_th_cwu / e_el_cwu) if e_el_cwu > 0 else 0.0

    e_th_total = e_th_co + e_th_cwu
    e_el_total = e_el_co + e_el_cwu
    scop_total = (e_th_total / e_el_total) if e_el_total > 0 else 0.0

    # Wykrywanie cykli defrost
    df_pivot["defrost_num"] = df_pivot["defrost"].fillna(0).apply(lambda x: 1 if x else 0)
    df_pivot["defrost_start"] = ((df_pivot["defrost_num"] == 1) & (df_pivot["defrost_num"].shift(1, fill_value=0) == 0)).astype(int)

    # Wykrywanie startów i czasu pracy sprężarki
    # Kompresor pracuje gdy comp_freq > 5 Hz
    df_pivot["comp_on"] = (df_pivot["comp_freq"] > 5).astype(int)
    # Wykryj moment startu: zmiana z 0 na 1
    df_pivot["comp_start"] = ((df_pivot["comp_on"] == 1) & (df_pivot["comp_on"].shift(1, fill_value=0) == 0)).astype(int)
    
    # Grupowanie okresów pracy - każdy start tworzy nową grupę
    df_pivot["work_period"] = df_pivot["comp_start"].cumsum()
    
    # Oblicz czas trwania każdego okresu pracy w godzinach
    # Dla każdego wiersza obliczamy dt_hours (różnica czasu od poprzedniego pomiaru)
    # Następnie sumujemy dt_hours w ramach każdego okresu pracy
    df_pivot["dt_hours_work"] = np.where(df_pivot["comp_on"] == 1, df_pivot["dt_hours"], 0.0)
    
    # Agregacja dzienna dla pompy
    df_pivot["dzień"] = df_pivot["czas"].dt.date
    df_pivot["E_el_co_row"] = np.where(df_pivot["Tryb"] == "CO", df_pivot["E_el_kwh"], 0.0)
    df_pivot["E_el_cwu_row"] = np.where(df_pivot["Tryb"] == "CWU", df_pivot["E_el_kwh"], 0.0)
    df_pivot["E_th_co_row"] = np.where(df_pivot["Tryb"] == "CO", df_pivot["E_th_kwh"], 0.0)
    df_pivot["E_th_cwu_row"] = np.where(df_pivot["Tryb"] == "CWU", df_pivot["E_th_kwh"], 0.0)

    daily_df = df_pivot.groupby("dzień").agg({
        "E_el_co_row": "sum",
        "E_el_cwu_row": "sum",
        "E_th_co_row": "sum",
        "E_th_cwu_row": "sum",
        "amb_temp": "mean",
        "defrost_start": "sum",
        "comp_start": "sum",  # liczba startów sprężarki
        "dt_hours_work": "sum"  # całkowity czas pracy sprężarki w godzinach
    }).reset_index()
    
    # Korekta czasu dla kolumny 'dzień' (pochodzącej z daty)
    if not daily_df.empty and 'dzień' in daily_df.columns:
        daily_df['dzień'] = pd.to_datetime(daily_df['dzień']).dt.date + pd.Timedelta(days=1 if time_offset_hours >= 12 else 0)
    
    daily_df["E_el_total"] = daily_df["E_el_co_row"] + daily_df["E_el_cwu_row"]
    daily_df["E_th_total"] = daily_df["E_th_co_row"] + daily_df["E_th_cwu_row"]
    daily_df["SCOP_dzienny"] = np.where(daily_df["E_el_total"] > 0, daily_df["E_th_total"] / daily_df["E_el_total"], np.nan)

    num_days = max(len(daily_df), 1)
    avg_daily_el_co = daily_df["E_el_co_row"].sum() / num_days
    avg_daily_el_cwu = daily_df["E_el_cwu_row"].sum() / num_days
    avg_amb_temp = df_pivot["amb_temp"].mean()
    total_defrosts = int(daily_df["defrost_start"].sum())
    total_comp_starts = int(daily_df["comp_start"].sum())
    total_work_hours = daily_df["dt_hours_work"].sum()
    avg_work_time_per_start = (total_work_hours / total_comp_starts * 60) if total_comp_starts > 0 else 0.0  # w minutach
    
    # Agregacja dzienna dla wszystkich danych (do tabeli niezależnej od zakresu)
    df_all_time_processed = df_all_time.copy()
    if not df_all_time_processed.empty:
        df_all_time_processed["val_combined"] = df_all_time_processed["val_num"]
        mask_na = df_all_time_processed["val_combined"].isna() & df_all_time_processed["val_str"].notna()
        df_all_time_processed.loc[mask_na, "val_combined"] = df_all_time_processed.loc[mask_na, "val_str"].map(bool_map)
        
        df_all_pivot = df_all_time_processed.pivot_table(index="czas", columns="code", values="val_combined", aggfunc="first").reset_index()
        df_all_pivot["czas"] = pd.to_datetime(df_all_pivot["czas"])
        df_all_pivot = apply_time_correction(df_all_pivot, time_offset_hours)
        df_all_pivot = df_all_pivot.sort_values("czas")
        
        for col in needed_cols:
            if col not in df_all_pivot.columns:
                df_all_pivot[col] = np.nan
            else:
                df_all_pivot[col] = df_all_pivot[col].ffill()
        
        df_all_pivot["valve"] = df_all_pivot["valve"].fillna(0).astype(float)
        df_all_pivot["Tryb"] = np.where(df_all_pivot["valve"] >= 0.5, "CWU", "CO")
        
        curr_a_all = df_all_pivot["ac_curr"] / 10
        df_all_pivot["flow_m3h"] = df_all_pivot["flow_rate"] / 10.0
        df_all_pivot["delta_t"] = df_all_pivot["out_water_temp"] - df_all_pivot["in_water_temp"]
        
        raw_p_el_kw_all = (df_all_pivot["ac_vol"] * curr_a_all * cos_phi) / 1000.0
        is_active_all = raw_p_el_kw_all > 0.1
        correction_kw_all = (standby_power_w / 1000.0) + np.where(is_active_all, active_power_w / 1000.0, 0.0)
        
        df_all_pivot["P_el_kw"] = raw_p_el_kw_all + correction_kw_all
        df_all_pivot["P_th_kw"] = (df_all_pivot["flow_m3h"] * 4.186 * df_all_pivot["delta_t"]) / 3.6
        
        df_all_pivot["dt_hours"] = df_all_pivot["czas"].diff().dt.total_seconds().fillna(0) / 3600.0
        df_all_pivot["E_el_kwh"] = df_all_pivot["P_el_kw"].shift(1).fillna(0) * df_all_pivot["dt_hours"]
        
        # Wykrywanie startów i czasu pracy sprężarki dla danych historycznych
        df_all_pivot["comp_on"] = (df_all_pivot["comp_freq"] > 5).astype(int)
        df_all_pivot["comp_start"] = ((df_all_pivot["comp_on"] == 1) & (df_all_pivot["comp_on"].shift(1, fill_value=0) == 0)).astype(int)
        df_all_pivot["dt_hours_work"] = np.where(df_all_pivot["comp_on"] == 1, df_all_pivot["dt_hours"], 0.0)
        
        df_all_pivot["dzień"] = df_all_pivot["czas"].dt.date
        df_all_pivot["E_el_co_row"] = np.where(df_all_pivot["Tryb"] == "CO", df_all_pivot["E_el_kwh"], 0.0)
        df_all_pivot["E_el_cwu_row"] = np.where(df_all_pivot["Tryb"] == "CWU", df_all_pivot["E_el_kwh"], 0.0)
        df_all_pivot["E_th_co_row"] = np.where(df_all_pivot["Tryb"] == "CO", df_all_pivot["P_th_kw"] * df_all_pivot["dt_hours"], 0.0)
        df_all_pivot["E_th_cwu_row"] = np.where(df_all_pivot["Tryb"] == "CWU", df_all_pivot["P_th_kw"] * df_all_pivot["dt_hours"], 0.0)
        df_all_pivot["defrost_num"] = df_all_pivot["defrost"].fillna(0).apply(lambda x: 1 if x else 0)
        df_all_pivot["defrost_start"] = ((df_all_pivot["defrost_num"] == 1) & (df_all_pivot["defrost_num"].shift(1, fill_value=0) == 0)).astype(int)
        
        daily_df_all = df_all_pivot.groupby("dzień").agg({
            "E_el_co_row": "sum",
            "E_el_cwu_row": "sum",
            "E_th_co_row": "sum",
            "E_th_cwu_row": "sum",
            "amb_temp": "mean",
            "defrost_start": "sum",
            "comp_start": "sum",
            "dt_hours_work": "sum"
        }).reset_index()
        
        # Korekta czasu dla kolumny 'dzień' (pochodzącej z daty)
        if not daily_df_all.empty and 'dzień' in daily_df_all.columns:
            daily_df_all['dzień'] = pd.to_datetime(daily_df_all['dzień']).dt.date + pd.Timedelta(days=1 if time_offset_hours >= 12 else 0)
        
        daily_df_all["E_el_total"] = daily_df_all["E_el_co_row"] + daily_df_all["E_el_cwu_row"]
        daily_df_all["E_th_total"] = daily_df_all["E_th_co_row"] + daily_df_all["E_th_cwu_row"]
        daily_df_all["SCOP_dzienny"] = np.where(daily_df_all["E_el_total"] > 0, daily_df_all["E_th_total"] / daily_df_all["E_el_total"], np.nan)
    else:
        daily_df_all = pd.DataFrame(columns=["dzień", "E_el_co_row", "E_el_cwu_row", "E_el_total", "amb_temp", "defrost_start", "comp_start", "dt_hours_work"])
else:
    df_pivot = pd.DataFrame()
    daily_df = pd.DataFrame(columns=["dzień", "E_el_total"])
    daily_df_all = pd.DataFrame(columns=["dzień", "E_el_co_row", "E_el_cwu_row", "E_el_total", "amb_temp", "defrost_start", "comp_start", "dt_hours_work"])
    e_el_co = e_el_cwu = e_th_co = e_th_cwu = e_th_total = e_el_total = scop_total = scop_co = scop_cwu = 0.0
    avg_daily_el_co = avg_daily_el_cwu = total_defrosts = total_comp_starts = 0
    total_work_hours = avg_work_time_per_start = 0.0
    avg_amb_temp = np.nan

# --- ZAŁADOWANIE DANYCH POGODOWYCH DO KORELACJI ---
weather_df = pd.DataFrame()
if not df_pivot.empty:
    try:
        # Jeśli wybrano zakres "1 dzień", pobierz dane pogodowe tylko z dzisiaj
        weather_data = get_weather_data(days=30, is_today=is_today_range)
        if weather_data:
            # Elastyczne tworzenie DataFrame - dopasowanie do faktycznej struktury danych z bazy (8 kolumn)
            if len(weather_data) > 0 and len(weather_data[0]) >= 8:
                # Struktura z bazy: id, timestamp, temperature, humidity, windspeed, precipitation, latitude, longitude
                weather_df = pd.DataFrame(weather_data, columns=['id', 'timestamp', 'temperature', 'humidity', 'windspeed', 'precipitation', 'latitude', 'longitude'])
                # Znormalizuj nazwy kolumn do oczekiwanego formatu
                weather_df = weather_df.rename(columns={'windspeed': 'wind_speed'})
                # Dodaj brakujące kolumny jeśli ich nie ma
                if 'pressure' not in weather_df.columns:
                    weather_df['pressure'] = 1013.0  # średnie ciśnienie
                if 'cloud_cover' not in weather_df.columns:
                    weather_df['cloud_cover'] = 0.0
                if 'created_at' not in weather_df.columns:
                    weather_df['created_at'] = None
    except Exception as e:
        st.warning(f"Nie udało się załadować danych pogodowych: {e}")

# --- GENEROWANIE RAPORTU DIAGNOSTYCZNEGO (dla zakładki Diagnostyka) ---
diagnostic_report = None
if not df_pivot.empty:
    try:
        diagnostic_report = generate_diagnostic_report(
            df=df_pivot,
            weather_df=weather_df,
            electricity_price=electricity_price  # zł/kWh - pobrane z UI
        )
    except Exception as e:
        st.warning(f"Błąd generowania raportu diagnostycznego: {e}")

# --- ZAKŁADKI DASHBOARDU ---
tab_main, tab_scop, tab_diag, tab_weather, tab_meter, tab_export = st.tabs([
    "📊 Panel Główny", 
    "🏆 Bilans Energetyczny & SCOP", 
    "🏥 Diagnostyka Pompy",
    "🌤️ Kontekst Pogodowy",
    "⚡ Fizyczny Licznik Energii",
    "📁 Eksport Danych"
])

# --- ZAKŁADKA 1: PANEL GŁÓWNY ---
with tab_main:
    if df.empty:
        st.info("Brak danych telemetrycznych pompy w wybranym oknie czasowym.")
    else:
        latest_df = df.drop_duplicates(subset=["code"], keep="last")
        def get_val(c):
            row = latest_df[latest_df["code"] == c]
            if not row.empty:
                v_num = row["val_num"].values[0]
                if pd.notnull(v_num):
                    return f"{v_num} °C" if "temp" in c or c in ["tidr", "back_temp", "heat_temp_set"] else f"{v_num}"
                return str(row["val_str"].values[0])
            return "N/A"

        latest_cop = df_pivot["COP"].dropna().iloc[-1] if not df_pivot["COP"].dropna().empty else 0.0
        latest_p_th = df_pivot["P_th_kw"].iloc[-1] if not df_pivot.empty else 0.0
        latest_p_el = df_pivot["P_el_kw"].iloc[-1] if not df_pivot.empty else 0.0
        latest_flow = df_pivot["flow_m3h"].iloc[-1] if not df_pivot.empty else 0.0
        current_mode = df_pivot["Tryb"].iloc[-1] if not df_pivot.empty else "CO"

        c1, c2, c3, c4, c5, c6 = st.columns(6)
        c1.metric("Woda CWU", get_val("tank_temp"))
        c2.metric("Powrót CO", get_val("in_water_temp"))
        c3.metric("Zasilanie CO", get_val("out_water_temp"))
        c4.metric("🎯 Nastawa CO", get_val("heat_temp_set"))
        c5.metric("Przepływ", f"{latest_flow:.1f} m³/h", delta=f"{latest_flow * 1000 / 60:.1f} L/min")
        c6.metric("📊 Chwilowe COP", f"{latest_cop:.2f}", delta=f"Tryb: {current_mode}")

        cp1, cp2 = st.columns(2)
        cp1.metric("🔥 Moc cieplna (P_th)", f"{latest_p_th:.2f} kW")
        cp2.metric("⚡ Pobór prądu (P_el)", f"{latest_p_el:.2f} kW")

        st.markdown("---")
        st.subheader("📊 Chwilowe COP z podziałem na tryb CO / CWU")
        fig_cop = px.line(
            df_pivot.dropna(subset=["COP"]),
            x="czas", y="COP", color="Tryb",
            color_discrete_map={"CO": "#2ECC71", "CWU": "#E67E22"},
            title="Wykres chwilowego COP (Zielony = CO, Pomarańczowy = CWU)",
            markers=(resample_rule is not None)
        )
        fig_cop.update_layout(hovermode="x unified")
        st.plotly_chart(fig_cop, width="stretch")

        st.subheader("📈 Przebieg wybranych parametrów")
        # Zastosuj korektę czasu dla surowych danych przed filtrowaniem
        df_corrected = apply_time_correction(df.copy(), time_offset_hours)
        all_codes = df_corrected["code"].unique().tolist()
        default_temps = [c for c in ["tank_temp", "in_water_temp", "out_water_temp", "heat_temp_set", "amb_temp"] if c in all_codes]
        selected_temps = st.multiselect("Wybierz parametry do wyświetlenia:", options=all_codes, default=default_temps, format_func=get_param_label)

        if selected_temps:
            temp_df = df_corrected[df_corrected["code"].isin(selected_temps) & df_corrected["val_num"].notnull()].copy()
            if resample_rule:
                temp_df["czas"] = pd.to_datetime(temp_df["czas"])
                temp_df = temp_df.groupby(["code", pd.Grouper(key="czas", freq=resample_rule)])["val_num"].mean().reset_index()

            temp_df["Parametr"] = temp_df["code"].map(lambda c: PARAM_INFO.get(c, {}).get("label", c))
            temp_df["Opis"] = temp_df["code"].map(lambda c: PARAM_INFO.get(c, {}).get("desc", "Brak opisu"))

            fig_temp = px.line(
                temp_df, x="czas", y="val_num", color="Parametr",
                hover_data={"Parametr": True, "Opis": True, "val_num": ":.1f", "code": False},
                title="Wykres parametrów w czasie"
            )
            fig_temp.update_layout(hovermode="x unified")
            st.plotly_chart(fig_temp, width="stretch")

# --- ZAKŁADKA 2: SCOP ---
with tab_scop:
    st.header("🏆 Podsumowanie Efektywności SCOP i Zużycia Energii")
    if df.empty:
        st.info("Brak danych do wyliczenia bilansu.")
    else:
        sc_col1, sc_col2, sc_col3 = st.columns(3)
        sc_col1.metric("🌟 SCOP Całkowite", f"{scop_total:.2f}")
        sc_col2.metric("🏠 SCOP dla CO (Ogrzewanie)", f"{scop_co:.2f}")
        sc_col3.metric("🚿 SCOP dla CWU (Ciepła Woda)", f"{scop_cwu:.2f}")

        st.markdown("### 📊 Statystyki Średniodobowe i Odszranianie")
        d_col1, d_col2, d_col3, d_col4 = st.columns(4)
        d_col1.metric("⚡ Śr. dzienne zużycie CO", f"{avg_daily_el_co:.2f} kWh/dzień")
        d_col2.metric("⚡ Śr. dzienne zużycie CWU", f"{avg_daily_el_cwu:.2f} kWh/dzień")
        d_col3.metric("🌡️ Średniodobowa temp. zewn.", f"{avg_amb_temp:.1f} °C" if not np.isnan(avg_amb_temp) else "Brak danych")
        d_col4.metric("❄️ Liczba defrostów (okres)", f"{total_defrosts}")
        
        d_col5, d_col6, d_col7 = st.columns(3)
        d_col5.metric("🔁 Liczba startów sprężarki (okres)", f"{total_comp_starts}")
        d_col6.metric("⏱️ Średni czas pracy sprężarki", f"{avg_work_time_per_start:.1f} min")
        d_col7.metric("🕐 Całkowity czas pracy sprężarki", f"{total_work_hours:.1f} h")

        st.markdown("---")
        st.subheader("⚡ Zużycie Prądu i Wygenerowane Ciepło [kWh] (Całkowite)")
        summary_data = {
            "Obieg / Tryb": ["🏠 Ogrzewanie (CO)", "🚿 Ciepła Woda (CWU)", " TOTAL (Łącznie)"],
            "Pobrana Energia El. [kWh]": [f"{e_el_co:.2f}", f"{e_el_cwu:.2f}", f"{e_el_total:.2f}"],
            "Oddane Ciepło [kWh]": [f"{e_th_co:.2f}", f"{e_th_cwu:.2f}", f"{e_th_total:.2f}"],
            "Średnie SCOP": [f"{scop_co:.2f}", f"{scop_cwu:.2f}", f"{scop_total:.2f}"]
        }
        st.table(pd.DataFrame(summary_data))

        fig_bar = go.Figure(data=[
            go.Bar(name='Prąd pobrany [kWh]', x=['Ogrzewanie CO', 'Ciepła Woda CWU'], y=[e_el_co, e_el_cwu], marker_color='#3498DB'),
            go.Bar(name='Ciepło oddane [kWh]', x=['Ogrzewanie CO', 'Ciepła Woda CWU'], y=[e_th_co, e_th_cwu], marker_color='#E74C3C')
        ])
        fig_bar.update_layout(barmode='group', title="Porównanie energii pobranej do oddanej")
        st.plotly_chart(fig_bar, width="stretch")

        st.markdown("---")
        st.subheader("📅 Dzienny Bilans Zużycia, Temperatur i Defrostów (wszystkie dane)")
        daily_display_all = daily_df_all[["dzień", "amb_temp", "E_el_co_row", "E_el_cwu_row", "E_el_total", "E_th_total", "SCOP_dzienny", "defrost_start"]].copy()
        daily_display_all.columns = ["Data", "Śr. Temp Zewn. [°C]", "Prąd CO [kWh]", "Prąd CWU [kWh]", "Prąd Łącznie [kWh]", "Ciepło Łącznie [kWh]", "SCOP Dzienny", "Liczba Defrostów"]
        daily_display_all["Śr. Temp Zewn. [°C]"] = daily_display_all["Śr. Temp Zewn. [°C]"].round(1)
        daily_display_all["Prąd CO [kWh]"] = daily_display_all["Prąd CO [kWh]"].round(2)
        daily_display_all["Prąd CWU [kWh]"] = daily_display_all["Prąd CWU [kWh]"].round(2)
        daily_display_all["Prąd Łącznie [kWh]"] = daily_display_all["Prąd Łącznie [kWh]"].round(2)
        daily_display_all["Ciepło Łącznie [kWh]"] = daily_display_all["Ciepło Łącznie [kWh]"].round(2)
        daily_display_all["SCOP Dzienny"] = daily_display_all["SCOP Dzienny"].round(2)
        st.dataframe(daily_display_all, width="stretch", hide_index=True)

# --- ZAKŁADKA 3: DIAGNOSTYKA ---
with tab_diag:
    st.header("🏥 Centrum Diagnostyczne Pompy Ciepła")
    if df.empty:
        st.info("Brak danych diagnostycznych.")
    else:
        # --- SEKCJA 1: RAPORT ZAAWANSOWANEJ DIAGNOSTYKI ---
        st.subheader("📋 Raport Zaawansowanej Diagnostyki")
        
        if diagnostic_report:
            # Kolumny z kluczowymi metrykami
            diag_col1, diag_col2, diag_col3, diag_col4 = st.columns(4)
            
            # Cykle krótkie
            short_cycles_count = len(diagnostic_report.short_cycles)
            if short_cycles_count > 0:
                diag_col1.warning(f"⚠️ Wykryto cykli krótkich: **{short_cycles_count}**")
                total_wasted = sum(c.energy_wasted_kwh for c in diagnostic_report.short_cycles)
                diag_col1.metric("Energia zmarnowana na cykle", f"{total_wasted:.2f} kWh")
            else:
                diag_col1.success("✅ Brak cykli krótkich")
            
            # Analiza inwertera
            if diagnostic_report.inverter_analysis:
                inv = diagnostic_report.inverter_analysis
                diag_col2.metric("Śr. częstotliwość sprężarki", f"{inv.avg_frequency:.1f} Hz")
                diag_col2.metric("Stabilność pracy", f"{inv.stability_score:.0f}/100")
                if inv.frequent_starts > 10:
                    diag_col2.warning(f"Częste starty: {inv.frequent_starts}")
            
            # Analiza trybów
            if diagnostic_report.mode_analysis:
                mode = diagnostic_report.mode_analysis
                diag_col3.metric("Czas pracy CO", f"{mode.co_runtime_hours:.1f} h")
                diag_col3.metric("Czas pracy CWU", f"{mode.cwu_runtime_hours:.1f} h")
                diag_col3.metric("Przełączeń trybów", f"{mode.mode_transitions}")
            
            # Korelacja pogodowa
            if diagnostic_report.weather_correlation:
                weather = diagnostic_report.weather_correlation
                diag_col4.metric("Śr. temperatura zewn.", f"{weather.temp_outside_avg:.1f}°C")
                corr = weather.cop_vs_temp_correlation
                diag_col4.metric("Korelacja COP↔Temp", f"{corr:.2f}")
            
            st.markdown("---")
            
            # Rekomendacje
            if diagnostic_report.recommendations:
                st.subheader("💡 Rekomendacje")
                for i, rec in enumerate(diagnostic_report.recommendations, 1):
                    if "krótkich" in rec.lower() or "taktowanie" in rec.lower():
                        st.error(f"**{i}.** {rec}")
                    elif "optymalizacji" in rec.lower() or "efektywności" in rec.lower():
                        st.warning(f"**{i}.** {rec}")
                    else:
                        st.info(f"**{i}.** {rec}")
            
            st.markdown("---")
            st.subheader("📊 Szczegółowa analiza inwertera")
            
            if diagnostic_report.inverter_analysis:
                inv = diagnostic_report.inverter_analysis
                inv_col1, inv_col2, inv_col3 = st.columns(3)
                inv_col1.metric("Min częstotliwość", f"{inv.min_frequency:.1f} Hz")
                inv_col1.metric("Max częstotliwość", f"{inv.max_frequency:.1f} Hz")
                inv_col2.metric("Odchylenie std", f"{inv.std_frequency:.1f} Hz")
                inv_col2.metric("Efektywność modulacji", f"{inv.modulation_efficiency:.1f}%")
                inv_col3.metric("Czas w zakresie opt. (30-60 Hz)", f"{inv.optimal_range_pct:.1f}%")
                
                # Wykres rozkładu częstotliwości
                if 'comp_freq' in df_pivot.columns:
                    fig_hist = px.histogram(
                        df_pivot[df_pivot['comp_freq'] > 0],
                        x='comp_freq',
                        nbins=30,
                        title="Rozkład częstotliwości pracy sprężarki",
                        labels={'comp_freq': 'Częstotliwość [Hz]'},
                        color_discrete_sequence=['#3498DB']
                    )
                    fig_hist.add_vrect(x0=30, x1=60, fillcolor="green", opacity=0.15, 
                                       annotation_text="Zakres optymalny (30-60 Hz)", annotation_position="top")
                    st.plotly_chart(fig_hist, width="stretch")
            
            st.markdown("---")
            st.subheader("🔄 Analiza cykli krótkich")
            
            if diagnostic_report.short_cycles:
                cycles_data = []
                for cycle in diagnostic_report.short_cycles:
                    cycles_data.append({
                        "Start": cycle.start_time.strftime("%Y-%m-%d %H:%M"),
                        "Koniec": cycle.end_time.strftime("%Y-%m-%d %H:%M"),
                        "Czas trwania [s]": cycle.duration_sec,
                        "Czas wyłączenia przed [s]": cycle.off_duration_sec,
                        "Śr. COP": f"{cycle.cop_avg:.2f}",
                        "Strata energii [kWh]": f"{cycle.energy_wasted_kwh:.3f}"
                    })
                cycles_df = pd.DataFrame(cycles_data)
                st.dataframe(cycles_df, width="stretch", hide_index=True)
            else:
                st.success("✅ Nie wykryto cykli krótkich w analizowanym okresie.")
        
        st.markdown("---")
        
        # --- SEKCJA 2: STANDARDOWA DIAGNOSTYKA ---
        st.subheader("⚠️ Status Pracy i Ostrzeżenia")
        col_a1, col_a2, col_a3 = st.columns(3)

        last_disc = df_pivot["disc_temp"].dropna().iloc[-1] if not df_pivot["disc_temp"].dropna().empty else None
        with col_a1:
            if last_disc and last_disc >= 90.0:
                st.error(f"🔴 **KRYTYCZNA TEMP. TŁOCZENIA:** {last_disc:.1f}°C\nRyzyko uszkodzenia!")
            elif last_disc and last_disc >= 80.0:
                st.warning(f"🟡 **Podwyższona temp. tłoczenia:** {last_disc:.1f}°C")
            elif last_disc:
                st.success(f"🟢 **Temp. tłoczenia w normie:** {last_disc:.1f}°C")
            else:
                st.info("⚪ Brak danych temp. tłoczenia")

        last_dt = df_pivot["delta_t"].dropna().iloc[-1] if not df_pivot["delta_t"].dropna().empty else None
        is_pumping = df_pivot["P_el_kw"].iloc[-1] > 0.2 if not df_pivot.empty else False
        with col_a2:
            if is_pumping and last_dt is not None:
                if last_dt < 2.0:
                    st.warning(f"🟡 **Za małe ΔT ({last_dt:.1f}°C):** Przepływ wody za duży.")
                elif last_dt > 8.0:
                    st.warning(f"🟡 **Za duże ΔT ({last_dt:.1f}°C):** Zbyt mały przepływ wody.")
                else:
                    st.success(f"🟢 **Różnica ΔT w normie:** {last_dt:.1f}°C")
            else:
                st.info("⚪ Pompa w stanie spoczynku")

        is_comp_on = df_pivot["comp_freq"] > 5
        starts_count = (is_comp_on & (~is_comp_on.shift(1, fill_value=False))).sum()
        with col_a3:
            if starts_count > 15:
                st.warning(f"🟡 **Wykryto taktowanie!** Starty: **{starts_count}**")
            else:
                st.success(f"🟢 **Cykliczność w normie:** Starty: **{starts_count}**")

        st.markdown("---")
        st.subheader("📊 Tabela: Statystyki dzienne pracy sprężarki")
        
        # Przygotowanie tabeli z danymi dziennymi
        daily_comp_stats = daily_df_all[["dzień", "comp_start", "dt_hours_work"]].copy()
        daily_comp_stats.columns = ["Data", "Liczba startów", "Czas pracy [h]"]
        
        # Oblicz średni czas pracy na jeden start (w minutach)
        daily_comp_stats["Śr. czas pracy/start [min]"] = np.where(
            daily_comp_stats["Liczba startów"] > 0,
            (daily_comp_stats["Czas pracy [h]"] / daily_comp_stats["Liczba startów"]) * 60,
            0.0
        )
        
        # Zaokrąglenie wartości
        daily_comp_stats["Czas pracy [h]"] = daily_comp_stats["Czas pracy [h]"].round(2)
        daily_comp_stats["Śr. czas pracy/start [min]"] = daily_comp_stats["Śr. czas pracy/start [min]"].round(1)
        daily_comp_stats["Liczba startów"] = daily_comp_stats["Liczba startów"].astype(int)
        
        # Wyświetlenie tabeli
        st.dataframe(daily_comp_stats, width="stretch", hide_index=True)
        
        st.markdown("---")
        st.subheader("1️⃣ Odbiór ciepła przez instalację (Różnica temperatur ΔT)")
        fig_dt = go.Figure()
        fig_dt.add_trace(go.Scatter(x=df_pivot["czas"], y=df_pivot["delta_t"], mode='lines', name='ΔT (°C)', line=dict(color='#3498DB', width=2)))
        fig_dt.add_hrect(y0=3.0, y1=7.0, fillcolor="Green", opacity=0.15, line_width=0, annotation_text="Strefa optymalna (3 - 7 °C)", annotation_position="top left")
        fig_dt.update_layout(hovermode="x unified", xaxis_title="Czas", yaxis_title="ΔT (°C)")
        st.plotly_chart(fig_dt, width="stretch")

        st.subheader("2️⃣ Bezpieczeństwo Sprężarki (Temperatura Tłoczenia Discharge)")
        fig_disc = go.Figure()
        fig_disc.add_trace(go.Scatter(x=df_pivot["czas"], y=df_pivot["disc_temp"], mode='lines', name='Temp. Tłoczenia (°C)', line=dict(color='#E67E22', width=2)))
        fig_disc.add_trace(go.Scatter(x=df_pivot["czas"], y=df_pivot["comp_freq"], mode='lines', name='Obroty sprężarki (Hz)', line=dict(color='#9B59B6', width=1.5, dash='dot')))
        fig_disc.add_hline(y=90.0, line_dash="dash", line_color="Red", annotation_text="Krytyczne 90°C", annotation_position="bottom right")
        fig_disc.update_layout(hovermode="x unified", xaxis_title="Czas", yaxis_title="Wartość")
        st.plotly_chart(fig_disc, width="stretch")

# --- ZAKŁADKA 4: KONTEKST POGODOWY ---
with tab_weather:
    st.header("🌤️ Kontekst Pogodowy i Wpływ na Wydajność")
    
    if df_pivot.empty:
        st.info("Brak danych do analizy korelacji pogodowych.")
    else:
        if diagnostic_report and diagnostic_report.weather_correlation:
            weather = diagnostic_report.weather_correlation
            
            # Kolumny z metrykami pogodowymi
            wx_col1, wx_col2, wx_col3, wx_col4 = st.columns(4)
            
            wx_col1.metric("Średnia temperatura zewn.", f"{weather.temp_outside_avg:.1f}°C")
            wx_col2.metric("Korelacja COP↔Temp", f"{weather.cop_vs_temp_correlation:.2f}", 
                          help="Współczynnik korelacji Pearsona (-1 do 1). Wartości dodatnie oznaczają że COP rośnie z temperaturą.")
            wx_col3.metric("Spadek COP na °C", f"{weather.efficiency_drop_per_degree:.3f}",
                          help="O ile spada COP przy spadku temperatury o 1°C")
            wx_col4.metric("HDD (Heating Degree Days)", f"{weather.heating_degree_days:.1f}",
                          help="Stopniodni grzania - miara chłodu okresu")
            
            st.markdown("---")
            
            # Zakresy temperatur i COP
            st.subheader("📊 COP w zależności od zakresu temperatury")
            
            if weather.cop_at_temp_ranges:
                ranges_df = pd.DataFrame([
                    {"Zakres temp.": range_label.replace("_", " ").title(), "Śr. COP": cop}
                    for range_label, cop in weather.cop_at_temp_ranges.items()
                ])
                st.dataframe(ranges_df, width="stretch", hide_index=True)
                
                # Wykres słupkowy COP vs temperature ranges
                fig_cop_ranges = px.bar(
                    ranges_df,
                    x="Zakres temp.",
                    y="Śr. COP",
                    title="Średnie COP w różnych zakresach temperatur zewnętrznych",
                    labels={"Zakres temp.": "Zakres temperatury [°C]", "Śr. COP": "COP"},
                    color="Śr. COP",
                    color_continuous_scale="RdYlGn"
                )
                fig_cop_ranges.update_layout(coloraxis_showscale=False)
                st.plotly_chart(fig_cop_ranges, width="stretch")
            
            st.markdown("---")
            
            # Optymalny zakres temperatur
            opt_range = weather.optimal_temp_range
            if opt_range[0] != opt_range[1]:
                st.success(f"🎯 **Optymalny zakres temperatur dla najlepszego COP:** {opt_range[0]:.1f}°C do {opt_range[1]:.1f}°C")
            
            st.markdown("---")
            
            # Wykres scatter: COP vs temperatura zewnętrzna
            st.subheader("📈 Korelacja COP z temperaturą zewnętrzną")
            
            if 'amb_temp' in df_pivot.columns and not df_pivot['amb_temp'].isna().all():
                scatter_df = df_pivot[['czas', 'COP', 'amb_temp', 'P_el_kw', 'Tryb']].dropna().copy()
                
                if not scatter_df.empty:
                    fig_scatter = px.scatter(
                        scatter_df,
                        x='amb_temp',
                        y='COP',
                        color='Tryb',
                        size='P_el_kw',
                        hover_data=['czas'],
                        title="Zależność COP od temperatury zewnętrznej (rozmiar = moc elektryczna)",
                        labels={
                            'amb_temp': 'Temperatura zewnętrzna [°C]',
                            'COP': 'COP',
                            'Tryb': 'Tryb pracy'
                        },
                        color_discrete_map={"CO": "#2ECC71", "CWU": "#E67E22"}
                    )
                    
                    # Dodaj linię trendu
                    import numpy as np
                    if len(scatter_df) > 10:
                        z = np.polyfit(scatter_df['amb_temp'].dropna(), scatter_df['COP'].dropna(), 1)
                        p = np.poly1d(z)
                        fig_scatter.add_trace(go.Scatter(
                            x=scatter_df['amb_temp'].sort_values(),
                            y=p(scatter_df['amb_temp'].sort_values()),
                            mode='lines',
                            name='Trend liniowy',
                            line=dict(color='red', width=2, dash='dash')
                        ))
                    
                    st.plotly_chart(fig_scatter, width="stretch")
            
            st.markdown("---")
            
            # Wykres porównawczy: temperatura z serwisu internetowego vs pompa ciepła
            st.subheader("🌡️ Porównanie temperatury: Serwis pogodowy vs Pompa ciepła")
            
            if not weather_df.empty and 'amb_temp' in df_pivot.columns:
                # Przygotowanie danych do wykresu
                weather_df_copy = weather_df.copy()
                weather_df_copy['timestamp'] = pd.to_datetime(weather_df_copy['timestamp'], unit='s')
                # Zastosowanie tej samej korekty czasu jak dla danych z pompy ciepła
                weather_df_copy['timestamp'] = weather_df_copy['timestamp'] + pd.Timedelta(hours=time_offset_hours)
                
                # Filtrowanie do zakresu czasowego df_pivot
                if not df_pivot.empty and 'czas' in df_pivot.columns:
                    min_time = df_pivot['czas'].min()
                    max_time = df_pivot['czas'].max()
                    weather_filtered = weather_df_copy[
                        (weather_df_copy['timestamp'] >= min_time) & 
                        (weather_df_copy['timestamp'] <= max_time)
                    ].copy()
                    
                    if not weather_filtered.empty:
                        fig_compare = go.Figure()
                        
                        # Temperatura z serwisu internetowego (linia ciągła)
                        fig_compare.add_trace(go.Scatter(
                            x=weather_filtered['timestamp'],
                            y=weather_filtered['temperature'],
                            mode='lines',
                            name='Serwis pogodowy (Open-Meteo)',
                            line=dict(color='#3498DB', width=2),
                            yaxis='y1'
                        ))
                        
                        # Temperatura z pompy ciepła (linia przerywana)
                        pump_temp_df = df_pivot[df_pivot['amb_temp'].notna()].copy()
                        if not pump_temp_df.empty:
                            fig_compare.add_trace(go.Scatter(
                                x=pump_temp_df['czas'],
                                y=pump_temp_df['amb_temp'],
                                mode='lines',
                                name='Pompa ciepła (odczyt)',
                                line=dict(color='#E74C3C', width=2, dash='dash'),
                                yaxis='y1'
                            ))
                        
                        fig_compare.update_layout(
                            title="Porównanie temperatury zewnętrznej: dane pogodowe vs odczyt z pompy",
                            xaxis=dict(title="Czas"),
                            yaxis=dict(title="Temperatura [°C]"),
                            hovermode='x unified',
                            legend=dict(x=0, y=1.1, orientation='h')
                        )
                        
                        st.plotly_chart(fig_compare, width="stretch")
                    else:
                        st.info("Brak danych pogodowych w wybranym zakresie czasu.")
                else:
                    st.info("Brak danych temperaturowych z pompy ciepła.")
            elif weather_df.empty:
                st.info("Brak danych pogodowych z serwisu internetowego.")
            else:
                st.info("Brak danych o temperaturze zewnętrznej z pompy ciepła.")
            
            st.markdown("---")
            
            # Wykres czasowy: temperatura + COP
            st.subheader("📊 Przebieg czasowy: Temperatura zewnętrzna i COP")
            
            if 'amb_temp' in df_pivot.columns and not df_pivot['amb_temp'].isna().all():
                fig_dual = go.Figure()
                
                # Filtruj dane do niepustych wartości temperatury
                temp_df = df_pivot[df_pivot['amb_temp'].notna()].copy()
                
                if not temp_df.empty:
                    fig_dual.add_trace(go.Scatter(
                        x=temp_df['czas'],
                        y=temp_df['amb_temp'],
                        mode='lines',
                        name='Temp. zewn. [°C]',
                        line=dict(color='#3498DB', width=2),
                        yaxis='y1'
                    ))
                    
                    fig_dual.add_trace(go.Scatter(
                        x=df_pivot['czas'],
                        y=df_pivot['COP'],
                        mode='lines',
                        name='COP',
                        line=dict(color='#E67E22', width=2),
                        yaxis='y2'
                    ))
                    
                    fig_dual.update_layout(
                        title="Temperatura zewnętrzna vs COP w czasie",
                        xaxis=dict(title="Czas"),
                        yaxis=dict(title="Temperatura [°C]", overlaying='y2'),
                        yaxis2=dict(title="COP", side='right', overlaying='y'),
                        hovermode='x unified',
                        legend=dict(x=0, y=1.1, orientation='h')
                    )
                    
                    st.plotly_chart(fig_dual, width="stretch")
                else:
                    st.info("Brak danych o temperaturze zewnętrznej w wybranym zakresie czasu.")
        
        else:
            st.warning("Nie udało się wygenerować raportu korelacji pogodowej. Sprawdź czy dane pogodowe są dostępne.")
        
        # Tabela z danymi pogodowymi
        st.markdown("---")
        st.subheader("📋 Ostatnie dane pogodowe z bazy")
        
        if not weather_df.empty:
            # Obliczanie początku bieżącego dnia kalendarzowego z uwzględnieniem przesunięcia czasowego
            now_local = datetime.now() + timedelta(hours=time_offset_hours)
            start_of_day_local = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
            
            # Konwersja z powrotem na czas serwerowy dla filtrowania
            start_query_time = start_of_day_local - timedelta(hours=time_offset_hours)
            
            # Filtrowanie danych tylko z bieżącego dnia (po korekcie czasu)
            weather_today = weather_df[weather_df['timestamp'] >= start_query_time.timestamp()].copy()
            
            if not weather_today.empty:
                weather_display = weather_today[['timestamp', 'temperature', 'humidity', 'pressure', 'wind_speed']].copy()
                weather_display['timestamp'] = pd.to_datetime(weather_display['timestamp'], unit='s')
                # Zastosowanie tej samej korekty czasu jak dla danych z pompy ciepła
                weather_display['timestamp'] = weather_display['timestamp'] + pd.Timedelta(hours=time_offset_hours)
                weather_display['timestamp'] = weather_display['timestamp'].dt.strftime('%Y-%m-%d %H:%M')
                weather_display.columns = ['Czas', 'Temp. [°C]', 'Wilgotność [%]', 'Ciśnienie [hPa]', 'Wiatr [m/s]']
                st.dataframe(weather_display.head(20), width="stretch", hide_index=True)
            else:
                st.info("Brak danych pogodowych w wybranym zakresie (dzisiejszy dzień).")
        else:
            st.info("Brak zapisanych danych pogodowych w bazie. Upewnij się że usługa pobierania pogody działa.")

# --- ZAKŁADKA 5: FIZYCZNY LICZNIK ENERGII (FORMULARZ & WYKRES) ---
with tab_meter:
    st.header("⚡ Rejestracja i Analiza Fizycznego Licznika Energii")
    st.caption(f"Dane wprowadzane ręcznie są rejestrowane w bazie pod identyfikatorem urządzenia: `{MANUAL_METER_DEV_ID}`.")

    # Zarządzanie stanem formularza (czyszczenie pola po dodaniu)
    if "meter_val_input" not in st.session_state:
        st.session_state["meter_val_input"] = ""

    col_form_add, col_form_edit = st.columns([1, 1])

    # --- SEKCJA DODAWANIA ---
    with col_form_add:
        st.subheader("➕ Dodaj nowy stan licznika")
        with st.form("form_add_manual_meter", clear_on_submit=False):
            now_dt = datetime.now()
            add_date = st.date_input("Data odczytu", value=now_dt.date(), key="add_date_key")
            add_time = st.time_input("Godzina odczytu", value=now_dt.time(), key="add_time_key")
            
            add_val_str = st.text_input(
                "Stan licznika [kWh]", 
                value=st.session_state["meter_val_input"], 
                placeholder="np. 12450.5",
                key="input_meter_str"
            )
            
            btn_add = st.form_submit_button("💾 Zapisz stan licznika", width="stretch")

            if btn_add:
                # Walidacja danych
                clean_str = add_val_str.strip().replace(",", ".")
                if not clean_str:
                    st.error("Pole stanu licznika nie może być puste!")
                else:
                    try:
                        val_float = float(clean_str)
                        ts_val = int(datetime.combine(add_date, add_time).timestamp())
                        success, msg = save_manual_energy_reading(val_float, ts_val)
                        if success:
                            st.success(msg)
                            st.session_state["meter_val_input"] = ""
                            st.rerun()
                        else:
                            st.error(msg)
                    except ValueError:
                        st.error("Wprowadzono niepoprawną wartość liczbową.")

    # --- SEKCJA EDYCJI / USUWANIA (ZWIJANA) ---
    with st.expander("✏️ Edytuj lub usuń wpis", expanded=False):
        df_meter_all = load_manual_readings()
        
        if df_meter_all.empty:
            st.info("Brak wpisów w historii licznika do modyfikacji.")
        else:
            options_edit = {
                f"[ID: {r['id']}] {r['czas']} -> {r['stan_kwh']:.2f} kWh": r 
                for _, r in df_meter_all.sort_values("timestamp", ascending=False).iterrows()
            }
            sel_label = st.selectbox("Wybierz wpis do edycji:", list(options_edit.keys()), index=None, placeholder="Wybierz z listy...")
            
            if sel_label:
                selected_rec = options_edit[sel_label]

                with st.form("form_edit_manual_meter"):
                    rec_dt = pd.to_datetime(selected_rec["czas"])
                    edit_date = st.date_input("Popraw datę", value=rec_dt.date())
                    edit_time = st.time_input("Popraw godzinę", value=rec_dt.time())
                    edit_val = st.number_input("Popraw stan [kWh]", value=float(selected_rec["stan_kwh"]), step=0.1, format="%.2f")

                    col_e1, col_e2 = st.columns(2)
                    btn_update = col_e1.form_submit_button("💾 Zapisz zmiany", width="stretch")
                    btn_delete = col_e2.form_submit_button("🗑️ Usuń wpis", width="stretch")

                    if btn_update:
                        edit_ts = int(datetime.combine(edit_date, edit_time).timestamp())
                        ok, msg = update_manual_energy_reading(int(selected_rec["id"]), edit_val, edit_ts)
                        if ok:
                            st.success(msg)
                            st.rerun()
                        else:
                            st.error(msg)

                    if btn_delete:
                        if delete_manual_energy_reading(int(selected_rec["id"])):
                            st.warning(f"Usunięto wpis ID: {selected_rec['id']}")
                            st.rerun()
                        else:
                            st.error("Błąd podczas usuwania wpisu.")

    st.markdown("---")

    # --- TABELA HISTORII Z RÓŻNICAMI ---
    st.subheader("📋 Tabela odczytów i zużycia energii")
    if df_meter_all.empty:
        st.info("Wprowadź co najmniej dwa odczyty licznika, aby wyświetlić tabelę różnic oraz wykres.")
    else:
        df_display = df_meter_all.copy()
        df_display["czas_dt"] = pd.to_datetime(df_display["czas"])
        # Korekta czasu już została zastosowana w load_manual_readings(), więc tylko sortujemy
        df_display = df_display.sort_values("czas_dt").reset_index(drop=True)

        # Różnice pomiędzy kolejnymi wpisami
        df_display["Zużycie [kWh]"] = df_display["stan_kwh"].diff()
        df_display["Okres [h]"] = df_display["timestamp"].diff() / 3600.0
        df_display["Średnia Moc [kW]"] = np.where(df_display["Okres [h]"] > 0, df_display["Zużycie [kWh]"] / df_display["Okres [h]"], np.nan)

        table_view = df_display[["id", "czas", "stan_kwh", "Zużycie [kWh]", "Okres [h]", "Średnia Moc [kW]"]].copy()
        table_view.columns = ["ID", "Data i Godzina", "Stan Licznika [kWh]", "Różnica / Zużycie [kWh]", "Czas od poprz. [h]", "Śr. Moc w okresie [kW]"]
        table_view["Stan Licznika [kWh]"] = table_view["Stan Licznika [kWh]"].round(2)
        table_view["Różnica / Zużycie [kWh]"] = table_view["Różnica / Zużycie [kWh]"].round(2)
        table_view["Czas od poprz. [h]"] = table_view["Czas od poprz. [h]"].round(1)
        table_view["Śr. Moc w okresie [kW]"] = table_view["Śr. Moc w okresie [kW]"].round(2)

        st.dataframe(table_view.sort_values("ID", ascending=False), width="stretch", hide_index=True)

        # --- WYKRES DZIENNEGO ZUŻYCIA Z ESTYMACJĄ I PORÓWNANIEM Z POMPĄ ---
        st.markdown("---")
        st.subheader("📊 Dzienne Zużycie Energii: Licznik Fizyczny (Estymowany) vs Wyliczenia Pompy")

        if len(df_display) >= 2:
            # Tworzenie ciągłej siatki czasowej (co 1 godzinę) do liniowej interpolacji brakujących dni
            df_interp = df_display.set_index("czas_dt")[["stan_kwh"]].resample("1h").interpolate(method="time")
            df_interp_daily = df_interp.resample("1D").first()
            df_interp_daily["Zuzycie_Licznik_kWh"] = df_interp_daily["stan_kwh"].diff().shift(-1)
            # Korekta czasu dla daty dziennej - przesunięcie o dzień jeśli offset >= 12h
            df_interp_daily.index = df_interp_daily.index + pd.Timedelta(days=1 if time_offset_hours >= 12 else 0)
            df_interp_daily["dzień"] = df_interp_daily.index.date
            
            meter_daily = df_interp_daily.dropna(subset=["Zuzycie_Licznik_kWh"])[["dzień", "Zuzycie_Licznik_kWh"]].reset_index(drop=True)

            # Połączenie ze statystykami dziennymi wyliczonymi przez pompę
            if not daily_df_all.empty:
                comp_df = pd.merge(meter_daily, daily_df_all[["dzień", "E_el_total"]], on="dzień", how="outer").sort_values("dzień")
            else:
                comp_df = meter_daily.copy()
                comp_df["E_el_total"] = np.nan

            comp_df = comp_df.rename(columns={"E_el_total": "Zuzycie_Pompa_kWh"})
            comp_df["dzień_str"] = comp_df["dzień"].astype(str)

            fig_comp = go.Figure()
            
            # Słupki: Fizyczny licznik (estymacja dzienna)
            fig_comp.add_trace(go.Bar(
                x=comp_df["dzień_str"],
                y=comp_df["Zuzycie_Licznik_kWh"],
                name="Fizyczny Licznik (interpolowane/estymowane)",
                marker_color="#2ECC71"
            ))

            # Linia: Wyliczenia automatyczne pompy ciepła
            fig_comp.add_trace(go.Scatter(
                x=comp_df["dzień_str"],
                y=comp_df["Zuzycie_Pompa_kWh"],
                name="Pompa Ciepła (wyliczone E_el)",
                mode="lines+markers",
                line=dict(color="#E74C3C", width=3)
            ))

            fig_comp.update_layout(
                title="Porównanie zużycia dobowego [kWh]",
                xaxis_title="Dzień",
                yaxis_title="Energia elektryczna [kWh]",
                hovermode="x unified",
                barmode="group"
            )
            st.plotly_chart(fig_comp, width="stretch")
        else:
            st.info("Wprowadź minimum 2 odczyty licznika w różnych dniach, aby wygenerować wykres interpolacji dobowej.")

# --- ZAKŁADKA 5: EKSPORT DANYCH ---
with tab_export:
    st.header("📁 Eksport Danych do CSV")
    st.markdown("""
    **Funkcjonalności eksportu:**
    - 📊 **Dane surowe**: Wszystkie pomiary z pompy ciepła
    - 📈 **Dane przetworzone**: Obliczone parametry (COP, moc, energia)
    - 📅 **Podsumowanie dzienne**: Statystyki dobowe
    
    Wybierz zakres czasu i format danych, a następnie kliknij przycisk pobierania.
    """)
    
    if df.empty:
        st.warning("Brak danych do eksportu w wybranym zakresie czasowym.")
    else:
        # Opcje eksportu
        exp_col1, exp_col2 = st.columns(2)
        with exp_col1:
            export_format = st.selectbox(
                "Format danych:",
                ["Dane surowe telemetryczne", "Dane przetworzone (z obliczeniami)", "Podsumowanie dzienne"],
                index=1
            )
        
        # Przygotowanie danych do eksportu
        if export_format == "Dane surowe telemetryczne":
            export_df = df.copy()
            filename = f"pompa_dane_surowe_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
            st.subheader("📊 Podgląd danych surowych")
            st.dataframe(export_df.head(10), width="stretch")
            
        elif export_format == "Dane przetworzone (z obliczeniami)":
            export_df = df_pivot.copy()
            filename = f"pompa_dane_przetworzone_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
            st.subheader("📈 Podgląd danych przetworzonych")
            st.dataframe(export_df.head(10), width="stretch")
            
        elif export_format == "Podsumowanie dzienne":
            export_df = daily_df.copy()
            filename = f"pompa_podsumowanie_dzienne_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
            st.subheader("📅 Podgląd podsumowania dziennego")
            st.dataframe(export_df.head(10), width="stretch")
        
        # Generowanie CSV do pobrania
        csv_data = export_df.to_csv(index=False, decimal=';', sep=';').encode('utf-8')
        
        st.download_button(
            label="⬇️ Pobierz plik CSV",
            data=csv_data,
            file_name=filename,
            mime="text/csv",
            width="stretch"
        )
        
        st.info(f"📝 Plik będzie zawierał {len(export_df)} wierszy danych z zakresu: {hours_back} godzin")
