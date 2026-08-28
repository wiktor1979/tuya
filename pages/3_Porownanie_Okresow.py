"""Podstrona: Porównanie Okresów — HDD, SCOP miesięczny, trend kWh/HDD."""
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from app.services.data_loader import (
    load_pump_data,
    process_telemetry,
    compute_monthly_stats,
)
from app.ui.styles import inject_css
from app.ui.sidebar import render_sidebar

# --- KONFIGURACJA STRONY ---
st.set_page_config(page_title="Porównanie Okresów — Pompa Ciepła", layout="wide", page_icon="📅")
inject_css()

st.markdown(
    '<h3 style="margin:0;padding:0.2rem 0;">📅 Porównanie Okresów</h3>',
    unsafe_allow_html=True,
)

if st.button("🔄 Odśwież dane"):
    st.rerun()

# --- PANEL BOCZNY ---
settings = render_sidebar()

# --- ŁADOWANIE DANYCH (all time — potrzebujemy pełnej historii) ---
df_all = load_pump_data(0, all_time=True)

if df_all.empty:
    st.info("Brak danych telemetrycznych. Porównanie okresów wymaga danych z co najmniej jednego miesiąca.")
    st.stop()

df_pivot_all = process_telemetry(
    df_all.copy(),
    settings.time_offset_hours,
    settings.cos_phi,
    settings.standby_power_w,
    settings.active_power_w,
    "5min",
)

if df_pivot_all is None or df_pivot_all.empty:
    st.info("Nie udało się przetworzyć danych telemetrycznych.")
    st.stop()

# --- OBLICZENIA MIESIĘCZNE ---
monthly = compute_monthly_stats(
    df_pivot_all,
    settings.time_offset_hours,
    electricity_price=settings.electricity_price,
)

if monthly.empty:
    st.info("Za mało danych do wygenerowania statystyk miesięcznych.")
    st.stop()

# --- KPI podsumowanie ---
st.subheader("📊 Podsumowanie")

total_hdd = monthly["HDD"].sum()
total_el_co = monthly["E_el_co"].sum()
total_el_cwu = monthly["E_el_cwu"].sum()
total_el = total_el_co + total_el_cwu
total_th_co = monthly["E_th_co"].sum()
total_th_cwu = monthly["E_th_cwu"].sum()
total_cost = monthly["koszt"].sum()
scop_co = total_th_co / total_el_co if total_el_co > 0 else 0
scop_cwu = total_th_cwu / total_el_cwu if total_el_cwu > 0 else 0

kpi1, kpi2, kpi3, kpi4 = st.columns(4)
kpi1.metric("Σ HDD", f"{total_hdd:.0f}")
kpi2.metric("SCOP CO", f"{scop_co:.2f}" if scop_co > 0 else "—")
kpi3.metric("SCOP CWU", f"{scop_cwu:.2f}" if scop_cwu > 0 else "—")
kpi4.metric("Σ Koszt", f"{total_cost:.0f} zł")

kpi5, kpi6, kpi7, kpi8 = st.columns(4)
kpi5.metric("Energia CO", f"{total_el_co:.1f} kWh")
kpi6.metric("Energia CWU", f"{total_el_cwu:.1f} kWh")
kpi7.metric("Energia Σ", f"{total_el:.1f} kWh")
kpi8.metric("Ciepło Σ", f"{total_th_co + total_th_cwu:.1f} kWh")

st.markdown("---")

# --- TABELA MIESIĘCZNA ---
st.subheader("📋 Statystyki miesięczne")

display_df = monthly[[
    "miesiąc_str", "HDD", "E_el_co", "E_el_cwu", "E_el_kwh",
    "SCOP_co", "SCOP_cwu", "kWh_per_HDD", "koszt",
    "dt_hours_work", "comp_start", "defrost_start", "amb_temp_avg",
]].copy()

display_df.columns = [
    "Miesiąc", "HDD", "E_el CO", "E_el CWU", "E_el Σ",
    "SCOP CO", "SCOP CWU", "kWh/HDD", "Koszt [zł]",
    "Praca [h]", "Starty", "Defrosty", "Śr. temp. [°C]",
]

# Formatowanie
for col in ["HDD", "E_el CO", "E_el CWU", "E_el Σ", "Koszt [zł]"]:
    display_df[col] = display_df[col].round(1)
for col in ["SCOP CO", "SCOP CWU", "kWh/HDD"]:
    display_df[col] = display_df[col].round(2)
display_df["Praca [h]"] = display_df["Praca [h]"].round(1)
display_df["Śr. temp. [°C]"] = display_df["Śr. temp. [°C]"].round(1)
display_df["Starty"] = display_df["Starty"].astype(int)
display_df["Defrosty"] = display_df["Defrosty"].astype(int)

st.dataframe(display_df, width="stretch", hide_index=True)

st.caption(
    "**HDD** = Heating Degree Days (baza 15°C) — miara zapotrzebowania na ogrzewanie. "
    "**kWh/HDD** = zużycie energii el. CO na stopniodzień (bez CWU) — im niżej tym lepiej. "
    "Pozwala porównywać miesiące/lata niezależnie od pogody."
)

st.markdown("---")

# --- WYKRES: TREND kWh/HDD ---
st.subheader("📈 Trend efektywności: kWh/HDD w czasie")

# Filtruj miesiące z sensownymi danymi HDD (>0 — sezon grzewczy)
trend_df = monthly[monthly["HDD"] > 5].copy()

if trend_df.empty:
    st.info(
        "Brak miesięcy z HDD > 5 (sezon grzewczy). "
        "Trend kWh/HDD pojawi się gdy będą dane z okresu ogrzewania."
    )
else:
    fig_trend = go.Figure()

    fig_trend.add_trace(go.Bar(
        x=trend_df["miesiąc_str"],
        y=trend_df["kWh_per_HDD"],
        name="kWh/HDD",
        marker_color=np.where(
            trend_df["kWh_per_HDD"] <= trend_df["kWh_per_HDD"].median(),
            "#2ECC71", "#E74C3C"
        ),
        text=trend_df["kWh_per_HDD"].round(2),
        textposition="outside",
    ))

    # Linia mediany
    median_val = trend_df["kWh_per_HDD"].median()
    fig_trend.add_hline(
        y=median_val, line_dash="dash", line_color="gray",
        annotation_text=f"Mediana: {median_val:.2f}",
        annotation_position="top right",
    )

    fig_trend.update_layout(
        xaxis_title="Miesiąc",
        yaxis_title="kWh / HDD",
        hovermode="x unified",
    )
    st.plotly_chart(fig_trend, width="stretch")

    st.caption(
        "Słupki zielone = lepsze od mediany, czerwone = gorsze. "
        "Rosnący trend oznacza spadek efektywności (budynku lub pompy)."
    )

st.markdown("---")

# --- WYKRES: SCOP miesięczny ---
st.subheader("🏆 SCOP — porównanie miesięczne (CO vs CWU)")

scop_df = monthly[monthly["SCOP_co"].notna() | monthly["SCOP_cwu"].notna()].copy()

if scop_df.empty:
    st.info("Brak danych SCOP do wyświetlenia.")
else:
    fig_scop = go.Figure()

    if scop_df["SCOP_co"].notna().any():
        fig_scop.add_trace(go.Bar(
            x=scop_df["miesiąc_str"],
            y=scop_df["SCOP_co"],
            name="SCOP CO",
            marker_color="#2ECC71",
            text=scop_df["SCOP_co"].round(2),
            textposition="outside",
        ))

    if scop_df["SCOP_cwu"].notna().any():
        fig_scop.add_trace(go.Bar(
            x=scop_df["miesiąc_str"],
            y=scop_df["SCOP_cwu"],
            name="SCOP CWU",
            marker_color="#3498DB",
            text=scop_df["SCOP_cwu"].round(2),
            textposition="outside",
        ))

    # Próg opłacalności
    fig_scop.add_hline(
        y=3.1, line_dash="dash", line_color="orange",
        annotation_text="Próg opłacalności 3.1",
        annotation_position="top right",
    )

    fig_scop.update_layout(
        xaxis_title="Miesiąc",
        yaxis_title="SCOP",
        barmode="group",
        hovermode="x unified",
    )
    st.plotly_chart(fig_scop, width="stretch")

st.markdown("---")

# --- WYKRES: HDD vs Energia CO ---
st.subheader("🌡️ HDD vs Zużycie energii CO")

fig_hdd = go.Figure()

fig_hdd.add_trace(go.Bar(
    x=monthly["miesiąc_str"],
    y=monthly["HDD"],
    name="HDD",
    marker_color="#3498DB",
    opacity=0.6,
    yaxis="y",
))

fig_hdd.add_trace(go.Scatter(
    x=monthly["miesiąc_str"],
    y=monthly["E_el_co"],
    name="E_el CO [kWh]",
    mode="lines+markers",
    line=dict(color="#E74C3C", width=3),
    yaxis="y2",
))

fig_hdd.update_layout(
    xaxis_title="Miesiąc",
    yaxis=dict(title="HDD", side="left"),
    yaxis2=dict(title="Energia el. CO [kWh]", side="right", overlaying="y"),
    hovermode="x unified",
    legend=dict(x=0, y=1.1, orientation="h"),
)
st.plotly_chart(fig_hdd, width="stretch")

st.caption(
    "Słupki = HDD (zapotrzebowanie na ogrzewanie), linia = zużycie prądu na CO. "
    "Powinny rosnąć proporcjonalnie — jeśli prąd rośnie szybciej niż HDD, pompa traci efektywność."
)



st.markdown("---")
with st.expander("📖 Metodologia — jak liczymy"):
    st.markdown("""
**Dane źródłowe**
- Wszystkie obliczenia opierają się na telemetrii z pompy ciepła (Tuya Pulsar) przetwarzanej identycznie jak na głównym dashboardzie.
- Dane są agregowane w interwałach 5-minutowych (resample) z uzupełnieniem brakujących wartości (forward fill).
- Podział na miesiące kalendarzowe (1. – ostatni dzień miesiąca). Bieżący miesiąc może być niepełny.

**HDD (Heating Degree Days)**
- Stopniodni grzania — miara zapotrzebowania budynku na ciepło, niezależna od pracy pompy.
- Obliczenie: dla każdego dnia `HDD = max(0, 15°C - średnia_temp_zewnętrzna)`.
- Temperatura bazowa 15°C (standard dla pomp ciepła, nie 18°C jak dla gazu).
- Źródło temperatury: czujnik pompy (`amb_temp`).
- Latem HDD ≈ 0, zimą HDD może wynosić 20-30 dziennie.

**Podział CO / CWU**
- Tryb pracy rozpoznawany po stanie zaworu 3-drożnego (`valve`): ≥ 0.5 = CWU, < 0.5 = CO.
- Energia elektryczna i cieplna liczone osobno dla każdego trybu.
- **kWh/HDD liczymy TYLKO z energii CO** — CWU nie zależy od pogody i zaburzałoby porównanie.

**SCOP (Seasonal COP)**
- SCOP CO = suma energii cieplnej CO (z uwzględnieniem strat defrostu) / suma energii elektrycznej CO.
- SCOP CWU = suma energii cieplnej CWU / suma energii elektrycznej CWU.
- Defrost: ujemna moc cieplna podczas odszraniania parownika obniża SCOP CO (SCOP „realny").

**Energia elektryczna (P_el)**
- `P_el = U × I × cos_φ + korekta_standby + korekta_active`
- Napięcie (`ac_vol`) i prąd (`ac_curr`, skala ×0.1 A) z czujników pompy.
- Parametry kalibracji (`cos_φ`, `standby_power_w`, `active_power_w`) pobierane z ustawień dashboardu.

**Energia cieplna (P_th)**
- `P_th = przepływ × 4.186 × ΔT / 3.6`
- Przepływ (`flow_rate`, skala ×0.1 m³/h), ΔT = temperatura zasilania − temperatura powrotu.
- Ujemne wartości P_th (defrost) zerowane w SCOP nominalnym, uwzględniane w SCOP realnym.

**Czego NIE uwzględniamy**
- Energia grzałki elektrycznej (brak wiarygodnych danych w telemetrii).
- Energia na pompy obiegowe i automatykę (częściowo w korekcie `active_power_w`).
- Straty ciepła na rurach między pompą a budynkiem.

**kWh/HDD — interpretacja**
- Im niższa wartość, tym efektywniej budynek + pompa wykorzystują energię.
- Pozwala porównywać miesiące i sezony niezależnie od tego czy zima była łagodna czy mroźna.
- Rosnący trend kWh/HDD w czasie może oznaczać: degradację pompy, pogorszenie izolacji, zmianę nastawień.
""")
