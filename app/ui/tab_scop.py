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

    # --- SCOP nominalny i realny ---
    sc_col1, sc_col2, sc_col3, sc_col4 = st.columns(4)
    sc_col1.metric("🌟 SCOP Nominalny", f"{scop['scop_total']:.2f}",
                   help="SCOP bez strat defrostu — okresy odszraniania wykluczone")
    sc_col2.metric("🎯 SCOP Realny", f"{scop['scop_real']:.2f}",
                   delta=f"Strata defrostu: {scop['defrost_loss_pct']:.1f}%",
                   delta_color="inverse",
                   help="SCOP uwzględniający ciepło zabrane z obiegu podczas defrostu")
    sc_col3.metric("🏠 SCOP CO", f"{scop['scop_co']:.2f}")
    sc_col4.metric("🚿 SCOP CWU", f"{scop['scop_cwu']:.2f}")

    # --- Straty defrostu ---
    if scop['e_th_defrost'] != 0 or scop['e_el_defrost'] != 0:
        st.markdown("### ❄️ Straty Energetyczne Defrostu")
        df_col1, df_col2, df_col3 = st.columns(3)
        df_col1.metric("🔻 Ciepło zabrane z obiegu",
                       f"{abs(scop['e_th_defrost']):.3f} kWh",
                       help="Energia cieplna odebrana z instalacji CO podczas odszraniania parownika")
        df_col2.metric("⚡ Prąd zużyty na defrost",
                       f"{scop['e_el_defrost']:.3f} kWh",
                       help="Energia elektryczna zużyta przez sprężarkę podczas cykli defrostu")
        df_col3.metric("📉 Wpływ na SCOP",
                       f"-{scop['scop_total'] - scop['scop_real']:.3f}",
                       help="O ile defrost obniża SCOP względem wartości nominalnej")

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
    summary_rows = [
        ["🏠 Ogrzewanie (CO)", f"{scop['e_el_co']:.2f}", f"{scop['e_th_co']:.2f}", f"{scop['scop_co']:.2f}"],
        ["🚿 Ciepła Woda (CWU)", f"{scop['e_el_cwu']:.2f}", f"{scop['e_th_cwu']:.2f}", f"{scop['scop_cwu']:.2f}"],
    ]
    if scop['e_th_defrost'] != 0:
        summary_rows.append([
            "❄️ Straty defrostu",
            f"{scop['e_el_defrost']:.3f}",
            f"{scop['e_th_defrost']:.3f}",
            "—"
        ])
    summary_rows.extend([
        ["📊 TOTAL (nominalny)", f"{scop['e_el_total']:.2f}", f"{scop['e_th_total']:.2f}", f"{scop['scop_total']:.2f}"],
        ["🎯 TOTAL (realny z defrostem)", f"{scop['e_el_total']:.2f}", f"{scop['e_th_total'] + scop['e_th_defrost']:.2f}", f"{scop['scop_real']:.2f}"],
    ])
    summary_data = {
        "Obieg / Tryb": [r[0] for r in summary_rows],
        "Energia El. [kWh]": [r[1] for r in summary_rows],
        "Ciepło [kWh]": [r[2] for r in summary_rows],
        "SCOP": [r[3] for r in summary_rows],
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

    daily_display_all = daily_df_all[["dzień", "amb_temp", "E_el_co_row", "E_el_cwu_row", "E_el_total", "E_th_total", "SCOP_dzienny"]].copy()

    # Dodaj kolumny defrostu jeśli istnieją
    if "SCOP_realny" in daily_df_all.columns:
        daily_display_all["SCOP_realny"] = daily_df_all["SCOP_realny"]
    if "E_th_defrost_kwh" in daily_df_all.columns:
        daily_display_all["E_th_defrost"] = daily_df_all["E_th_defrost_kwh"].abs()

    daily_display_all["defrost_start"] = daily_df_all["defrost_start"]
    daily_display_all["comp_start"] = daily_df_all["comp_start"]

    col_rename = {
        "dzień": "Data",
        "amb_temp": "Śr. Temp [°C]",
        "E_el_co_row": "Prąd CO [kWh]",
        "E_el_cwu_row": "Prąd CWU [kWh]",
        "E_el_total": "Prąd Łącznie [kWh]",
        "E_th_total": "Ciepło [kWh]",
        "SCOP_dzienny": "SCOP Nom.",
        "SCOP_realny": "SCOP Real.",
        "E_th_defrost": "Strata Defr. [kWh]",
        "defrost_start": "Defrosty",
        "comp_start": "Cykle Spr.",
    }
    daily_display_all = daily_display_all.rename(columns=col_rename)

    for col in ["Śr. Temp [°C]"]:
        if col in daily_display_all.columns:
            daily_display_all[col] = daily_display_all[col].round(1)
    for col in ["Prąd CO [kWh]", "Prąd CWU [kWh]", "Prąd Łącznie [kWh]", "Ciepło [kWh]", "SCOP Nom.", "SCOP Real.", "Strata Defr. [kWh]"]:
        if col in daily_display_all.columns:
            daily_display_all[col] = daily_display_all[col].round(2)
    if "Cykle Spr." in daily_display_all.columns:
        daily_display_all["Cykle Spr."] = daily_display_all["Cykle Spr."].astype(int)

    daily_display_all = daily_display_all.sort_values(by="Data", ascending=False)
    st.dataframe(daily_display_all, width="stretch", hide_index=True)
