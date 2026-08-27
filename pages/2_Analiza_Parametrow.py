"""Podstrona: Analiza Parametrów Pompy Ciepła — COP, Hydraulika, Sprężarka, Defrost."""
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from streamlit_autorefresh import st_autorefresh

import streamlit.components.v1 as components

from app.services.data_loader import (
    get_pump_status_for_refresh,
    load_pump_data,
    process_telemetry,
    compute_daily_stats,
)
from app.ui.styles import inject_css
from app.ui.sidebar import render_sidebar

# --- KONFIGURACJA STRONY ---
st.set_page_config(page_title="Analiza Parametrów — Pompa Ciepła", layout="wide", page_icon="🔬")
inject_css()

# --- STATUS POMPY I AUTO-ODŚWIEŻANIE ---
pump_running = get_pump_status_for_refresh()
interval_sec = 60 if pump_running else 300

st.title("🔬 Analiza Parametrów Pompy Ciepła")

status_color = "#4CAF50" if pump_running else "#888"
status_text = "Pompa pracuje — odświeżanie co 1 min" if pump_running else "Pompa stoi — odświeżanie co 5 min"
components.html(
    f"""
    <div style="text-align:center;font-size:0.85em;color:#aaa;font-family:sans-serif;">
        Następne odświeżenie za: <span id="cd" style="font-weight:bold;color:#4CAF50;">{interval_sec}</span> s
        <span style="font-size:0.75em;margin-left:8px;color:{status_color};">{status_text}</span>
    </div>
    <script>
    (function(){{
        var remaining = {interval_sec};
        var d = document.getElementById('cd');
        if (!d) return;
        d.textContent = remaining;
        var timer = setInterval(function() {{
            remaining--;
            if (remaining <= 0) {{
                clearInterval(timer);
                d.textContent = "0";
                d.style.color = "#FF5722";
            }} else {{
                d.textContent = remaining;
                d.style.color = remaining <= 10 ? "#FF9800" : "#4CAF50";
            }}
        }}, 1000);
    }})();
    </script>
    """,
    height=35,
)

st_autorefresh(interval=interval_sec * 1000, limit=None, key="analysis_refresher")

# --- PANEL BOCZNY ---
settings = render_sidebar()

# --- ŁADOWANIE DANYCH ---
is_today_range = settings.selected_range == "1 dzień"
df = load_pump_data(settings.hours_back, is_today=is_today_range)
df_all_time = load_pump_data(settings.hours_back, all_time=True)

df_pivot = process_telemetry(
    df.copy(),
    settings.time_offset_hours,
    settings.cos_phi,
    settings.standby_power_w,
    settings.active_power_w,
    settings.resample_rule,
)

df_pivot_all = process_telemetry(
    df_all_time.copy(),
    settings.time_offset_hours,
    settings.cos_phi,
    settings.standby_power_w,
    settings.active_power_w,
    None,
)

daily_df = compute_daily_stats(df_pivot, settings.time_offset_hours) if df_pivot is not None else pd.DataFrame()
daily_df_all = compute_daily_stats(df_pivot_all, settings.time_offset_hours) if df_pivot_all is not None else pd.DataFrame()


# ==============================================================================
# HELPER FUNCTIONS
# ==============================================================================

def safe_col(df: pd.DataFrame, col: str) -> bool:
    """Sprawdza czy kolumna istnieje i ma jakiekolwiek dane."""
    return col in df.columns and df[col].notna().any()


def kpi_with_status(label: str, value, unit: str = "", norm_min=None, norm_max=None, fmt: str = ".1f"):
    """Wyświetla KPI z kolorowym statusem."""
    if value is None or (isinstance(value, float) and np.isnan(value)):
        st.metric(label, "—")
        return

    formatted = f"{value:{fmt}}{unit}"
    delta_text = None
    if norm_min is not None and norm_max is not None:
        if norm_min <= value <= norm_max:
            delta_text = f"✓ Norma ({norm_min}-{norm_max}{unit})"
        elif value < norm_min:
            delta_text = f"↓ Poniżej normy ({norm_min}{unit})"
        else:
            delta_text = f"↑ Powyżej normy ({norm_max}{unit})"

    delta_color = "normal" if delta_text and "✓" in delta_text else "inverse"
    st.metric(label, formatted, delta=delta_text, delta_color=delta_color)


# ==============================================================================
# ZAKŁADKI
# ==============================================================================

if df_pivot is None or df_pivot.empty:
    st.warning("⚠️ Brak danych w wybranym zakresie czasu. Zmień zakres w panelu bocznym.")
    st.stop()

tab_cop, tab_hydr, tab_comp, tab_defr = st.tabs([
    "🔋 Wydajność COP",
    "💧 Hydraulika i ΔT",
    "⚙️ Sprężarka i Taktowanie",
    "❄️ Defrost i Obieg Chłodniczy",
])


# ==============================================================================
# TAB 1: WYDAJNOŚĆ COP
# ==============================================================================
with tab_cop:
    st.subheader("🔋 Wydajność i Efektywność Energetyczna")

    # --- KPI ---
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        current_cop = df_pivot["COP"].dropna().iloc[-1] if safe_col(df_pivot, "COP") else None
        kpi_with_status("COP Chwilowy", current_cop, "", 2.5, 5.0)
    with col2:
        e_th = df_pivot["E_th_kwh"].sum() if safe_col(df_pivot, "E_th_kwh") else 0
        e_el = df_pivot["E_el_kwh"].sum() if safe_col(df_pivot, "E_el_kwh") else 0
        e_th_defrost = df_pivot["E_th_defrost_kwh"].sum() if safe_col(df_pivot, "E_th_defrost_kwh") else 0
        # SCOP realny uwzględniający straty defrostu
        scop_real = (e_th + e_th_defrost) / e_el if e_el > 0 else None
        scop_nom = e_th / e_el if e_el > 0 else None
        if scop_real is not None:
            if scop_real >= 3.1:
                delta_text = f"✓ Opłacalny (próg 3.1)"
                delta_color = "normal"
            else:
                delta_text = f"✗ Poniżej progu 3.1"
                delta_color = "inverse"
            st.metric("SCOP Realny (okres)", f"{scop_real:.2f}", delta=delta_text, delta_color=delta_color,
                      help="SCOP uwzględniający straty cieplne defrostu")
        else:
            st.metric("SCOP Realny (okres)", "—")
    with col3:
        st.metric("Ciepło wygenerowane", f"{e_th:.1f} kWh")
    with col4:
        defrost_loss = abs(e_th_defrost)
        if defrost_loss > 0.001:
            st.metric("❄️ Strata defrostu", f"{defrost_loss:.3f} kWh",
                      delta=f"{defrost_loss / e_th * 100:.1f}% ciepła" if e_th > 0 else None,
                      delta_color="inverse")
        else:
            st.metric("Energia zużyta", f"{e_el:.1f} kWh")

    st.divider()

    # --- COP w czasie ---
    st.markdown("##### 📈 COP chwilowy w czasie")
    if safe_col(df_pivot, "COP"):
        fig_cop = go.Figure()
        fig_cop.add_trace(go.Scatter(
            x=df_pivot["czas"], y=df_pivot["COP"],
            mode="lines", name="COP",
            line=dict(color="#4CAF50", width=2),
            fill="tozeroy", fillcolor="rgba(76,175,80,0.1)"
        ))
        # Progi referencyjne
        fig_cop.add_hline(y=4.2, line_dash="dash", line_color="rgba(76,175,80,0.5)",
                          annotation_text="Norma A7/W35 (4.2)")
        fig_cop.add_hline(y=3.1, line_dash="dash", line_color="rgba(255,152,0,0.8)",
                          annotation_text="⚡ Próg opłacalności (3.1)",
                          annotation=dict(font_size=12, font_color="#FF9800"))
        fig_cop.add_hline(y=2.5, line_dash="dash", line_color="rgba(244,67,54,0.5)",
                          annotation_text="Min A-7/W35 (2.5)")
        fig_cop.update_layout(
            yaxis_title="COP", xaxis_title="",
            height=350, margin=dict(t=20, b=40),
            yaxis=dict(range=[0, 8]),
        )
        st.plotly_chart(fig_cop, use_container_width=True)
    else:
        st.info("Brak danych COP w wybranym zakresie.")

    # --- COP vs Temperatura zewnętrzna ---
    col_a, col_b = st.columns(2)

    with col_a:
        st.markdown("##### 🌡️ COP vs Temperatura zewnętrzna")
        if safe_col(df_pivot, "COP") and safe_col(df_pivot, "amb_temp"):
            mask_cop = df_pivot["COP"].notna() & df_pivot["amb_temp"].notna()
            fig_scatter = px.scatter(
                df_pivot[mask_cop], x="amb_temp", y="COP",
                color="Tryb",
                color_discrete_map={"CO": "#2196F3", "CWU": "#FF9800"},
                opacity=0.6,
                trendline="lowess",
            )
            fig_scatter.update_layout(
                xaxis_title="Temp. zewnętrzna (°C)", yaxis_title="COP",
                height=350, margin=dict(t=20, b=40),
                yaxis=dict(range=[0, 8]),
            )
            st.plotly_chart(fig_scatter, use_container_width=True)
        else:
            st.info("Brak danych do korelacji COP/temperatura.")

    with col_b:
        st.markdown("##### 📊 SCOP dzienny z progiem opłacalności")
        scop_col = "SCOP_realny" if "SCOP_realny" in daily_df.columns else "SCOP_dzienny"
        if not daily_df.empty and scop_col in daily_df.columns:
            scop_valid = daily_df[daily_df[scop_col].notna()].copy()
            if not scop_valid.empty:
                # Kolor słupka: zielony jeśli SCOP realny >= 3.1, czerwony jeśli poniżej
                scop_valid["kolor"] = scop_valid[scop_col].apply(
                    lambda x: "rgba(76,175,80,0.8)" if x >= 3.1 else "rgba(244,67,54,0.8)"
                )
                fig_scop_daily = go.Figure()
                # Słupki SCOP realny
                fig_scop_daily.add_trace(go.Bar(
                    x=scop_valid["dzień"].astype(str),
                    y=scop_valid[scop_col],
                    name="SCOP realny",
                    marker_color=scop_valid["kolor"].tolist(),
                    text=scop_valid[scop_col].apply(lambda x: f"{x:.2f}"),
                    textposition="outside",
                ))
                # Linia SCOP nominalny (jeśli istnieje i różni się)
                if "SCOP_dzienny" in scop_valid.columns and scop_col != "SCOP_dzienny":
                    fig_scop_daily.add_trace(go.Scatter(
                        x=scop_valid["dzień"].astype(str),
                        y=scop_valid["SCOP_dzienny"],
                        mode="markers+lines",
                        name="SCOP nominalny",
                        line=dict(color="rgba(150,150,150,0.6)", width=1, dash="dot"),
                        marker=dict(size=5, color="rgba(150,150,150,0.6)"),
                    ))
                # Próg opłacalności
                fig_scop_daily.add_hline(
                    y=3.1, line_dash="dash", line_color="#FF9800", line_width=2,
                    annotation_text="⚡ Próg opłacalności (3.1)",
                    annotation=dict(font_size=12, font_color="#FF9800"),
                )
                fig_scop_daily.update_layout(
                    yaxis_title="SCOP", height=350, margin=dict(t=20, b=40),
                    yaxis=dict(range=[0, max(6, scop_valid[scop_col].max() * 1.3)]),
                )
                st.plotly_chart(fig_scop_daily, use_container_width=True)

                # Podsumowanie tekstowe
                days_above = (scop_valid[scop_col] >= 3.1).sum()
                days_total = len(scop_valid)
                if days_above == days_total:
                    st.success(f"✅ Wszystkie {days_total} dni powyżej progu opłacalności 3.1")
                else:
                    st.warning(
                        f"⚠️ {days_total - days_above} z {days_total} dni poniżej progu opłacalności 3.1 — "
                        f"pompa w tych dniach jest mniej opłacalna niż ogrzewanie gazowe."
                    )
            else:
                st.info("Brak danych SCOP dziennego.")
        else:
            st.info("Brak danych dziennych do wykresu SCOP.")

    # --- Alerty wydajności (bazowane na SCOP dziennym, nie COP chwilowym) ---
    st.markdown("##### ⚠️ Alerty wydajności")
    if not daily_df.empty:
        scop_alert_col = "SCOP_realny" if "SCOP_realny" in daily_df.columns else "SCOP_dzienny"
        low_scop_days = daily_df[daily_df[scop_alert_col].notna() & (daily_df[scop_alert_col] < 3.1)].copy()

        if not low_scop_days.empty:
            for _, row in low_scop_days.sort_values(scop_alert_col).head(5).iterrows():
                amb = f"{row['amb_temp']:.1f}°C" if pd.notna(row.get('amb_temp')) else "b/d"
                defrosts = int(row.get('defrost_start', 0))
                severity = "error" if row[scop_alert_col] < 2.5 else "warning"
                msg = (
                    f"📅 {row['dzień']} — SCOP realny = {row[scop_alert_col]:.2f} "
                    f"(próg 3.1), śr. temp. zewn. {amb}, defrostów: {defrosts}"
                )
                if severity == "error":
                    st.error(f"🚨 {msg}. Sprawdź przepływ, filtr i nastawy.")
                else:
                    st.warning(f"⚠️ {msg}")
        else:
            st.success("✅ Brak alertów — SCOP dzienny powyżej progu opłacalności 3.1 we wszystkich dniach.")
    else:
        st.info("Brak danych dziennych do oceny wydajności.")


# ==============================================================================
# TAB 2: HYDRAULIKA I ΔT
# ==============================================================================
with tab_hydr:
    st.subheader("💧 Hydraulika i Wymiana Ciepła")

    # --- KPI ---
    col1, col2, col3, col4 = st.columns(4)

    # Ostatni ΔT dla CO i CWU
    co_mask = df_pivot["Tryb"] == "CO"
    cwu_mask = df_pivot["Tryb"] == "CWU"

    with col1:
        dt_co = df_pivot.loc[co_mask, "delta_t"].dropna().iloc[-1] if co_mask.any() and safe_col(df_pivot, "delta_t") else None
        kpi_with_status("ΔT aktualny (CO)", dt_co, "°C", 3.0, 7.0)
    with col2:
        dt_cwu = df_pivot.loc[cwu_mask, "delta_t"].dropna().iloc[-1] if cwu_mask.any() and safe_col(df_pivot, "delta_t") else None
        kpi_with_status("ΔT aktualny (CWU)", dt_cwu, "°C", 5.0, 10.0)
    with col3:
        flow_last = df_pivot["flow_m3h"].dropna().iloc[-1] * 1000 / 60 if safe_col(df_pivot, "flow_m3h") else None  # m3/h -> l/min
        kpi_with_status("Przepływ", flow_last, " l/min", 5.0, 25.0)
    with col4:
        current_mode = df_pivot["Tryb"].iloc[-1] if "Tryb" in df_pivot.columns else "—"
        st.metric("Tryb aktualny", current_mode)

    st.divider()

    # --- ΔT w czasie ---
    st.markdown("##### 🌡️ ΔT w czasie — z zakresami prawidłowymi")
    if safe_col(df_pivot, "delta_t"):
        fig_dt = go.Figure()
        fig_dt.add_trace(go.Scatter(
            x=df_pivot["czas"], y=df_pivot["delta_t"],
            mode="lines", name="ΔT (°C)",
            line=dict(color="#FF9800", width=2),
            fill="tozeroy", fillcolor="rgba(255,152,0,0.08)",
        ))
        # Strefa normy CO
        fig_dt.add_hrect(y0=3, y1=7, fillcolor="rgba(76,175,80,0.05)",
                         line=dict(width=0),
                         annotation_text="Norma CO (3-7°C)", annotation_position="top left")
        fig_dt.update_layout(
            yaxis_title="ΔT (°C)", height=350, margin=dict(t=20, b=40),
            yaxis=dict(range=[0, max(15, df_pivot["delta_t"].max() * 1.2 if df_pivot["delta_t"].max() > 0 else 15)]),
        )
        st.plotly_chart(fig_dt, use_container_width=True)
    else:
        st.info("Brak danych ΔT.")

    # --- Przepływ i korelacja ---
    col_a, col_b = st.columns(2)

    with col_a:
        st.markdown("##### 💧 Przepływ w czasie")
        if safe_col(df_pivot, "flow_m3h"):
            flow_lmin = df_pivot["flow_m3h"] * 1000 / 60  # m3/h -> l/min
            fig_flow = go.Figure()
            fig_flow.add_trace(go.Scatter(
                x=df_pivot["czas"], y=flow_lmin,
                mode="lines", name="Przepływ (l/min)",
                line=dict(color="#2196F3", width=2),
                fill="tozeroy", fillcolor="rgba(33,150,243,0.08)",
            ))
            fig_flow.update_layout(
                yaxis_title="l/min", height=320, margin=dict(t=20, b=40),
            )
            st.plotly_chart(fig_flow, use_container_width=True)
        else:
            st.info("Brak danych przepływu.")

    with col_b:
        st.markdown("##### 📉 Korelacja ΔT vs Przepływ")
        if safe_col(df_pivot, "delta_t") and safe_col(df_pivot, "flow_m3h"):
            flow_lmin_col = df_pivot["flow_m3h"] * 1000 / 60
            mask_valid = df_pivot["delta_t"].notna() & flow_lmin_col.notna() & (flow_lmin_col > 0)
            if mask_valid.any():
                scatter_df = pd.DataFrame({
                    "Przepływ (l/min)": flow_lmin_col[mask_valid],
                    "ΔT (°C)": df_pivot.loc[mask_valid, "delta_t"],
                    "Tryb": df_pivot.loc[mask_valid, "Tryb"],
                })
                fig_scatter_dt = px.scatter(
                    scatter_df, x="Przepływ (l/min)", y="ΔT (°C)",
                    color="Tryb", color_discrete_map={"CO": "#FF9800", "CWU": "#9C27B0"},
                    opacity=0.5, trendline="ols",
                )
                fig_scatter_dt.update_layout(height=320, margin=dict(t=20, b=40))
                st.plotly_chart(fig_scatter_dt, use_container_width=True)
            else:
                st.info("Za mało danych do korelacji.")
        else:
            st.info("Brak danych do korelacji ΔT/przepływ.")

    # --- Alerty hydrauliki ---
    st.markdown("##### ⚠️ Alerty hydrauliki")
    if safe_col(df_pivot, "delta_t"):
        # ΔT > 8°C w trybie CO
        alert_dt = df_pivot[(df_pivot["delta_t"] > 8) & (df_pivot["Tryb"] == "CO") & df_pivot["delta_t"].notna()]
        if not alert_dt.empty:
            for _, row in alert_dt.tail(3).iterrows():
                st.warning(
                    f"⚠️ {row['czas'].strftime('%d.%m %H:%M')} — ΔT = {row['delta_t']:.1f}°C w CO "
                    f"(max 7°C). Możliwy niedostateczny przepływ — sprawdź filtr siatkowy."
                )
        else:
            st.success("✅ ΔT w normie dla trybu CO.")


# ==============================================================================
# TAB 3: SPRĘŻARKA I TAKTOWANIE
# ==============================================================================
with tab_comp:
    st.subheader("⚙️ Stabilność i Żywotność Sprężarki")

    # --- Analiza cykli ---
    # Obliczamy statystyki cykli pracy
    if safe_col(df_pivot, "work_period") and safe_col(df_pivot, "comp_on"):
        work_periods = df_pivot[df_pivot["comp_on"] == 1].groupby("work_period")["dt_hours"].sum() * 60  # minuty
        avg_cycle_min = work_periods.mean() if len(work_periods) > 0 else None
        num_starts = len(work_periods)
    else:
        work_periods = pd.Series(dtype=float)
        avg_cycle_min = None
        num_starts = 0

    # --- KPI ---
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        kpi_with_status("Średni czas cyklu", avg_cycle_min, " min", 30, 120)
    with col2:
        # Starty na dobę (szacunkowo)
        total_hours = (df_pivot["czas"].max() - df_pivot["czas"].min()).total_seconds() / 3600 if len(df_pivot) > 1 else 1
        starts_per_day = num_starts / max(total_hours / 24, 0.01)
        kpi_with_status("Starty / dobę", starts_per_day, "", 0, 15, fmt=".0f")
    with col3:
        comp_freq_last = df_pivot["comp_freq"].dropna().iloc[-1] if safe_col(df_pivot, "comp_freq") else None
        st.metric("Częstotliwość spr.", f"{comp_freq_last:.0f} Hz" if comp_freq_last else "—")
    with col4:
        disc_last = df_pivot["disc_temp"].dropna().iloc[-1] if safe_col(df_pivot, "disc_temp") else None
        kpi_with_status("Temp. tłoczenia", disc_last, "°C", 40, 90)

    st.divider()

    # --- Timeline cykli ---
    st.markdown("##### ⏱️ Cykle pracy sprężarki")
    if safe_col(df_pivot, "comp_on"):
        # Tworzenie timeline jako area chart
        fig_timeline = go.Figure()
        fig_timeline.add_trace(go.Scatter(
            x=df_pivot["czas"], y=df_pivot["comp_on"],
            mode="lines", name="Sprężarka ON/OFF",
            line=dict(color="#4CAF50", width=1),
            fill="tozeroy", fillcolor="rgba(76,175,80,0.3)",
        ))
        fig_timeline.update_layout(
            yaxis=dict(tickvals=[0, 1], ticktext=["OFF", "ON"], range=[-0.1, 1.2]),
            height=150, margin=dict(t=10, b=30, l=50, r=20),
            showlegend=False,
        )
        st.plotly_chart(fig_timeline, use_container_width=True)
    else:
        st.info("Brak danych o pracy sprężarki.")

    # --- Histogram i starty dzienne ---
    col_a, col_b = st.columns(2)

    with col_a:
        st.markdown("##### 📊 Histogram długości cykli pracy")
        if len(work_periods) > 2:
            fig_hist = go.Figure()
            fig_hist.add_trace(go.Histogram(
                x=work_periods.values,
                nbinsx=15,
                marker_color="rgba(33,150,243,0.7)",
                name="Cykle"
            ))
            fig_hist.add_vline(x=30, line_dash="dash", line_color="rgba(255,152,0,0.8)",
                              annotation_text="Min. 30 min")
            fig_hist.add_vline(x=60, line_dash="dash", line_color="rgba(76,175,80,0.8)",
                              annotation_text="Idealne 60 min")
            fig_hist.update_layout(
                xaxis_title="Czas cyklu (min)", yaxis_title="Liczba cykli",
                height=320, margin=dict(t=20, b=40),
            )
            st.plotly_chart(fig_hist, use_container_width=True)
        else:
            st.info("Za mało cykli do histogramu.")

    with col_b:
        st.markdown("##### 📈 Starty sprężarki na dobę")
        if not daily_df_all.empty and "comp_start" in daily_df_all.columns:
            fig_starts = go.Figure()
            fig_starts.add_trace(go.Bar(
                x=daily_df_all["dzień"].astype(str), y=daily_df_all["comp_start"],
                name="Starty / dobę",
                marker_color="rgba(33,150,243,0.7)",
            ))
            fig_starts.add_hline(y=15, line_dash="dash", line_color="rgba(255,152,0,0.7)",
                                 annotation_text="Próg ostrzegawczy (15)")
            fig_starts.add_hline(y=20, line_dash="dash", line_color="rgba(244,67,54,0.7)",
                                 annotation_text="Próg krytyczny (20)")
            fig_starts.update_layout(
                yaxis_title="Starty", height=320, margin=dict(t=20, b=40),
            )
            st.plotly_chart(fig_starts, use_container_width=True)
        else:
            st.info("Brak danych dziennych o startach.")

    # --- Częstotliwość / modulacja ---
    st.markdown("##### ⚡ Częstotliwość sprężarki (modulacja) w czasie")
    if safe_col(df_pivot, "comp_freq"):
        fig_freq = go.Figure()
        fig_freq.add_trace(go.Scatter(
            x=df_pivot["czas"], y=df_pivot["comp_freq"],
            mode="lines", name="Częstotliwość (Hz)",
            line=dict(color="#9C27B0", width=2),
            fill="tozeroy", fillcolor="rgba(156,39,176,0.08)",
        ))
        fig_freq.update_layout(
            yaxis_title="Hz", height=300, margin=dict(t=20, b=40),
        )
        st.plotly_chart(fig_freq, use_container_width=True)
    else:
        st.info("Brak danych częstotliwości sprężarki.")

    # --- Alerty ---
    st.markdown("##### ⚠️ Alerty taktowania")
    if avg_cycle_min is not None and avg_cycle_min < 30:
        st.error(
            f"🚨 Średni czas cyklu = {avg_cycle_min:.0f} min (minimum 30 min). "
            "Sprężarka taktuje — sprawdź krzywą grzewczą i bufor ciepła."
        )
    elif starts_per_day > 15:
        st.warning(
            f"⚠️ {starts_per_day:.0f} startów/dobę (próg 15). Rozważ obniżenie nastaw lub zwiększenie histerezy."
        )
    else:
        st.success(f"✅ Praca sprężarki stabilna — śr. cykl {avg_cycle_min:.0f} min, {starts_per_day:.0f} startów/dobę." if avg_cycle_min else "✅ Brak danych do oceny, ale brak alertów.")


# ==============================================================================
# TAB 4: DEFROST I OBIEG CHŁODNICZY
# ==============================================================================
with tab_defr:
    st.subheader("❄️ Odszranianie i Obieg Chłodniczy")

    # --- Analiza cykli defrost ---
    if safe_col(df_pivot, "defrost_start") and safe_col(df_pivot, "defrost_num"):
        # Identyfikuj początki i końce defrostów
        defrost_starts_idx = df_pivot[df_pivot["defrost_start"] == 1].index.tolist()
        defrost_durations = []
        defrost_intervals = []

        for i, start_idx in enumerate(defrost_starts_idx):
            # Szukaj końca defrostu
            remaining = df_pivot.loc[start_idx:, "defrost_num"]
            end_mask = remaining == 0
            if end_mask.any():
                end_idx = end_mask.idxmax()
                duration_min = (df_pivot.loc[end_idx, "czas"] - df_pivot.loc[start_idx, "czas"]).total_seconds() / 60
                defrost_durations.append(duration_min)
            # Odstęp od poprzedniego
            if i > 0:
                interval_min = (df_pivot.loc[start_idx, "czas"] - df_pivot.loc[defrost_starts_idx[i - 1], "czas"]).total_seconds() / 60
                defrost_intervals.append(interval_min)

        num_defrosts = len(defrost_starts_idx)
        avg_defrost_duration = np.mean(defrost_durations) if defrost_durations else None
        avg_defrost_interval = np.mean(defrost_intervals) if defrost_intervals else None
    else:
        num_defrosts = 0
        avg_defrost_duration = None
        avg_defrost_interval = None
        defrost_durations = []
        defrost_intervals = []
        defrost_starts_idx = []

    # --- KPI ---
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Defrosty (okres)", f"{num_defrosts}")
    with col2:
        kpi_with_status("Śr. czas defrostu", avg_defrost_duration, " min", 3.0, 8.0)
    with col3:
        kpi_with_status("Śr. odstęp", avg_defrost_interval, " min", 45, 180)
    with col4:
        eev_last = df_pivot["m_eev"].dropna().iloc[-1] if safe_col(df_pivot, "m_eev") else None
        st.metric("Zawór EEV (m_eev)", f"{eev_last:.0f} kroków" if eev_last else "—")

    st.divider()

    # --- Timeline defrostów ---
    st.markdown("##### ❄️ Cykle defrost w czasie")
    if safe_col(df_pivot, "defrost_num"):
        fig_defrost_tl = go.Figure()
        fig_defrost_tl.add_trace(go.Scatter(
            x=df_pivot["czas"], y=df_pivot["defrost_num"],
            mode="lines", name="Defrost (aktywny=1)",
            line=dict(color="#00BCD4", width=2),
            fill="tozeroy", fillcolor="rgba(0,188,212,0.3)",
        ))
        fig_defrost_tl.update_layout(
            yaxis=dict(tickvals=[0, 1], ticktext=["OFF", "DEFROST"], range=[-0.1, 1.3]),
            height=150, margin=dict(t=10, b=30, l=50, r=20),
            showlegend=False,
        )
        st.plotly_chart(fig_defrost_tl, use_container_width=True)
    else:
        st.info("Brak danych o defrostach.")

    # --- Wykresy ---
    col_a, col_b = st.columns(2)

    with col_a:
        st.markdown("##### 🌡️ Defrost vs Temperatura zewnętrzna")
        if defrost_starts_idx and safe_col(df_pivot, "amb_temp"):
            scatter_data = []
            for i, idx in enumerate(defrost_starts_idx):
                amb = df_pivot.loc[idx, "amb_temp"] if pd.notna(df_pivot.loc[idx, "amb_temp"]) else None
                dur = defrost_durations[i] if i < len(defrost_durations) else None
                if amb is not None and dur is not None:
                    scatter_data.append({"Temp. zewn. (°C)": amb, "Czas trwania (min)": dur})
            if scatter_data:
                sdf = pd.DataFrame(scatter_data)
                fig_def_temp = px.scatter(
                    sdf, x="Temp. zewn. (°C)", y="Czas trwania (min)",
                    color_discrete_sequence=["#00BCD4"],
                    size="Czas trwania (min)", size_max=15,
                )
                fig_def_temp.add_vrect(x0=-3, x1=5,
                                       fillcolor="rgba(0,188,212,0.05)", line_width=0,
                                       annotation_text="Strefa typowych defrostów")
                fig_def_temp.update_layout(height=320, margin=dict(t=20, b=40))
                st.plotly_chart(fig_def_temp, use_container_width=True)
            else:
                st.info("Brak danych do wykresu scatter defrost/temp.")
        else:
            st.info("Za mało danych defrost.")

    with col_b:
        st.markdown("##### ⏱️ Odstępy między cyklami defrost")
        if defrost_intervals:
            fig_intervals = go.Figure()
            colors = ["#f44336" if v < 45 else "#FF9800" if v < 60 else "#00BCD4" for v in defrost_intervals]
            fig_intervals.add_trace(go.Bar(
                x=list(range(1, len(defrost_intervals) + 1)),
                y=defrost_intervals,
                marker_color=colors,
                name="Odstęp (min)",
            ))
            fig_intervals.add_hline(y=45, line_dash="dash", line_color="rgba(255,152,0,0.7)",
                                    annotation_text="Min. 45 min")
            fig_intervals.update_layout(
                xaxis_title="Nr cyklu", yaxis_title="Minuty",
                height=320, margin=dict(t=20, b=40),
            )
            st.plotly_chart(fig_intervals, use_container_width=True)
        else:
            st.info("Za mało cykli defrost do analizy odstępów.")

    # --- EEV i wentylator ---
    col_c, col_d = st.columns(2)

    with col_c:
        st.markdown("##### 🔧 Zawór rozprężny EEV w czasie")
        if safe_col(df_pivot, "m_eev") or safe_col(df_pivot, "a_eev"):
            fig_eev = go.Figure()
            if safe_col(df_pivot, "m_eev"):
                fig_eev.add_trace(go.Scatter(
                    x=df_pivot["czas"], y=df_pivot["m_eev"],
                    mode="lines", name="m_eev (główny)",
                    line=dict(color="#FF9800", width=2),
                ))
            if safe_col(df_pivot, "a_eev"):
                fig_eev.add_trace(go.Scatter(
                    x=df_pivot["czas"], y=df_pivot["a_eev"],
                    mode="lines", name="a_eev (dodatkowy)",
                    line=dict(color="#9C27B0", width=2),
                    yaxis="y2",
                ))
            fig_eev.update_layout(
                yaxis=dict(title="m_eev (kroki)"),
                yaxis2=dict(title="a_eev", overlaying="y", side="right"),
                height=320, margin=dict(t=20, b=40),
            )
            st.plotly_chart(fig_eev, use_container_width=True)
        else:
            st.info("Brak danych EEV.")

    with col_d:
        st.markdown("##### 🌀 Wentylator DC Fan 1")
        if safe_col(df_pivot, "dc_fan1"):
            fig_fan = go.Figure()
            fig_fan.add_trace(go.Scatter(
                x=df_pivot["czas"], y=df_pivot["dc_fan1"],
                mode="lines", name="DC Fan 1 (RPM)",
                line=dict(color="#4CAF50", width=2),
                fill="tozeroy", fillcolor="rgba(76,175,80,0.1)",
            ))
            fig_fan.update_layout(
                yaxis_title="RPM", height=320, margin=dict(t=20, b=40),
            )
            st.plotly_chart(fig_fan, use_container_width=True)
        else:
            st.info("Brak danych DC Fan 1.")

    # --- Alerty defrost ---
    st.markdown("##### ⚠️ Alerty defrost")
    alerts_fired = False
    if defrost_intervals:
        short_intervals = [v for v in defrost_intervals if v < 30]
        if short_intervals:
            st.error(
                f"🚨 Znaleziono {len(short_intervals)} defrostów z odstępem < 30 min. "
                "Możliwy problem: zablokowany parownik, uszkodzony wentylator lub niedobór czynnika."
            )
            alerts_fired = True
    if defrost_durations:
        long_defrosts = [v for v in defrost_durations if v > 10]
        if long_defrosts:
            st.warning(
                f"⚠️ {len(long_defrosts)} defrostów trwało dłużej niż 10 min (norma 3-8 min). "
                "Sprawdź wentylator parownika i poziom czynnika."
            )
            alerts_fired = True
    if not alerts_fired:
        st.success("✅ Cykle defrost w normie — czasy i odstępy prawidłowe.")
