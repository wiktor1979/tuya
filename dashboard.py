import sqlite3
import time

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

# --- KONFIGURACJA STRONY ---
st.set_page_config(
    page_title="Monitor Pompy Ciepła",
    layout="wide",
    page_icon="🔥",
)

st.markdown(
    """
    <style>
    /* 1. Wygląd kafelków metryk */
    [data-testid="stMetric"] {
        background-color: #1E1E1E;
        border: 1px solid #333;
        border-radius: 10px;
        padding: 15px;
        box-shadow: 2px 2px 10px rgba(0,0,0,0.3);
    }

    /* 2. Siatka kafelków na telefonach */
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
    """,
    unsafe_allow_html=True,
)

st.title("🔥 Panel Monitorowania i Diagnostyki Pompy Ciepła")

DB_FILE = "/data/tuya_telemetry.db"
TIMEZONE = "Europe/Warsaw"

# --- SŁOWNIK METADANYCH PARAMETRÓW ---
PARAM_INFO = {
    "in_water_temp": {
        "label": "Powrót CO",
        "desc": "Temperatura wody powracającej z instalacji grzewczej",
    },
    "out_water_temp": {
        "label": "Zasilanie CO",
        "desc": "Temperatura wody wychodzącej na dom",
    },
    "tank_temp": {
        "label": "Woda CWU",
        "desc": "Temperatura wody w zasobniku ciepłej wody użytkowej",
    },
    "amb_temp": {
        "label": "Temp. zewnętrzna",
        "desc": "Temperatura powietrza na zewnątrz budynku",
    },
    "disc_temp": {
        "label": "Tłoczenie sprężarki",
        "desc": "Temperatura gazu na wylocie/tłoczeniu sprężarki (discharge)",
    },
    "back_temp": {
        "label": "Powrót do sprężarki",
        "desc": "Temperatura czynnika na powrocie do sprężarki (suction)",
    },
    "tidr": {
        "label": "Temp. ssania",
        "desc": "Temperatura czujnika ssania / wymiennika chłodniczego",
    },
    "heat_temp_set": {
        "label": "Nastawa CO",
        "desc": "Docelowa zadana temperatura dla trybu ogrzewania CO",
    },
    "cool_temp_set": {
        "label": "Nastawa chłodzenia",
        "desc": "Docelowa zadana temperatura dla trybu chłodzenia",
    },
    "hot_water_temp_set": {
        "label": "Nastawa CWU",
        "desc": "Docelowa zadana temperatura dla wody użytkowej",
    },
    "ac_vol": {
        "label": "Napięcie AC",
        "desc": "Napięcie zasilania sieciowego AC podawane do jednostki",
    },
    "ac_curr": {
        "label": "Prąd AC",
        "desc": "Natężenie prądu pobieranego przez urządzenie",
    },
    "comp_freq": {
        "label": "Częstotliwość sprężarki",
        "desc": "Aktualna częstotliwość pracy sprężarki (Hz)",
    },
    "flow_rate": {
        "label": "Przepływ",
        "desc": "Przepływ wody w obiegu hydraulicznym",
    },
    "m_eev": {
        "label": "Zawór EEV główny",
        "desc": "Pozycja otwarcia głównego elektronicznego zaworu rozprężnego",
    },
    "valve": {
        "label": "Zawór 3-drożny",
        "desc": "Stan zaworu przełączającego (0 = CO, 1 = CWU)",
    },
    "defrost": {
        "label": "Odszranianie",
        "desc": "Cykl automatycznego odszraniania parownika",
    },
}


def get_param_label(code: str) -> str:
    info = PARAM_INFO.get(code)
    return f"{info['label']} ({code})" if info else code


def clip_outliers(series: pd.Series, low: float, high: float) -> pd.Series:
    """
    Ustawia wartości spoza zakresu jako NaN.
    """
    return series.mask((series < low) | (series > high))


def load_data(hours: int) -> pd.DataFrame:
    """
    Ładuje dane telemetryczne z bazy SQLite.

    Używany jest surowy timestamp UNIX, aby uniknąć problemów ze strefami czasu
    i zmianami czasu letniego/zimowego przy integracji energii.
    """
    start_epoch = int(time.time()) - int(hours) * 3600

    conn = sqlite3.connect(DB_FILE)

    query = """
        SELECT
            timestamp AS epoch_s,
            trim(code) AS code,
            val_num,
            val_str
        FROM telemetry
        WHERE timestamp >= ?
          AND trim(code) != 'energy_kwh'
        ORDER BY timestamp ASC
    """

    df_data = pd.read_sql_query(query, conn, params=(start_epoch,))
    conn.close()

    if not df_data.empty:
        df_data["code"] = df_data["code"].astype(str).str.strip()
        df_data["czas"] = (
            pd.to_datetime(df_data["epoch_s"], unit="s", utc=True)
            .dt.tz_convert(TIMEZONE)
            .dt.tz_localize(None)
        )

    return df_data


def load_energy_meter_total(hours: int):
    """
    Ładuje sumę energii z ręcznego licznika energii (energy_kwh),
    jeśli dostępne są co najmniej dwa odczyty w wybranym zakresie.

    Zwraca kWh albo None.
    """
    start_epoch = int(time.time()) - int(hours) * 3600

    conn = sqlite3.connect(DB_FILE)

    query = """
        SELECT
            timestamp AS epoch_s,
            val_num
        FROM telemetry
        WHERE trim(code) = 'energy_kwh'
          AND timestamp >= ?
          AND val_num IS NOT NULL
        ORDER BY timestamp ASC
    """

    meter = pd.read_sql_query(query, conn, params=(start_epoch,))
    conn.close()

    if meter.empty or len(meter) < 2:
        return None

    meter = meter.sort_values("epoch_s").reset_index(drop=True)
    diffs = meter["val_num"].diff().dropna()

    # Ignorujemy ujemne różnice jako reset licznika / błąd odczytu
    diffs = diffs.clip(lower=0.0)
    total = float(diffs.sum())

    return total if total > 0.0 else None


# --- PANEL BOCZNY ---

st.sidebar.header("⏱️ Zakres danych")

time_range_map = {
    "Ostatnie 6 godzin": 6,
    "Ostatnie 24 godziny": 24,
    "Ostatnie 3 dni": 72,
    "Ostatnie 7 dni": 168,
}

selected_range = st.sidebar.selectbox(
    "Wybierz zakres czasu:",
    list(time_range_map.keys()),
    index=1,
)

hours_back = time_range_map[selected_range]

st.sidebar.header("📊 Optymalizacja wykresów")

resample_map = {
    "Brak (surowe dane)": None,
    "Co 1 minutę": "1min",
    "Co 5 minut": "5min",
    "Co 15 minut": "15min",
}

selected_resample = st.sidebar.selectbox(
    "Agregacja punktów:",
    list(resample_map.keys()),
    index=1,
)

resample_rule = resample_map[selected_resample]

st.sidebar.header("⚙️ Kalkulator COP")

cos_phi = st.sidebar.slider(
    "Współczynnik mocy (cos φ)",
    0.80,
    1.00,
    0.92,
    0.01,
)

ac_curr_div = st.sidebar.selectbox(
    "Dzielnik prądu (ac_curr)",
    [1, 10, 100],
    index=1,
)

st.sidebar.header("🛠️ Kalibracja strat mocy")

standby_power_w = st.sidebar.number_input(
    "Pobór w spoczynku (elektronika) [W]",
    min_value=0,
    max_value=100,
    value=20,
    step=5,
)

active_power_w = st.sidebar.number_input(
    "Pobór pracy (wentylator, pompa obiegowa) [W]",
    min_value=0,
    max_value=300,
    value=140,
    step=10,
)

st.sidebar.header("🧮 Dokładność COP/SCOP")

flow_scale = st.sidebar.number_input(
    "Skala przepływu (flow_rate/10 × skala)",
    min_value=0.2,
    max_value=5.0,
    value=1.0,
    step=0.01,
)

flow_offset_m3h = st.sidebar.number_input(
    "Offset przepływu [m³/h]",
    min_value=-1.0,
    max_value=1.0,
    value=0.0,
    step=0.01,
)

power_scale = st.sidebar.number_input(
    "Skala mocy elektrycznej (V × I × cos φ)",
    min_value=0.5,
    max_value=2.0,
    value=1.0,
    step=0.01,
)

power_offset_kw = st.sidebar.number_input(
    "Offset mocy elektrycznej [kW]",
    min_value=-0.5,
    max_value=0.5,
    value=0.0,
    step=0.01,
)

include_fixed_loads = st.sidebar.checkbox(
    "Doliczaj stałe odbiory (standby + pompa/wentylator)",
    value=True,
)

include_standby_in_scop = st.sidebar.checkbox(
    "Doliczaj energię standby do SCOP całkowitego",
    value=True,
)

max_gap_min = st.sidebar.slider(
    "Maksymalny gap integracji [min]",
    min_value=5,
    max_value=60,
    value=20,
    step=5,
)

min_stable_s = st.sidebar.slider(
    "Minimalny czas stabilnej pracy dla COP chwilowego [s]",
    min_value=0,
    max_value=600,
    value=120,
    step=30,
)

delta_filter = st.sidebar.selectbox(
    "Filtr ΔT",
    options=[
        "Brak",
        "Mediana 3 próbki",
        "Średnia 2 min",
    ],
    index=1,
)

glycol_percent = st.sidebar.slider(
    "Przybliżona zawartość glikolu [%]",
    min_value=0,
    max_value=50,
    value=0,
    step=5,
)

if st.button("🔄 Odśwież dane"):
    st.rerun()

# --- ŁADOWANIE DANYCH ---

df = load_data(hours_back)
meter_energy_total = load_energy_meter_total(hours_back)

if df.empty:
    st.info(f"Brak danych z ostatnich {hours_back} godzin w bazie.")
    st.stop()

# --- NORMALIZACJA WARTOSCI ---

df["code"] = df["code"].astype(str).str.strip()

df["val_combined"] = df["val_num"]

bool_map = {
    "True": 1.0,
    "true": 1.0,
    "1": 1.0,
    "1.0": 1.0,
    "False": 0.0,
    "false": 0.0,
    "0": 1.0 if False else 0.0,
    "0.0": 0.0,
}

mask_str = df["val_combined"].isna() & df["val_str"].notna()

if mask_str.any():
    df.loc[mask_str, "val_combined"] = (
        df.loc[mask_str, "val_str"]
        .astype(str)
        .str.strip()
        .map(bool_map)
    )

# Jeśli val_str nie jest booleanem, spróbuj przekonwertować na liczbę
still_na = df["val_combined"].isna() & df["val_str"].notna()

if still_na.any():
    df.loc[still_na, "val_combined"] = pd.to_numeric(
        df.loc[still_na, "val_str"].astype(str).str.strip(),
        errors="coerce",
    )

# --- PIVOT ---

df_pivot = df.pivot_table(
    index="czas",
    columns="code",
    values="val_combined",
    aggfunc="first",
).reset_index()

if df_pivot.empty:
    st.info("Brak danych liczbowych do analizy.")
    st.stop()

df_pivot["czas"] = pd.to_datetime(df_pivot["czas"])
df_pivot = df_pivot.sort_values("czas")

needed_cols = [
    "out_water_temp",
    "in_water_temp",
    "tank_temp",
    "flow_rate",
    "ac_vol",
    "ac_curr",
    "comp_freq",
    "disc_temp",
    "amb_temp",
    "valve",
    "heat_temp_set",
    "defrost",
]

for col in needed_cols:
    if col not in df_pivot.columns:
        df_pivot[col] = np.nan
    else:
        df_pivot[col] = df_pivot[col].ffill()

# Domyślne wartości dla kluczowych pól
df_pivot["valve"] = df_pivot["valve"].fillna(0).astype(float)
df_pivot["defrost"] = df_pivot["defrost"].fillna(0)

# --- RESAMPLE ---

if resample_rule:
    df_pivot = df_pivot.set_index("czas").resample(resample_rule).agg(
        {
            "out_water_temp": "mean",
            "in_water_temp": "mean",
            "tank_temp": "mean",
            "flow_rate": "mean",
            "ac_vol": "mean",
            "ac_curr": "mean",
            "comp_freq": "mean",
            "disc_temp": "mean",
            "amb_temp": "mean",
            "heat_temp_set": "last",
            "valve": "mean",
            "defrost": "max",
        }
    ).reset_index()

    for col in needed_cols:
        df_pivot[col] = df_pivot[col].ffill()

# --- OBLICZENIA FIZYCZNE ---

# Czas UNIX w sekundach - najlepszy do integracji energii
df_pivot["epoch_s"] = df_pivot["czas"].astype("int64") // 1_000_000_000

# Czyszczenie oczywistych outlierów
df_pivot["ac_vol"] = clip_outliers(df_pivot["ac_vol"], 170, 265)
df_pivot["ac_curr"] = clip_outliers(df_pivot["ac_curr"], 0, 100 * ac_curr_div)
df_pivot["flow_rate"] = clip_outliers(df_pivot["flow_rate"], 0, 1000)

for col in [
    "out_water_temp",
    "in_water_temp",
    "tank_temp",
    "amb_temp",
    "disc_temp",
    "back_temp",
]:
    if col in df_pivot.columns:
        df_pivot[col] = clip_outliers(df_pivot[col], -30, 95)

# Uzupełnienie braków dla pól elektrycznych/hydraulicznych
df_pivot["ac_vol"] = df_pivot["ac_vol"].ffill().fillna(230.0)
df_pivot["ac_curr"] = df_pivot["ac_curr"].fillna(0.0)
df_pivot["flow_rate"] = df_pivot["flow_rate"].fillna(0.0)
df_pivot["comp_freq"] = df_pivot["comp_freq"].fillna(0.0)
df_pivot["valve"] = df_pivot["valve"].fillna(0.0)
df_pivot["defrost"] = df_pivot["defrost"].fillna(0.0)

# Prąd
curr_a = (df_pivot["ac_curr"] / ac_curr_div).clip(lower=0.0)

# Przepływ skalibrowany
df_pivot["flow_m3h"] = (df_pivot["flow_rate"] / 10.0) * flow_scale + flow_offset_m3h
df_pivot["flow_m3h"] = df_pivot["flow_m3h"].clip(lower=0.0)

# Delikatne wygładzenie przepływu
df_pivot["flow_m3h"] = df_pivot["flow_m3h"].rolling(3, min_periods=1).median()

# ΔT z opcjonalnym filtrem
df_pivot["delta_t_raw"] = df_pivot["out_water_temp"] - df_pivot["in_water_temp"]

if delta_filter == "Mediana 3 próbki":
    df_pivot["delta_t"] = df_pivot["delta_t_raw"].rolling(3, min_periods=1).median()
elif delta_filter == "Średnia 2 min":
    tmp = df_pivot.set_index("czas")
    df_pivot["delta_t"] = (
        tmp["delta_t_raw"]
        .rolling("120s", min_periods=1)
        .mean()
        .to_numpy()
    )
else:
    df_pivot["delta_t"] = df_pivot["delta_t_raw"]

# Moc cieplna
# Dla wody: 1 m³/h × 1 K ≈ 1.163 kW
# Przybliżona korekta dla glikolu
glycol_factor = 1.0 - (0.002 * glycol_percent)
water_factor = 1.163 * glycol_factor

df_pivot["P_th_kw"] = df_pivot["flow_m3h"] * df_pivot["delta_t"] * water_factor
df_pivot["P_th_kw"] = df_pivot["P_th_kw"].clip(lower=-3.0, upper=30.0)

# Moc elektryczna szacowana z V × I × cos φ
raw_p_el_kw = (df_pivot["ac_vol"] * curr_a * cos_phi) / 1000.0
raw_p_el_kw = raw_p_el_kw.clip(lower=0.0)

# Kalibracja mocy elektrycznej
df_pivot["P_el_measured_kw"] = (raw_p_el_kw.fillna(0.0) * power_scale) + power_offset_kw
df_pivot["P_el_measured_kw"] = df_pivot["P_el_measured_kw"].clip(lower=0.0)

# Stany pracy
comp_freq = df_pivot["comp_freq"].fillna(0.0)
comp_on = (comp_freq > 3.0) | (curr_a > 0.15)

defrost_on = (
    pd.to_numeric(df_pivot["defrost"], errors="coerce")
    .fillna(0.0)
    .astype(float)
    .gt(0.5)
)

# Stałe odbiory
# Dodawaj tylko wtedy, gdy ac_curr nie zawiera już tych odbiorników.
if include_fixed_loads:
    fixed_kw = (standby_power_w / 1000.0) + np.where(
        comp_on | defrost_on,
        active_power_w / 1000.0,
        0.0,
    )
else:
    fixed_kw = 0.0

df_pivot["P_el_kw"] = df_pivot["P_el_measured_kw"] + fixed_kw
df_pivot["P_el_kw"] = df_pivot["P_el_kw"].clip(lower=0.0, upper=20.0)

# Tryb pracy
mode_bool = df_pivot["valve"] >= 0.5
df_pivot["Tryb"] = np.where(mode_bool, "CWU", "CO")

# Czas pracy dla stabilności COP chwilowego
df_pivot["comp_group"] = (comp_on != comp_on.shift()).cumsum()
df_pivot["runtime_s"] = (
    df_pivot["epoch_s"]
    - df_pivot.groupby("comp_group")["epoch_s"].transform("first")
)

df_pivot["mode_group"] = (mode_bool != mode_bool.shift()).cumsum()
df_pivot["mode_runtime_s"] = (
    df_pivot["epoch_s"]
    - df_pivot.groupby("mode_group")["epoch_s"].transform("first")
)

# Warunki poprawności hydrauliki
hydraulic_ok = (
    (df_pivot["flow_m3h"] > 0.15)
    & (df_pivot["delta_t"] > 0.3)
    & (df_pivot["delta_t"] < 10.0)
    & df_pivot["out_water_temp"].notna()
    & df_pivot["in_water_temp"].notna()
)

electrical_ok = (
    (df_pivot["P_el_kw"] > 0.05)
    & df_pivot["ac_vol"].notna()
    & df_pivot["ac_curr"].notna()
)

# COP chwilowy tylko dla stabilnych warunków
stable_for_cop = (
    comp_on
    & electrical_ok
    & hydraulic_ok
    & (~defrost_on)
    & (df_pivot["runtime_s"] >= min_stable_s)
    & (df_pivot["mode_runtime_s"] >= min_stable_s)
)

df_pivot["COP_raw"] = np.where(
    (df_pivot["P_el_kw"] > 0.03) & (df_pivot["P_th_kw"] > 0.0),
    df_pivot["P_th_kw"] / df_pivot["P_el_kw"],
    np.nan,
)

# Fizyczne ograniczenie COP
df_pivot["COP_raw"] = df_pivot["COP_raw"].mask(
    (df_pivot["COP_raw"] < 0.5) | (df_pivot["COP_raw"] > 10.0)
)

# COP do wyświetlenia
df_pivot["COP"] = np.where(stable_for_cop, df_pivot["COP_raw"], np.nan)

# --- INTEGRACJA ENERGII ---

max_gap_s = max_gap_min * 60

dt_s = df_pivot["epoch_s"].diff().fillna(0).clip(lower=0)
gap_ok = (dt_s > 0) & (dt_s <= max_gap_s)
dt_h = np.where(gap_ok, dt_s / 3600.0, 0.0)

# Energia cieplna
# Dla defrostu dopuszczamy ujemne P_th, jeśli delta_t jest ujemna.
P_th_energy = df_pivot["P_th_kw"].where(hydraulic_ok | defrost_on, 0.0)
P_th_energy = P_th_energy.fillna(0.0).clip(lower=-3.0, upper=30.0)

# Energia elektryczna
P_el_energy = df_pivot["P_el_kw"].fillna(0.0)

if not include_standby_in_scop:
    # Jeśli użytkownik nie chce standby, zostawiamy przynajmniej compressor/defrost
    P_el_energy = P_el_energy.where(comp_on | defrost_on, 0.0)

# Integracja trapezowa: średnia mocy z poprzedniego i bieżącego punktu
P_th_avg = P_th_energy.rolling(2, min_periods=1).mean()
P_el_avg = P_el_energy.rolling(2, min_periods=1).mean()

df_pivot["E_th_kwh"] = np.where(gap_ok, P_th_avg * dt_h, 0.0)
df_pivot["E_el_kwh"] = np.where(gap_ok, P_el_avg * dt_h, 0.0)

# Przypisanie energii do trybu CO/CWU
# Interwał należy do trybu z poprzedniego wiersza.
# Jeśli tryb zmienił się w tym interwale, nie przypisujemy go jednoznacznie.
mode_prev = df_pivot["Tryb"].shift(1)
mode_changed = df_pivot["Tryb"] != mode_prev
interval_mode = mode_prev.where(~mode_changed, np.nan)

df_pivot["E_th_co_kwh"] = np.where(interval_mode == "CO", df_pivot["E_th_kwh"], 0.0)
df_pivot["E_th_cwu_kwh"] = np.where(interval_mode == "CWU", df_pivot["E_th_kwh"], 0.0)

df_pivot["E_el_co_kwh"] = np.where(interval_mode == "CO", df_pivot["E_el_kwh"], 0.0)
df_pivot["E_el_cwu_kwh"] = np.where(interval_mode == "CWU", df_pivot["E_el_kwh"], 0.0)

# Kolumny do agregacji
df_pivot["E_el_co_row"] = df_pivot["E_el_co_kwh"]
df_pivot["E_el_cwu_row"] = df_pivot["E_el_cwu_kwh"]
df_pivot["E_th_co_row"] = df_pivot["E_th_co_kwh"]
df_pivot["E_th_cwu_row"] = df_pivot["E_th_cwu_kwh"]

df_pivot["E_el_row"] = df_pivot["E_el_kwh"]
df_pivot["E_th_row"] = df_pivot["E_th_kwh"]

# --- SCOP ---

e_th_total = float(df_pivot["E_th_kwh"].sum())
e_el_total_estimated = float(df_pivot["E_el_kwh"].sum())

e_th_co = float(df_pivot["E_th_co_kwh"].sum())
e_el_co = float(df_pivot["E_el_co_kwh"].sum())

e_th_cwu = float(df_pivot["E_th_cwu_kwh"].sum())
e_el_cwu = float(df_pivot["E_el_cwu_kwh"].sum())

scop_co = (e_th_co / e_el_co) if e_el_co > 0 else 0.0
scop_cwu = (e_th_cwu / e_el_cwu) if e_el_cwu > 0 else 0.0
scop_total_estimated = (e_th_total / e_el_total_estimated) if e_el_total_estimated > 0 else 0.0

# Jeśli dostępny jest ręczny licznik energii, użyj go jako dokładniejszego
# mianownika dla SCOP całkowitego.
meter_available = meter_energy_total is not None and meter_energy_total > 0.01

if meter_available:
    e_el_total_source = meter_energy_total
    scop_total = (e_th_total / e_el_total_source) if e_el_total_source > 0 else 0.0
else:
    e_el_total_source = e_el_total_estimated
    scop_total = scop_total_estimated

# --- DEFROST ---

df_pivot["defrost_num"] = defrost_on.astype(int)

df_pivot["defrost_start"] = (
    (df_pivot["defrost_num"] == 1)
    & (df_pivot["defrost_num"].shift(1, fill_value=0) == 0)
).astype(int)

# --- AGREGACJA DZIENNA ---

df_pivot["dzien"] = df_pivot["czas"].dt.date

daily_df = df_pivot.groupby("dzien").agg(
    {
        "E_el_co_row": "sum",
        "E_el_cwu_row": "sum",
        "E_el_row": "sum",
        "E_th_co_row": "sum",
        "E_th_cwu_row": "sum",
        "E_th_row": "sum",
        "amb_temp": "mean",
        "defrost_start": "sum",
    }
).reset_index()

daily_df["E_el_total"] = daily_df["E_el_row"]
daily_df["E_th_total"] = daily_df["E_th_row"]

daily_df["SCOP_dzienny"] = np.where(
    daily_df["E_el_total"] > 0,
    daily_df["E_th_total"] / daily_df["E_el_total"],
    np.nan,
)

num_days = max(len(daily_df), 1)

avg_daily_el_co = daily_df["E_el_co_row"].sum() / num_days
avg_daily_el_cwu = daily_df["E_el_cwu_row"].sum() / num_days
avg_amb_temp = df_pivot["amb_temp"].mean()
total_defrosts = int(daily_df["defrost_start"].sum())

# --- ZAKŁADKI ---

tab_main, tab_scop, tab_diag = st.tabs(
    [
        "📊 Panel Główny",
        "🏆 Bilans Energetyczny & SCOP",
        "🏥 Diagnostyka Pompy",
    ]
)

# ZAKŁADKA 1
with tab_main:
    latest_df = df.drop_duplicates(subset=["code"], keep="last")

    def get_val(c: str):
        row = latest_df[latest_df["code"] == c]

        if not row.empty:
            v_num = row["val_num"].values[0]

            if pd.notnull(v_num):
                if (
                    "temp" in c
                    or c in [
                        "tidr",
                        "back_temp",
                        "heat_temp_set",
                        "hot_water_temp_set",
                        "cool_temp_set",
                    ]
                ):
                    return f"{float(v_num):.1f} °C"

                return f"{float(v_num):.1f}"

            v_str = row["val_str"].values[0]
            return str(v_str)

        return "N/A"

    # COP chwilowy: lepiej użyć krótkiej mediany niż ostatniego surowego punktu
    cop_series = df_pivot.set_index("czas")["COP"].dropna()

    if not cop_series.empty:
        latest_cop = cop_series.rolling("10min", min_periods=1).median().iloc[-1]
    else:
        latest_cop = 0.0

    latest_p_th = float(df_pivot["P_th_kw"].fillna(0.0).iloc[-1]) if not df_pivot.empty else 0.0
    latest_p_el = float(df_pivot["P_el_kw"].fillna(0.0).iloc[-1]) if not df_pivot.empty else 0.0
    latest_flow = float(df_pivot["flow_m3h"].fillna(0.0).iloc[-1]) if not df_pivot.empty else 0.0
    current_mode = df_pivot["Tryb"].iloc[-1] if not df_pivot.empty else "CO"

    c1, c2, c3, c4, c5, c6 = st.columns(6)

    c1.metric("Woda CWU", get_val("tank_temp"))
    c2.metric("Powrót CO", get_val("in_water_temp"))
    c3.metric("Zasilanie CO", get_val("out_water_temp"))
    c4.metric("🎯 Nastawa CO", get_val("heat_temp_set"))
    c5.metric(
        "Przepływ",
        f"{latest_flow:.1f} m³/h",
        delta=f"{latest_flow * 1000 / 60:.1f} L/min",
    )
    c6.metric(
        "📊 Chwilowe COP",
        f"{latest_cop:.2f}",
        delta=f"Tryb: {current_mode}",
    )

    cp1, cp2 = st.columns(2)

    cp1.metric("🔥 Moc cieplna (P_th)", f"{latest_p_th:.2f} kW")
    cp2.metric("⚡ Pobór prądu (P_el)", f"{latest_p_el:.2f} kW")

    st.markdown("---")

    st.subheader("📊 Chwilowe COP z podziałem na tryb CO / CWU")

    cop_chart_df = df_pivot.dropna(subset=["COP"])

    if cop_chart_df.empty:
        st.info("Brak stabilnych punktów COP w wybranym zakresie.")
    else:
        fig_cop = px.line(
            cop_chart_df,
            x="czas",
            y="COP",
            color="Tryb",
            color_discrete_map={
                "CO": "#2ECC71",
                "CWU": "#E67E22",
            },
            title="Wykres chwilowego COP (zielony = CO, pomarańczowy = CWU)",
            markers=(resample_rule is not None),
        )
        fig_cop.update_layout(hovermode="x unified")
        st.plotly_chart(fig_cop, use_container_width=True)

    st.subheader("📈 Przebieg wybranych parametrów")

    all_codes = sorted(df["code"].unique().tolist())

    default_temps = [
        c
        for c in [
            "tank_temp",
            "in_water_temp",
            "out_water_temp",
            "heat_temp_set",
            "amb_temp",
        ]
        if c in all_codes
    ]

    selected_temps = st.multiselect(
        "Wybierz parametry do wyświetlenia:",
        options=all_codes,
        default=default_temps,
        format_func=get_param_label,
    )

    if selected_temps:
        temp_df = df[
            df["code"].isin(selected_temps)
            & df["val_combined"].notnull()
        ].copy()

        if resample_rule:
            temp_df["czas"] = pd.to_datetime(temp_df["czas"])
            temp_df = (
                temp_df.groupby(
                    [
                        "code",
                        pd.Grouper(key="czas", freq=resample_rule),
                    ]
                )["val_combined"]
                .mean()
                .reset_index()
            )

        temp_df["Parametr"] = temp_df["code"].map(
            lambda c: PARAM_INFO.get(c, {}).get("label", c)
        )
        temp_df["Opis"] = temp_df["code"].map(
            lambda c: PARAM_INFO.get(c, {}).get("desc", "Brak opisu")
        )

        fig_temp = px.line(
            temp_df,
            x="czas",
            y="val_combined",
            color="Parametr",
            hover_data={
                "Parametr": True,
                "Opis": True,
                "val_combined": ":.1f",
                "code": False,
            },
            title="Wykres wartości parametrów w czasie",
        )
        fig_temp.update_layout(hovermode="x unified")
        st.plotly_chart(fig_temp, use_container_width=True)

# ZAKŁADKA 2: BILANS ENERGETYCZNY & SCOP
with tab_scop:
    st.header("🏆 Podsumowanie Efektywności SCOP i Zużycia Energii")

    if meter_available:
        st.success(
            "Wykryto ręczny licznik energii (energy_kwh). "
            "SCOP całkowite używa energii z licznika jako dokładniejszego mianownika."
        )
        st.caption(
            f"Energia z licznika: {meter_energy_total:.2f} kWh | "
            f"Szacowana energia z danych pompy: {e_el_total_estimated:.2f} kWh | "
            f"Szacowany SCOP bez licznika: {scop_total_estimated:.2f}"
        )
    else:
        st.info(
            "Brak wystarczających odczytów zewnętrznego/licznika ręcznego (energy_kwh) "
            "w wybranym zakresie. SCOP całkowite jest szacowane z V × I × cos φ."
        )

    sc_col1, sc_col2, sc_col3 = st.columns(3)

    sc_col1.metric(
        "🌟 SCOP Całkowite",
        f"{scop_total:.2f}",
        delta="Licznik energii" if meter_available else "Szacunek",
        delta_color="off",
    )

    sc_col2.metric(
        "🏠 SCOP dla CO (Ogrzewanie)",
        f"{scop_co:.2f}",
        delta="Tryb CO",
        delta_color="off",
    )

    sc_col3.metric(
        "🚿 SCOP dla CWU (Ciepła Woda)",
        f"{scop_cwu:.2f}",
        delta="Tryb CWU",
        delta_color="off",
    )

    st.markdown("### 📊 Statystyki Średniodobowe i Odszranianie")

    d_col1, d_col2, d_col3, d_col4 = st.columns(4)

    d_col1.metric(
        "⚡ Śr. dzienne zużycie CO",
        f"{avg_daily_el_co:.2f} kWh/dzień",
    )
    d_col2.metric(
        "⚡ Śr. dzienne zużycie CWU",
        f"{avg_daily_el_cwu:.2f} kWh/dzień",
    )
    d_col3.metric(
        "🌡️ Średniodobowa temp. zewn.",
        f"{avg_amb_temp:.1f} °C" if not np.isnan(avg_amb_temp) else "Brak danych",
    )
    d_col4.metric(
        "❄️ Liczba defrostów (okres)",
        f"{total_defrosts}",
    )

    st.markdown("---")

    st.subheader("⚡ Zużycie Prądu i Wygenerowane Ciepło [kWh]")

    summary_data = {
        "Obieg / Tryb": [
            "🏠 Ogrzewanie (CO)",
            "🚿 Ciepła Woda (CWU)",
            "TOTAL (Łącznie)",
        ],
        "Pobrana Energia El. [kWh]": [
            f"{e_el_co:.2f}",
            f"{e_el_cwu:.2f}",
            f"{e_el_total_source:.2f}",
        ],
        "Oddane Ciepło [kWh]": [
            f"{e_th_co:.2f}",
            f"{e_th_cwu:.2f}",
            f"{e_th_total:.2f}",
        ],
        "Średnie SCOP": [
            f"{scop_co:.2f}",
            f"{scop_cwu:.2f}",
            f"{scop_total:.2f}",
        ],
    }

    st.table(pd.DataFrame(summary_data))

    if meter_available:
        st.caption(
            "Uwaga: energia elektryczna dla CO/CWU jest szacunkowa i może nie obejmować "
            "całości standby, przejść trybów lub defrostów. TOTAL używa licznika energii."
        )

    fig_bar = go.Figure(
        data=[
            go.Bar(
                name="Prąd pobrany [kWh]",
                x=["Ogrzewanie CO", "Ciepła Woda CWU"],
                y=[e_el_co, e_el_cwu],
                marker_color="#3498DB",
            ),
            go.Bar(
                name="Ciepło oddane [kWh]",
                x=["Ogrzewanie CO", "Ciepła Woda CWU"],
                y=[e_th_co, e_th_cwu],
                marker_color="#E74C3C",
            ),
        ]
    )

    fig_bar.update_layout(
        barmode="group",
        title="Porównanie energii pobranej do oddanej według trybu pracy",
    )

    st.plotly_chart(fig_bar, use_container_width=True)

    st.markdown("---")

    st.subheader("📅 Dzienny Bilans Zużycia, Temperatur i Defrostów")

    daily_display = daily_df[
        [
            "dzien",
            "amb_temp",
            "E_el_co_row",
            "E_el_cwu_row",
            "E_el_row",
            "defrost_start",
            "SCOP_dzienny",
        ]
    ].copy()

    daily_display.columns = [
        "Data",
        "Śr. Temp Zewn. [°C]",
        "Prąd CO [kWh]",
        "Prąd CWU [kWh]",
        "Prąd Łącznie [kWh]",
        "Liczba Defrostów",
        "SCOP Dzienny",
    ]

    daily_display["Śr. Temp Zewn. [°C]"] = daily_display["Śr. Temp Zewn. [°C]"].round(1)
    daily_display["Prąd CO [kWh]"] = daily_display["Prąd CO [kWh]"].round(2)
    daily_display["Prąd CWU [kWh]"] = daily_display["Prąd CWU [kWh]"].round(2)
    daily_display["Prąd Łącznie [kWh]"] = daily_display["Prąd Łącznie [kWh]"].round(2)
    daily_display["SCOP Dzienny"] = daily_display["SCOP Dzienny"].round(2)

    st.dataframe(daily_display, use_container_width=True)

# ZAKŁADKA 3: DIAGNOSTYKA
with tab_diag:
    st.header("🏥 Centrum Diagnostyczne Pompy Ciepła")

    st.subheader("⚠️ Status Pracy i Ostrzeżenia")

    col_a1, col_a2, col_a3 = st.columns(3)

    last_disc = (
        df_pivot["disc_temp"].dropna().iloc[-1]
        if not df_pivot["disc_temp"].dropna().empty
        else None
    )

    with col_a1:
        if last_disc is not None and last_disc >= 90.0:
            st.error(
                f"🔴 **KRYTYCZNA TEMP. TŁOCZENIA:** {last_disc:.1f}°C\n"
                "Ryzyko przegrzania sprężarki!"
            )
        elif last_disc is not None and last_disc >= 80.0:
            st.warning(
                f"🟡 **Podwyższona temp. tłoczenia:** {last_disc:.1f}°C"
            )
        elif last_disc is not None:
            st.success(
                f"🟢 **Temp. tłoczenia w normie:** {last_disc:.1f}°C"
            )
        else:
            st.info("⚪ Brak danych temp. tłoczenia")

    last_dt = (
        df_pivot["delta_t"].dropna().iloc[-1]
        if not df_pivot["delta_t"].dropna().empty
        else None
    )

    is_pumping = (
        float(df_pivot["P_el_kw"].fillna(0.0).iloc[-1]) > 0.2
        if not df_pivot.empty
        else False
    )

    with col_a2:
        if is_pumping and last_dt is not None:
            if last_dt < 2.0:
                st.warning(
                    f"🟡 **Za małe ΔT ({last_dt:.1f}°C):** "
                    "Przepływ wody za duży lub brak odbioru ciepła."
                )
            elif last_dt > 8.0:
                st.warning(
                    f"🟡 **Za duże ΔT ({last_dt:.1f}°C):** "
                    "Zbyt mały przepływ wody (sprawdź pompę/filtry)."
                )
            else:
                st.success(
                    f"🟢 **Różnica ΔT w normie:** {last_dt:.1f}°C "
                    "(Idealnie: 3-6°C)"
                )
        else:
            st.info("⚪ Pompa w stanie spoczynku (ΔT pauza)")

    is_comp_on = df_pivot["comp_freq"].fillna(0.0) > 5.0
    starts_count = int(
        (is_comp_on & (~is_comp_on.shift(1, fill_value=False))).sum()
    )

    with col_a3:
        if starts_count > 15:
            st.warning(
                f"🟡 **Wykryto taktowanie!** "
                f"Liczba startów sprężarki: **{starts_count}** w wybranym oknie."
            )
        else:
            st.success(
                f"🟢 **Cykliczność w normie:** "
                f"Liczba startów sprężarki: **{starts_count}**"
            )

    st.markdown("---")

    st.subheader("1️⃣ Odbiór ciepła przez instalację (Różnica temperatur ΔT)")

    fig_dt = go.Figure()

    fig_dt.add_trace(
        go.Scatter(
            x=df_pivot["czas"],
            y=df_pivot["delta_t"],
            mode="lines",
            name="Różnica ΔT (°C)",
            line=dict(color="#3498DB", width=2),
        )
    )

    fig_dt.add_hrect(
        y0=3.0,
        y1=7.0,
        fillcolor="Green",
        opacity=0.15,
        line_width=0,
        annotation_text="Strefa optymalna (3 - 7 °C)",
        annotation_position="top left",
    )

    fig_dt.update_layout(
        hovermode="x unified",
        xaxis_title="Czas",
        yaxis_title="ΔT (°C)",
    )

    st.plotly_chart(fig_dt, use_container_width=True)

    st.subheader("2️⃣ Bezpieczeństwo Sprężarki (Temperatura Tłoczenia Discharge)")

    fig_disc = go.Figure()

    fig_disc.add_trace(
        go.Scatter(
            x=df_pivot["czas"],
            y=df_pivot["disc_temp"],
            mode="lines",
            name="Temp. Tłoczenia (°C)",
            line=dict(color="#E67E22", width=2),
        )
    )

    fig_disc.add_trace(
        go.Scatter(
            x=df_pivot["czas"],
            y=df_pivot["comp_freq"],
            mode="lines",
            name="Obroty sprężarki (Hz)",
            line=dict(color="#9B59B6", width=1.5, dash="dot"),
        )
    )

    fig_disc.add_hline(
        y=90.0,
        line_dash="dash",
        line_color="Red",
        annotation_text="Krytyczne 90°C",
        annotation_position="bottom right",
    )

    fig_disc.update_layout(
        hovermode="x unified",
        xaxis_title="Czas",
        yaxis_title="Wartość",
    )

    st.plotly_chart(fig_disc, use_container_width=True)
