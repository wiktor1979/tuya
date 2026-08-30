"""Zakładka: Panel Główny — metryki bieżące i wykresy parametrów."""
import pandas as pd
import numpy as np
import streamlit as st
import plotly.express as px

from app.ui.styles import PARAM_INFO, get_param_label
from app.services.data_loader import apply_time_correction
from app.services.database import get_active_faults, get_current_fault_value
from app.services.analytics import decode_fault_bitmap
from app.config import HEAT_PUMP_DEV_ID


def render(df: pd.DataFrame, df_pivot: pd.DataFrame, resample_rule, time_offset_hours: int):
    """Renderuje zakładkę Panel Główny."""
    if df.empty or df_pivot is None or df_pivot.empty:
        st.info("Brak danych telemetrycznych pompy w wybranym oknie czasowym.")
        return

    # --- Alert awarii — czerwony banner na samej górze ---
    fault_val = get_current_fault_value(HEAT_PUMP_DEV_ID)
    active_fault_codes = decode_fault_bitmap(fault_val) if fault_val else []
    active_faults_db = get_active_faults(HEAT_PUMP_DEV_ID)

    # Połącz kody z bitmapy i z bazy (na wypadek gdyby bitmapa była 0 ale w bazie są nierozwiązane)
    all_active_codes = list(set(active_fault_codes + [r[2] for r in active_faults_db]))

    if all_active_codes:
        codes_str = ", ".join(sorted(all_active_codes))
        st.error(f"🚨 **AWARIA POMPY** — aktywne kody błędów: **{codes_str}**")

    # --- Wizualne wyróżnienie statusu pompy (pracuje vs stoi) ---
    pump_running = False
    if "comp_freq" in df_pivot.columns:
        last_freq = df_pivot["comp_freq"].dropna().iloc[-1] if not df_pivot["comp_freq"].dropna().empty else 0
        pump_running = last_freq > 0

    if pump_running:
        st.markdown("""<style>
        [data-testid="stMetric"] {
            border-color: #2e7d32 !important;
            box-shadow: 0 0 12px rgba(46,125,50,0.35) !important;
        }
        </style>""", unsafe_allow_html=True)
    else:
        st.markdown("""<style>
        [data-testid="stMetric"] { opacity: 0.65; }
        </style>""", unsafe_allow_html=True)

    # Aktualne wartości
    latest_df = df.drop_duplicates(subset=["code"], keep="last")

    def get_val(c):
        row = latest_df[latest_df["code"] == c]
        if not row.empty:
            v_num = row["val_num"].values[0]
            if pd.notnull(v_num):
                # heat_temp_set_z2, idr_temp_set: stare dane w bazie mogą być niedzielone (350/250 zamiast 35.0/25.0)
                if c in ("heat_temp_set_z2", "idr_temp_set") and v_num > 100:
                    v_num = v_num / 10.0
                return f"{v_num} °C" if "temp" in c or c in ["tidr", "back_temp", "heat_temp_set", "heat_temp_set_z2", "hot_water_temp_set", "idr_temp_set"] else f"{v_num}"
            return str(row["val_str"].values[0])
        return "N/A"

    latest_cop = df_pivot["COP"].dropna().iloc[-1] if not df_pivot["COP"].dropna().empty else 0.0
    latest_p_th = df_pivot["P_th_kw"].iloc[-1] if not df_pivot.empty else 0.0
    latest_p_el = df_pivot["P_el_kw"].iloc[-1] if not df_pivot.empty else 0.0
    latest_flow = df_pivot["flow_m3h"].iloc[-1] if not df_pivot.empty else 0.0
    current_mode = df_pivot["Tryb"].iloc[-1] if not df_pivot.empty else "CO"

    c1, c2, c3, c4, c5, c6, c7 = st.columns(7)
    c1.metric("Woda CWU", get_val("tank_temp"))
    c2.metric("🎯 Zadana CWU", get_val("hot_water_temp_set"))
    c3.metric("Powrót CO", get_val("in_water_temp"))
    c4.metric("Zasilanie CO", get_val("out_water_temp"))

    # Nastawa CO — zależna od aktywnej strefy
    zone_row = latest_df[latest_df["code"] == "zone_select"]
    zone_val = None
    if not zone_row.empty:
        z_str = str(zone_row["val_str"].values[0])
        try:
            zone_val = int(float(z_str))
        except (ValueError, TypeError):
            zone_val = None

    if zone_val == 2:
        # Tylko strefa 2 (podłogówka) — pokazuj heat_temp_set_z2
        co_set_label = "🎯 Nastawa Z2"
        co_set_val = get_val("heat_temp_set_z2")
    elif zone_val == 3:
        # Obie strefy — pokazuj obie nastawy
        co_set_label = "🎯 Nastawa Z1+Z2"
        v1 = get_val("heat_temp_set")
        v2 = get_val("heat_temp_set_z2")
        co_set_val = f"{v1}/{v2}"
    else:
        # Strefa 1 lub brak danych — domyślnie heat_temp_set
        co_set_label = "🎯 Nastawa CO"
        co_set_val = get_val("heat_temp_set")

    c5.metric(co_set_label, co_set_val)
    c6.metric("Przepływ", f"{latest_flow:.1f} m³/h", delta=f"{latest_flow * 1000 / 60:.1f} L/min")
    c7.metric("📊 Chwilowe COP", f"{latest_cop:.2f}", delta=f"Tryb: {current_mode}")

    cp1, cp2, cp3 = st.columns(3)
    cp1.metric("🔥 Moc cieplna (P_th)", f"{latest_p_th:.2f} kW")
    cp2.metric("⚡ Pobór prądu (P_el)", f"{latest_p_el:.2f} kW")
    cp3.metric("📈 Nastawa z krzywej", get_val("idr_temp_set"))

    # Tryby specjalne — widoczne tylko gdy aktywne
    def is_mode_active(code):
        row = latest_df[latest_df["code"] == code]
        if not row.empty:
            val = str(row["val_str"].values[0]).lower()
            return val in ("true", "1", "1.0")
        return False

    active_modes = []
    if is_mode_active("holiday_sw"):
        active_modes.append("🏖️ **Tryb Holiday** — pompa pracuje w trybie urlopowym (obniżona temperatura)")
    if is_mode_active("mute"):
        active_modes.append("🔇 **Tryb Silent** — pompa pracuje w trybie cichym (ograniczona moc)")

    if active_modes:
        st.warning(" · ".join(active_modes))

    st.markdown("---")
    st.subheader("📈 Przebieg wybranych parametrów")
    df_corrected = apply_time_correction(df.copy(), time_offset_hours)
    all_codes = df_corrected["code"].unique().tolist()
    default_temps = [c for c in ["tank_temp", "in_water_temp", "out_water_temp", "heat_temp_set", "amb_temp"] if c in all_codes]
    selected_temps = st.multiselect(
        "Wybierz parametry do wyświetlenia:",
        options=all_codes,
        default=default_temps,
        format_func=get_param_label
    )

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
