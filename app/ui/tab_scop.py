"""Zakładka: Bilans Energetyczny & SCOP."""
import pandas as pd
import numpy as np
import streamlit as st
import plotly.graph_objects as go


def render(
    df_empty: bool,
    scop: dict,
    ops: dict,
    daily_df_all: pd.DataFrame
):
    """
    Renderuje zakładkę SCOP.
    
    Args:
        df_empty: czy brak danych
        scop: dict z compute_scop_metrics
        ops: dict z compute_operational_stats
        daily_df_all: DataFrame z daily stats (all time)
    """
    st.header("🏆 Podsumowanie Efektywności SCOP i Zużycia Energii")

    if df_empty:
        st.info("Brak danych do wyliczenia bilansu.")
        return

    sc_col1, sc_col2, sc_col3 = st.columns(3)
    sc_col1.metric("🌟 SCOP Całkowite", f"{scop['scop_total']:.2f}")
    sc_col2.metric("🏠 SCOP dla CO (Ogrzewanie)", f"{scop['scop_co']:.2f}")
    sc_col3.metric("🚿 SCOP dla CWU (Ciepła Woda)", f"{scop['scop_cwu']:.2f}")

    st.markdown("### 📊 Statystyki Średniodobowe i Odszranianie")
    d_col1, d_col2, d_col3, d_col4 = st.columns(4)
    d_col1.metric("⚡ Śr. dzienne zużycie CO", f"{ops['avg_daily_el_co']:.2f} kWh/dzień")
    d_col2.metric("⚡ Śr. dzienne zużycie CWU", f"{ops['avg_daily_el_cwu']:.2f} kWh/dzień")
    d_col3.metric("🌡️ Średniodobowa temp. zewn.", f"{ops['avg_amb_temp']:.1f} °C" if not np.isnan(ops['avg_amb_temp']) else "Brak danych")
    d_col4.metric("❄️ Liczba defrostów (okres)", f"{ops['total_defrosts']}")

    d_col5, d_col6, d_col7 = st.columns(3)
    d_col5.metric("🔁 Liczba startów sprężarki (okres)", f"{ops['total_comp_starts']}")
    d_col6.metric("⏱️ Średni czas pracy sprężarki", f"{ops['avg_work_time_per_start']:.1f} min")
    d_col7.metric("🕐 Całkowity czas pracy sprężarki", f"{ops['total_work_hours']:.1f} h")

    st.markdown("---")
    st.subheader("⚡ Zużycie Prądu i Wygenerowane Ciepło [kWh] (Całkowite)")
    summary_data = {
        "Obieg / Tryb": ["🏠 Ogrzewanie (CO)", "🚿 Ciepła Woda (CWU)", " TOTAL (Łącznie)"],
        "Pobrana Energia El. [kWh]": [f"{scop['e_el_co']:.2f}", f"{scop['e_el_cwu']:.2f}", f"{scop['e_el_total']:.2f}"],
        "Oddane Ciepło [kWh]": [f"{scop['e_th_co']:.2f}", f"{scop['e_th_cwu']:.2f}", f"{scop['e_th_total']:.2f}"],
        "Średnie SCOP": [f"{scop['scop_co']:.2f}", f"{scop['scop_cwu']:.2f}", f"{scop['scop_total']:.2f}"]
    }
    st.table(pd.DataFrame(summary_data))

    fig_bar = go.Figure(data=[
        go.Bar(name='Prąd pobrany [kWh]', x=['Ogrzewanie CO', 'Ciepła Woda CWU'], y=[scop['e_el_co'], scop['e_el_cwu']], marker_color='#3498DB'),
        go.Bar(name='Ciepło oddane [kWh]', x=['Ogrzewanie CO', 'Ciepła Woda CWU'], y=[scop['e_th_co'], scop['e_th_cwu']], marker_color='#E74C3C')
    ])
    fig_bar.update_layout(barmode='group', title="Porównanie energii pobranej do oddanej")
    st.plotly_chart(fig_bar, width="stretch")

    st.markdown("---")
    st.subheader("📅 Dzienny Bilans Zużycia, Temperatur i Defrostów (wszystkie dane)")

    if daily_df_all.empty:
        st.info("Brak danych dziennych.")
        return

    daily_display_all = daily_df_all[["dzień", "amb_temp", "E_el_co_row", "E_el_cwu_row", "E_el_total", "E_th_total", "SCOP_dzienny", "defrost_start", "comp_start"]].copy()
    daily_display_all.columns = ["Data", "Śr. Temp Zewn. [°C]", "Prąd CO [kWh]", "Prąd CWU [kWh]", "Prąd Łącznie [kWh]", "Ciepło Łącznie [kWh]", "SCOP Dzienny", "Liczba Defrostów", "Cykle Sprężarki"]
    daily_display_all["Śr. Temp Zewn. [°C]"] = daily_display_all["Śr. Temp Zewn. [°C]"].round(1)
    daily_display_all["Prąd CO [kWh]"] = daily_display_all["Prąd CO [kWh]"].round(2)
    daily_display_all["Prąd CWU [kWh]"] = daily_display_all["Prąd CWU [kWh]"].round(2)
    daily_display_all["Prąd Łącznie [kWh]"] = daily_display_all["Prąd Łącznie [kWh]"].round(2)
    daily_display_all["Ciepło Łącznie [kWh]"] = daily_display_all["Ciepło Łącznie [kWh]"].round(2)
    daily_display_all["SCOP Dzienny"] = daily_display_all["SCOP Dzienny"].round(2)
    daily_display_all["Cykle Sprężarki"] = daily_display_all["Cykle Sprężarki"].astype(int)

    daily_display_all = daily_display_all.sort_values(by="Data", ascending=False)
    st.dataframe(daily_display_all, width="stretch", hide_index=True)
