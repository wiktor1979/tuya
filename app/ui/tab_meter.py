"""Zakładka: Fizyczny Licznik Energii — formularz i wykres."""
import pandas as pd
import numpy as np
import streamlit as st
import plotly.graph_objects as go
from datetime import datetime

from app.config import MANUAL_METER_DEV_ID
from app.services.data_loader import load_manual_readings
from db import save_manual_energy_reading, update_manual_energy_reading, delete_manual_energy_reading


def render(daily_df_all: pd.DataFrame, time_offset_hours: int):
    """Renderuje zakładkę Fizyczny Licznik."""
    st.header("⚡ Rejestracja i Analiza Fizycznego Licznika Energii")
    st.caption(f"Dane wprowadzane ręcznie są rejestrowane w bazie pod identyfikatorem urządzenia: `{MANUAL_METER_DEV_ID}`.")

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

            btn_add = st.form_submit_button("💾 Zapisz stan licznika")

            if btn_add:
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

    # --- SEKCJA EDYCJI / USUWANIA ---
    with st.expander("✏️ Edytuj lub usuń wpis", expanded=False):
        df_meter_all = load_manual_readings(time_offset_hours)

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
                    btn_update = col_e1.form_submit_button("💾 Zapisz zmiany")
                    btn_delete = col_e2.form_submit_button("🗑️ Usuń wpis")

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
    _render_meter_table(time_offset_hours, daily_df_all)


def _render_meter_table(time_offset_hours: int, daily_df_all: pd.DataFrame):
    """Tabela historii odczytów i wykres porównawczy."""
    st.subheader("📋 Tabela odczytów i zużycia energii")
    df_meter_all = load_manual_readings(time_offset_hours)

    if df_meter_all.empty:
        st.info("Wprowadź co najmniej dwa odczyty licznika, aby wyświetlić tabelę różnic oraz wykres.")
        return

    df_display = df_meter_all.copy()
    df_display["czas_dt"] = pd.to_datetime(df_display["czas"])
    df_display = df_display.sort_values("czas_dt").reset_index(drop=True)

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

    # --- WYKRES PORÓWNAWCZY ---
    st.markdown("---")
    st.subheader("📊 Dzienne Zużycie Energii: Licznik Fizyczny (Estymowany) vs Wyliczenia Pompy")

    if len(df_display) < 2:
        st.info("Wprowadź minimum 2 odczyty licznika w różnych dniach, aby wygenerować wykres interpolacji dobowej.")
        return

    df_interp = df_display.set_index("czas_dt")[["stan_kwh"]].resample("1h").interpolate(method="time")
    df_interp_daily = df_interp.resample("1D").first()
    df_interp_daily["Zuzycie_Licznik_kWh"] = df_interp_daily["stan_kwh"].diff().shift(-1)
    df_interp_daily.index = df_interp_daily.index + pd.Timedelta(days=1 if time_offset_hours >= 12 else 0)
    df_interp_daily["dzień"] = df_interp_daily.index.date

    meter_daily = df_interp_daily.dropna(subset=["Zuzycie_Licznik_kWh"])[["dzień", "Zuzycie_Licznik_kWh"]].reset_index(drop=True)

    if not daily_df_all.empty:
        comp_df = pd.merge(meter_daily, daily_df_all[["dzień", "E_el_total"]], on="dzień", how="outer").sort_values("dzień")
    else:
        comp_df = meter_daily.copy()
        comp_df["E_el_total"] = np.nan

    comp_df = comp_df.rename(columns={"E_el_total": "Zuzycie_Pompa_kWh"})
    comp_df["dzień_str"] = comp_df["dzień"].astype(str)

    fig_comp = go.Figure()
    fig_comp.add_trace(go.Bar(
        x=comp_df["dzień_str"], y=comp_df["Zuzycie_Licznik_kWh"],
        name="Fizyczny Licznik (interpolowane/estymowane)", marker_color="#2ECC71"
    ))
    fig_comp.add_trace(go.Scatter(
        x=comp_df["dzień_str"], y=comp_df["Zuzycie_Pompa_kWh"],
        name="Pompa Ciepła (wyliczone E_el)", mode="lines+markers",
        line=dict(color="#E74C3C", width=3)
    ))
    fig_comp.update_layout(
        title="Porównanie zużycia dobowego [kWh]",
        xaxis_title="Dzień", yaxis_title="Energia elektryczna [kWh]",
        hovermode="x unified", barmode="group"
    )
    st.plotly_chart(fig_comp, width="stretch")
