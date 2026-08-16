import sqlite3
import datetime
import time
import pandas as pd
import numpy as np
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
from db import init_db, save_manual_energy_reading

# Inicjalizacja bazy danych
init_db()

# --- KONFIGURACJA STRONY ---
st.set_page_config(page_title="Monitor Pompy Ciepła", layout="wide", page_icon="🔥")

st.markdown("""
<style>
/* 1. Wygląd kafelków dla wszystkich metryk */
[data-testid="stMetric"] {
    background-color: #1E1E1E;
    border: 1px solid #333;
    border-radius: 10px;
    padding: 15px;
    box-shadow: 2px 2px 10px rgba(0,0,0,0.3);
}

/* 2. Układ siatki na telefonach */
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

DB_FILE = "/data/tuya_telemetry.db"
HEAT_PUMP_DEV_ID = "bf874f7ae72aca1fc23op0"
MANUAL_METER_DEV_ID = "licznikRęczny"

# --- SŁOWNIK METADANYCH PARAMETRÓW ---
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
    "Ostatni 1 dzień": 24,
    "Ostatnie 3 dni": 72,
    "Ostatnie 7 dni": 168
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

st.sidebar.header("⚙️ Kalkulator COP")
cos_phi = st.sidebar.slider("Współczynnik mocy (cos φ)", 0.80, 1.00, 1.00, 0.01)
ac_curr_div = st.sidebar.selectbox("Dzielnik prądu (ac_curr)", [1, 10, 100], index=1)

st.sidebar.header("🛠️ Kalibracja strat mocy")
standby_power_w = st.sidebar.number_input("Pobór w spoczynku (elektronika) [W]", min_value=0, max_value=100, value=20, step=5)
active_power_w = st.sidebar.number_input("Pobór pracy (wentylator, pompa obieg.) [W]", min_value=0, max_value=300, value=140, step=10)

# --- FUNKCJE BAZODANOWE ---
def load_data(hours: int) -> pd.DataFrame:
    conn = sqlite3.connect(DB_FILE)
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
    conn = sqlite3.connect(DB_FILE)
    query = f"""
        SELECT 
            timestamp,
            datetime(timestamp, 'unixepoch', 'localtime') as czas,
            val_num as stan_kwh
        FROM telemetry
        WHERE device_id = '{MANUAL_METER_DEV_ID}' AND code = 'energy_kwh'
        ORDER BY timestamp ASC
    """
    df_manual = pd.read_sql_query(query, conn)
    conn.close()
    return df_manual

def load_all_pump_power() -> pd.DataFrame:
    """Wczytuje surowy prąd i napięcie pompy z całej historii do porównania dziennego."""
    conn = sqlite3.connect(DB_FILE)
    query = f"""
        SELECT 
            datetime(timestamp, 'unixepoch', 'localtime') as czas,
            code, val_num
        FROM telemetry
        WHERE device_id = '{HEAT_PUMP_DEV_ID}'
          AND code IN ('ac_vol', 'ac_curr')
        ORDER BY timestamp ASC
    """
    df_p = pd.read_sql_query(query, conn)
    conn.close()
    return df_p

if st.button("🔄 Odśwież dane"):
    st.rerun()

df = load_data(hours_back)

# --- PRZETWARZANIE DANYCH TELEMETRII POMPY ---
df_pivot = pd.DataFrame()
daily_df = pd.DataFrame()
scop_total = 0.0
scop_co = 0.0
scop_cwu = 0.0
e_el_co = 0.0
e_el_cwu = 0.0
e_el_total = 0.0
e_th_co = 0.0
e_th_cwu = 0.0
e_th_total = 0.0
avg_daily_el_co = 0.0
avg_daily_el_cwu = 0.0
avg_amb_temp = np.nan
total_defrosts = 0

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

    # Obliczenia mocy
    curr_a = df_pivot["ac_curr"] / ac_curr_div
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

    df_pivot["defrost_num"] = df_pivot["defrost"].fillna(0).apply(lambda x: 1 if x else 0)
    df_pivot["defrost_start"] = ((df_pivot["defrost_num"] == 1) & (df_pivot["defrost_num"].shift(1, fill_value=0) == 0)).astype(int)

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
        "defrost_start": "sum"
    }).reset_index()

    daily_df["E_el_total"] = daily_df["E_el_co_row"] + daily_df["E_el_cwu_row"]
    daily_df["E_th_total"] = daily_df["E_th_co_row"] + daily_df["E_th_cwu_row"]
    daily_df["SCOP_dzienny"] = np.where(daily_df["E_el_total"] > 0, daily_df["E_th_total"] / daily_df["E_el_total"], np.nan)

    num_days = max(len(daily_df), 1)
    avg_daily_el_co = daily_df["E_el_co_row"].sum() / num_days
    avg_daily_el_cwu = daily_df["E_el_cwu_row"].sum() / num_days
    avg_amb_temp = df_pivot["amb_temp"].mean()
    total_defrosts = int(daily_df["defrost_start"].sum())

# --- DEFINICJA ZAKŁADEK ---
tab_main, tab_scop, tab_diag, tab_manual = st.tabs([
    "📊 Panel Główny", 
    "🏆 Bilans Energetyczny & SCOP", 
    "🏥 Diagnostyka Pompy", 
    "📝 Ręczny Licznik Energii"
])

# ==========================================
# ZAKŁADKA 1: PANEL GŁÓWNY
# ==========================================
with tab_main:
    if df.empty:
        st.info(f"Brak danych pompy ciepła z wybranego okresu ({selected_range}).")
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

        latest_cop = df_pivot["COP"].dropna().iloc[-1] if not df_pivot.empty and not df_pivot["COP"].dropna().empty else 0.0
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
        if not df_pivot.empty and not df_pivot.dropna(subset=["COP"]).empty:
            fig_cop = px.line(
                df_pivot.dropna(subset=["COP"]),
                x="czas", y="COP", color="Tryb",
                color_discrete_map={"CO": "#2ECC71", "CWU": "#E67E22"},
                title="Wykres chwilowego COP (Zielony = CO, Pomarańczowy = CWU)",
                markers=(resample_rule is not None)
            )
            fig_cop.update_layout(hovermode="x unified")
            st.plotly_chart(fig_cop, use_container_width=True)

        st.subheader("📈 Przebieg wybranych parametrów")
        all_codes = df["code"].unique().tolist()
        default_temps = [c for c in ["tank_temp", "in_water_temp", "out_water_temp", "heat_temp_set", "amb_temp"] if c in all_codes]
        selected_temps = st.multiselect("Wybierz parametry do wyświetlenia:", options=all_codes, default=default_temps, format_func=get_param_label)

        if selected_temps:
            temp_df = df[df["code"].isin(selected_temps) & df["val_num"].notnull()].copy()
            if resample_rule:
                temp_df["czas"] = pd.to_datetime(temp_df["czas"])
                temp_df = temp_df.groupby(["code", pd.Grouper(key="czas", freq=resample_rule)])["val_num"].mean().reset_index()

            temp_df["Parametr"] = temp_df["code"].map(lambda c: PARAM_INFO.get(c, {}).get("label", c))
            temp_df["Opis"] = temp_df["code"].map(lambda c: PARAM_INFO.get(c, {}).get("desc", "Brak opisu"))

            fig_temp = px.line(
                temp_df, x="czas", y="val_num", color="Parametr",
                hover_data={"Parametr": True, "Opis": True, "val_num": ":.1f", "code": False},
                title="Wykres wartości parametrów w czasie"
            )
            fig_temp.update_layout(hovermode="x unified")
            st.plotly_chart(fig_temp, use_container_width=True)

# ==========================================
# ZAKŁADKA 2: BILANS ENERGETYCZNY & SCOP
# ==========================================
with tab_scop:
    if df.empty:
        st.info("Brak danych do wyliczenia bilansu.")
    else:
        st.header("🏆 Podsumowanie Efektywności SCOP i Zużycia Energii")
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
        fig_bar.update_layout(barmode='group', title="Porównanie energii pobranej do oddanej według trybu pracy")
        st.plotly_chart(fig_bar, use_container_width=True)

        st.markdown("---")
        st.subheader("📅 Dzienny Bilans Zużycia, Temperatur i Defrostów")
        if not daily_df.empty:
            daily_display = daily_df[["dzień", "amb_temp", "E_el_co_row", "E_el_cwu_row", "E_el_total", "defrost_start", "SCOP_dzienny"]].copy()
            daily_display.columns = ["Data", "Śr. Temp Zewn. [°C]", "Prąd CO [kWh]", "Prąd CWU [kWh]", "Prąd Łącznie [kWh]", "Liczba Defrostów", "SCOP Dzienny"]
            daily_display["Śr. Temp Zewn. [°C]"] = daily_display["Śr. Temp Zewn. [°C]"].round(1)
            daily_display["Prąd CO [kWh]"] = daily_display["Prąd CO [kWh]"].round(2)
            daily_display["Prąd CWU [kWh]"] = daily_display["Prąd CWU [kWh]"].round(2)
            daily_display["Prąd Łącznie [kWh]"] = daily_display["Prąd Łącznie [kWh]"].round(2)
            daily_display["SCOP Dzienny"] = daily_display["SCOP Dzienny"].round(2)
            st.dataframe(daily_display, use_container_width=True, hide_index=True)

# ==========================================
# ZAKŁADKA 3: DIAGNOSTYKA
# ==========================================
with tab_diag:
    if df.empty:
        st.info("Brak danych diagnostycznych.")
    else:
        st.header("🏥 Centrum Diagnostyczne Pompy Ciepła")
        st.subheader("⚠️ Status Pracy i Ostrzeżenia")
        col_a1, col_a2, col_a3 = st.columns(3)

        last_disc = df_pivot["disc_temp"].dropna().iloc[-1] if not df_pivot.empty and not df_pivot["disc_temp"].dropna().empty else None
        with col_a1:
            if last_disc and last_disc >= 90.0:
                st.error(f"🔴 **KRYTYCZNA TEMP. TŁOCZENIA:** {last_disc:.1f}°C\nRyzyko przegrzania sprężarki!")
            elif last_disc and last_disc >= 80.0:
                st.warning(f"🟡 **Podwyższona temp. tłoczenia:** {last_disc:.1f}°C")
            elif last_disc:
                st.success(f"🟢 **Temp. tłoczenia w normie:** {last_disc:.1f}°C")
            else:
                st.info("⚪ Brak danych temp. tłoczenia")

        last_dt = df_pivot["delta_t"].dropna().iloc[-1] if not df_pivot.empty and not df_pivot["delta_t"].dropna().empty else None
        is_pumping = df_pivot["P_el_kw"].iloc[-1] > 0.2 if not df_pivot.empty else False
        with col_a2:
            if is_pumping and last_dt is not None:
                if last_dt < 2.0:
                    st.warning(f"🟡 **Za małe ΔT ({last_dt:.1f}°C):** Przepływ wody za duży lub brak odbioru ciepła.")
                elif last_dt > 8.0:
                    st.warning(f"🟡 **Za duże ΔT ({last_dt:.1f}°C):** Zbyt mały przepływ wody (sprawdź pompę/filtry).")
                else:
                    st.success(f"🟢 **Różnica ΔT w normie:** {last_dt:.1f}°C (Idealnie: 3-6°C)")
            else:
                st.info("⚪ Pompa w stanie spoczynku (ΔT pauza)")

        is_comp_on = df_pivot["comp_freq"] > 5 if not df_pivot.empty and "comp_freq" in df_pivot.columns else pd.Series([False])
        starts_count = (is_comp_on & (~is_comp_on.shift(1, fill_value=False))).sum()
        with col_a3:
            if starts_count > 15:
                st.warning(f"🟡 **Wykryto taktowanie!** Liczba startów sprężarki: **{starts_count}** w wybranym oknie.")
            else:
                st.success(f"🟢 **Cykliczność w normie:** Liczba startów sprężarki: **{starts_count}**")

        st.markdown("---")
        st.subheader("1️⃣ Odbiór ciepła przez instalację (Różnica temperatur ΔT)")
        if not df_pivot.empty:
            fig_dt = go.Figure()
            fig_dt.add_trace(go.Scatter(x=df_pivot["czas"], y=df_pivot["delta_t"], mode='lines', name='Różnica ΔT (°C)', line=dict(color='#3498DB', width=2)))
            fig_dt.add_hrect(y0=3.0, y1=7.0, fillcolor="Green", opacity=0.15, line_width=0, annotation_text="Strefa optymalna (3 - 7 °C)", annotation_position="top left")
            fig_dt.update_layout(hovermode="x unified", xaxis_title="Czas", yaxis_title="ΔT (°C)")
            st.plotly_chart(fig_dt, use_container_width=True)

        st.subheader("2️⃣ Bezpieczeństwo Sprężarki (Temperatura Tłoczenia Discharge)")
        if not df_pivot.empty:
            fig_disc = go.Figure()
            fig_disc.add_trace(go.Scatter(x=df_pivot["czas"], y=df_pivot["disc_temp"], mode='lines', name='Temp. Tłoczenia (°C)', line=dict(color='#E67E22', width=2)))
            fig_disc.add_trace(go.Scatter(x=df_pivot["czas"], y=df_pivot["comp_freq"], mode='lines', name='Obroty sprężarki (Hz)', line=dict(color='#9B59B6', width=1.5, dash='dot')))
            fig_disc.add_hline(y=90.0, line_dash="dash", line_color="Red", annotation_text="Krytyczne 90°C", annotation_position="bottom right")
            fig_disc.update_layout(hovermode="x unified", xaxis_title="Czas", yaxis_title="Wartość")
            st.plotly_chart(fig_disc, use_container_width=True)

# ==========================================
# ZAKŁADKA 4: RĘCZNY LICZNIK ENERGII
# ==========================================
with tab_manual:
    st.header("📝 Wprowadzanie i Analiza Stanu Fizycznego Licznika Energii")
    st.caption("Rejestracja wskazań podlicznika (urządzenie: `licznikRęczny`, parametr: `energy_kwh`).")

    # Inicjalizacja klucza wartości w sesji, aby móc go czyścić po zapisie
    if "meter_val_input" not in st.session_state:
        st.session_state["meter_val_input"] = ""

    with st.expander("➕ Dodaj nowy odczyt z licznika", expanded=True):
        col_form1, col_form2, col_form3 = st.columns([2, 2, 1])
        
        now_dt = datetime.datetime.now()
        with col_form1:
            input_date = st.date_input("Data odczytu", value=now_dt.date())
        with col_form2:
            input_time = st.time_input("Godzina odczytu", value=now_dt.time())
        with col_form3:
            meter_val_str = st.text_input("Stan licznika [kWh]", value=st.session_state["meter_val_input"], placeholder="np. 12450.5", key="input_raw_val")

        if st.button("💾 Zapisz odczyt do bazy", type="primary"):
            # Walidacja danych
            clean_str = meter_val_str.strip().replace(",", ".")
            if not clean_str:
                st.error("❌ Błąd: Pole stanu licznika nie może być puste!")
            else:
                try:
                    val_float = float(clean_str)
                    if val_float <= 0:
                        st.error("❌ Błąd: Stan licznika musi być większy od 0.")
                    else:
                        chosen_dt = datetime.datetime.combine(input_date, input_time)
                        chosen_ts = int(chosen_dt.timestamp())

                        saved = save_manual_energy_reading(val_float, chosen_ts)
                        if saved:
                            st.success(f"✅ Zapisano pomyślnie: **{val_float:.2f} kWh** ({chosen_dt.strftime('%Y-%m-%d %H:%M')})")
                            st.session_state["meter_val_input"] = ""
                            time.sleep(0.8)
                            st.rerun()
                        else:
                            st.warning("⚠️ Ten odczyt lub dokładny timestamp już istnieje w bazie danych!")
                except ValueError:
                    st.error("❌ Błąd: Wpisana wartość nie jest prawidłową liczbą!")

    st.markdown("---")

    # Wczytanie historii odczytów
    df_manual_raw = load_manual_readings()

    if df_manual_raw.empty:
        st.info("Brak wpisów ręcznych w bazie danych. Dodaj pierwszy odczyt powyżej.")
    else:
        df_m = df_manual_raw.copy()
        df_m["czas"] = pd.to_datetime(df_m["czas"])
        df_m = df_m.sort_values("czas").reset_index(drop=True)

        # Różnica względem poprzedniego odczytu
        df_m["Różnica [kWh]"] = df_m["stan_kwh"].diff()
        df_m["dt_dni"] = df_m["timestamp"].diff() / 86400.0
        df_m["Śr. dzienne [kWh/d]"] = np.where(df_m["dt_dni"] > 0, df_m["Różnica [kWh]"] / df_m["dt_dni"], np.nan)

        st.subheader("📋 Tabela zarejestrowanych odczytów")
        display_m = df_m[["czas", "stan_kwh", "Różnica [kWh]", "Śr. dzienne [kWh/d]"]].copy()
        display_m.columns = ["Data i Godzina", "Stan Licznika [kWh]", "Różnica od poprz. [kWh]", "Średnio na dzień [kWh/d]"]
        display_m["Stan Licznika [kWh]"] = display_m["Stan Licznika [kWh]"].map(lambda x: f"{x:.2f}")
        display_m["Różnica od poprz. [kWh]"] = display_m["Różnica od poprz. [kWh]"].map(lambda x: f"+{x:.2f}" if pd.notnull(x) else "-")
        display_m["Średnio na dzień [kWh/d]"] = display_m["Średnio na dzień [kWh/d]"].map(lambda x: f"{x:.2f}" if pd.notnull(x) else "-")
        st.dataframe(display_m.iloc[::-1], use_container_width=True, hide_index=True)

        # Wyliczenie zużycia dziennego z interpolacją (estymacją) brakujących dni
        st.markdown("---")
        st.subheader("📈 Wykres dziennego zużycia energii (Licznik Fizyczny vs Pompa Ciepła)")

        # Ciągła siatka dzienna od pierwszego do ostatniego odczytu ręcznego
        min_date = df_m["czas"].min().date()
        max_date = max(df_m["czas"].max().date(), datetime.date.today())
        
        full_date_idx = pd.date_range(start=min_date, end=max_date, freq="D")
        daily_meter_df = pd.DataFrame({"Data": full_date_idx})
        daily_meter_df["czas_ts"] = daily_meter_df["Data"].apply(lambda d: int(datetime.datetime.combine(d, datetime.time(12, 0)).timestamp()))

        # Interpolacja liniowa stanu licznika na każdy dzień (godz. 12:00)
        daily_meter_df["stan_interp"] = np.interp(
            daily_meter_df["czas_ts"],
            df_m["timestamp"],
            df_m["stan_kwh"]
        )
        daily_meter_df["Zużycie_Licznik_Fizyczny"] = daily_meter_df["stan_interp"].diff()
        daily_meter_df.loc[daily_meter_df["Zużycie_Licznik_Fizyczny"] < 0, "Zużycie_Licznik_Fizyczny"] = 0.0

        # Wczytanie wyliczeń zużycia pompy ciepła dla tych samych dni
        df_pump_raw = load_all_pump_power()
        daily_pump_energy = {}
        if not df_pump_raw.empty:
            df_p_piv = df_pump_raw.pivot_table(index="czas", columns="code", values="val_num", aggfunc="first").reset_index()
            df_p_piv["czas"] = pd.to_datetime(df_p_piv["czas"])
            df_p_piv = df_p_piv.sort_values("czas")
            
            for c in ["ac_vol", "ac_curr"]:
                if c in df_p_piv.columns:
                    df_p_piv[c] = df_p_piv[c].ffill()
                else:
                    df_p_piv[c] = 0.0

            curr_a_all = df_p_piv["ac_curr"] / ac_curr_div
            raw_p_all = (df_p_piv["ac_vol"] * curr_a_all * cos_phi) / 1000.0
            is_act_all = raw_p_all > 0.1
            corr_all = (standby_power_w / 1000.0) + np.where(is_act_all, active_power_w / 1000.0, 0.0)
            df_p_piv["P_el_kw"] = raw_p_all + corr_all

            df_p_piv["dt_hours"] = df_p_piv["czas"].diff().dt.total_seconds().fillna(0) / 3600.0
            df_p_piv["E_el_kwh"] = df_p_piv["P_el_kw"].shift(1).fillna(0) * df_p_piv["dt_hours"]
            df_p_piv["dzień"] = df_p_piv["czas"].dt.date
            
            pump_agg = df_p_piv.groupby("dzień")["E_el_kwh"].sum().to_dict()
            daily_pump_energy = pump_agg

        daily_meter_df["dzień_date"] = daily_meter_df["Data"].dt.date
        daily_meter_df["Zużycie_Pompa_Teoria"] = daily_meter_df["dzień_date"].map(daily_pump_energy).fillna(0.0)

        # Wizualizacja porównawcza
        plot_df = daily_meter_df.dropna(subset=["Zużycie_Licznik_Fizyczny"]).copy()
        
        fig_meter = go.Figure()
        
        # Słupki estymowanego dziennego zużycia z licznika fizycznego
        fig_meter.add_trace(go.Bar(
            x=plot_df["dzień_date"],
            y=plot_df["Zużycie_Licznik_Fizyczny"],
            name="Licznik Fizyczny (Estymacja dzienna)",
            marker_color="#2ECC71",
            opacity=0.85
        ))
        
        # Linia zużycia wyliczonego przez pompę
        fig_meter.add_trace(go.Scatter(
            x=plot_df["dzień_date"],
            y=plot_df["Zużycie_Pompa_Teoria"],
            name="Wyliczone przez Pompę (U*I*cosφ + straty)",
            mode="lines+markers",
            line=dict(color="#E74C3C", width=2.5)
        ))

        fig_meter.update_layout(
            title="Porównanie dziennego zużycia energii elektrycznej [kWh]",
            xaxis_title="Dzień",
            yaxis_title="Energia [kWh / dzień]",
            hovermode="x unified",
            barmode="overlay",
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
        )
        st.plotly_chart(fig_meter, use_container_width=True)
        st.info("💡 **Uwaga:** W dniach pomiędzy odczytami licznika fizycznego, zużycie jest równomiernie estymowane na podstawie interpolacji liniowej.")
