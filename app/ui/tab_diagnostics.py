"""Zakładka: Diagnostyka Pompy Ciepła."""
import pandas as pd
import numpy as np
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime

from app.services.analytics import DiagnosticReport
from app.services.database import get_fault_history, get_active_faults
from app.config import HEAT_PUMP_DEV_ID


def render(
    df_empty: bool,
    df_pivot: pd.DataFrame,
    daily_df_all: pd.DataFrame,
    diagnostic_report: DiagnosticReport | None
):
    """Renderuje zakładkę Diagnostyka."""
    st.header("🏥 Centrum Diagnostyczne Pompy Ciepła")

    if df_empty or df_pivot is None or df_pivot.empty:
        st.info("Brak danych diagnostycznych.")
        return

    st.subheader("📋 Raport Zaawansowanej Diagnostyki")

    if diagnostic_report:
        _render_advanced_diagnostics(df_pivot, diagnostic_report)

    st.markdown("---")
    _render_standard_diagnostics(df_pivot, daily_df_all)

    st.markdown("---")
    _render_fault_history()


def _render_advanced_diagnostics(df_pivot: pd.DataFrame, report: DiagnosticReport):
    """Sekcja zaawansowanej diagnostyki."""
    diag_col1, diag_col2, diag_col3, diag_col4 = st.columns(4)

    # Cykle krótkie
    short_cycles_count = len(report.short_cycles)
    if short_cycles_count > 0:
        diag_col1.warning(f"⚠️ Wykryto cykli krótkich: **{short_cycles_count}**")
        total_wasted = sum(c.energy_wasted_kwh for c in report.short_cycles)
        diag_col1.metric("Energia zmarnowana na cykle", f"{total_wasted:.2f} kWh")
    else:
        diag_col1.success("✅ Brak cykli krótkich")

    # Analiza inwertera
    if report.inverter_analysis:
        inv = report.inverter_analysis
        diag_col2.metric("Śr. częstotliwość sprężarki", f"{inv.avg_frequency:.1f} Hz")
        diag_col2.metric("Stabilność pracy", f"{inv.stability_score:.0f}/100")
        # Próg frequent_starts z analytics zależy od zakresu — pokazuj tylko jeśli >6/dzień
        if not df_pivot.empty and 'czas' in df_pivot.columns:
            days_span = max((df_pivot['czas'].max() - df_pivot['czas'].min()).total_seconds() / 86400, 1)
        else:
            days_span = 1
        starts_per_day_inv = inv.frequent_starts / days_span
        if starts_per_day_inv > 12:
            diag_col2.warning(f"Częste starty: {inv.frequent_starts} ({starts_per_day_inv:.1f}/dzień)")

    # Analiza trybów
    if report.mode_analysis:
        mode = report.mode_analysis
        diag_col3.metric("Czas pracy CO", f"{mode.co_runtime_hours:.1f} h")
        diag_col3.metric("Czas pracy CWU", f"{mode.cwu_runtime_hours:.1f} h")
        diag_col3.metric("Przełączeń trybów", f"{mode.mode_transitions}")

    # Korelacja pogodowa
    if report.weather_correlation:
        weather = report.weather_correlation
        diag_col4.metric("Śr. temperatura zewn.", f"{weather.temp_outside_avg:.1f}°C")
        diag_col4.metric("Korelacja COP↔Temp", f"{weather.cop_vs_temp_correlation:.2f}")

    st.markdown("---")

    # Rekomendacje
    if report.recommendations:
        st.subheader("💡 Rekomendacje")
        for i, rec in enumerate(report.recommendations, 1):
            if "krótkich" in rec.lower() or "taktowanie" in rec.lower():
                st.error(f"**{i}.** {rec}")
            elif "optymalizacji" in rec.lower() or "efektywności" in rec.lower():
                st.warning(f"**{i}.** {rec}")
            else:
                st.info(f"**{i}.** {rec}")

    st.markdown("---")
    st.subheader("📊 Szczegółowa analiza inwertera")

    if report.inverter_analysis:
        inv = report.inverter_analysis
        inv_col1, inv_col2, inv_col3 = st.columns(3)
        inv_col1.metric("Min częstotliwość", f"{inv.min_frequency:.1f} Hz")
        inv_col1.metric("Max częstotliwość", f"{inv.max_frequency:.1f} Hz")
        inv_col2.metric("Odchylenie std", f"{inv.std_frequency:.1f} Hz")
        inv_col2.metric("Efektywność modulacji", f"{inv.modulation_efficiency:.1f}%")
        inv_col3.metric("Czas w zakresie opt. (30-60 Hz)", f"{inv.optimal_range_pct:.1f}%")

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

    if report.short_cycles:
        cycles_data = []
        for cycle in report.short_cycles:
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


def _render_standard_diagnostics(df_pivot: pd.DataFrame, daily_df_all: pd.DataFrame):
    """Sekcja standardowej diagnostyki — ostrzeżenia i wykresy."""
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
    
    # Oblicz liczbę dni w zakresie danych
    if not df_pivot.empty and 'czas' in df_pivot.columns:
        time_span_days = max((df_pivot['czas'].max() - df_pivot['czas'].min()).total_seconds() / 86400, 1)
    else:
        time_span_days = 1
    starts_per_day = starts_count / time_span_days
    
    with col_a3:
        # Taktowanie = więcej niż 12 startów dziennie
        if starts_per_day > 12:
            st.warning(f"🟡 **Wykryto taktowanie!** Starty: **{starts_count}** ({starts_per_day:.1f}/dzień)")
        else:
            st.success(f"🟢 **Cykliczność w normie:** Starty: **{starts_count}** ({starts_per_day:.1f}/dzień)")

    st.markdown("---")
    st.subheader("📊 Tabela: Statystyki dzienne pracy sprężarki")

    if not daily_df_all.empty:
        daily_comp_stats = daily_df_all[["dzień", "comp_start", "dt_hours_work"]].copy()
        daily_comp_stats.columns = ["Data", "Liczba startów", "Czas pracy [h]"]
        daily_comp_stats["Śr. czas pracy/start [min]"] = np.where(
            daily_comp_stats["Liczba startów"] > 0,
            (daily_comp_stats["Czas pracy [h]"] / daily_comp_stats["Liczba startów"]) * 60,
            0.0
        )
        daily_comp_stats["Czas pracy [h]"] = daily_comp_stats["Czas pracy [h]"].round(2)
        daily_comp_stats["Śr. czas pracy/start [min]"] = daily_comp_stats["Śr. czas pracy/start [min]"].round(1)
        daily_comp_stats["Liczba startów"] = daily_comp_stats["Liczba startów"].astype(int)
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



def _render_fault_history():
    """Sekcja historii awarii pompy."""
    st.subheader("🚨 Historia Awarii")

    # Aktywne awarie
    active = get_active_faults(HEAT_PUMP_DEV_ID)
    if active:
        st.error(f"**{len(active)} aktywnych awarii:**")
        for _, ts, code, bitmap in active:
            ts_str = datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")
            st.markdown(f"- 🔴 **{code}** — od {ts_str}")
    else:
        st.success("✅ Brak aktywnych awarii")

    # Historia
    history = get_fault_history(HEAT_PUMP_DEV_ID, limit=50)
    if history:
        rows = []
        for _, ts, code, bitmap, resolved, resolved_at in history:
            ts_str = datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")
            if resolved and resolved_at:
                res_str = datetime.fromtimestamp(resolved_at).strftime("%Y-%m-%d %H:%M")
                duration_sec = resolved_at - ts
                if duration_sec < 60:
                    dur_str = f"{duration_sec:.0f} s"
                elif duration_sec < 3600:
                    dur_str = f"{duration_sec / 60:.0f} min"
                else:
                    dur_str = f"{duration_sec / 3600:.1f} h"
                status = "✅ Rozwiązana"
            else:
                res_str = "—"
                dur_str = "trwa..."
                status = "🔴 Aktywna"
            rows.append({
                "Status": status,
                "Kod": code,
                "Początek": ts_str,
                "Koniec": res_str,
                "Czas trwania": dur_str,
            })

        history_df = pd.DataFrame(rows)
        st.dataframe(history_df, width="stretch", hide_index=True)
    else:
        st.info("Brak zarejestrowanych awarii w historii.")
