"""Zakładka: Panel Główny — metryki bieżące i wykresy parametrów."""
import pandas as pd
import numpy as np
import streamlit as st
import plotly.express as px

from app.ui.styles import PARAM_INFO, get_param_label
from app.services.data_loader import apply_time_correction


def render(df: pd.DataFrame, df_pivot: pd.DataFrame, resample_rule, time_offset_hours: int):
    """Renderuje zakładkę Panel Główny."""
    if df.empty or df_pivot is None or df_pivot.empty:
        st.info("Brak danych telemetrycznych pompy w wybranym oknie czasowym.")
        return

    # Aktualne wartości
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
    st.plotly_chart(fig_cop, use_container_width=True)

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
        st.plotly_chart(fig_temp, use_container_width=True)
