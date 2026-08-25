"""Zakładka: Kontekst Pogodowy i wpływ na wydajność."""
import pandas as pd
import numpy as np
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta

from app.services.analytics import DiagnosticReport


def render(
    df_pivot: pd.DataFrame,
    weather_df: pd.DataFrame,
    diagnostic_report: DiagnosticReport | None,
    time_offset_hours: int
):
    """Renderuje zakładkę Kontekst Pogodowy."""
    st.header("🌤️ Kontekst Pogodowy i Wpływ na Wydajność")

    if df_pivot is None or df_pivot.empty:
        st.info("Brak danych do analizy korelacji pogodowych.")
        return

    if diagnostic_report and diagnostic_report.weather_correlation:
        weather = diagnostic_report.weather_correlation
        _render_weather_metrics(weather)
        st.markdown("---")
        _render_cop_temp_ranges(weather)
        st.markdown("---")
        _render_cop_scatter(df_pivot)
        st.markdown("---")
        _render_temp_comparison(df_pivot, weather_df, time_offset_hours)
        st.markdown("---")
        _render_temp_cop_dual_axis(df_pivot)
    else:
        st.warning("Nie udało się wygenerować raportu korelacji pogodowej. Sprawdź czy dane pogodowe są dostępne.")

    st.markdown("---")
    _render_weather_table(weather_df, time_offset_hours)


def _render_weather_metrics(weather):
    """Metryki pogodowe."""
    wx_col1, wx_col2, wx_col3, wx_col4 = st.columns(4)
    wx_col1.metric("Średnia temperatura zewn.", f"{weather.temp_outside_avg:.1f}°C")
    wx_col2.metric("Korelacja COP↔Temp", f"{weather.cop_vs_temp_correlation:.2f}",
                  help="Współczynnik korelacji Pearsona (-1 do 1). Wartości dodatnie oznaczają że COP rośnie z temperaturą.")
    wx_col3.metric("Spadek COP na °C", f"{weather.efficiency_drop_per_degree:.3f}",
                  help="O ile spada COP przy spadku temperatury o 1°C")
    wx_col4.metric("HDD (Heating Degree Days)", f"{weather.heating_degree_days:.1f}",
                  help="Stopniodni grzania - miara chłodu okresu")


def _render_cop_temp_ranges(weather):
    """COP w zakresach temperatur."""
    st.subheader("📊 COP w zależności od zakresu temperatury")

    if weather.cop_at_temp_ranges:
        ranges_df = pd.DataFrame([
            {"Zakres temp.": range_label.replace("_", " ").title(), "Śr. COP": cop}
            for range_label, cop in weather.cop_at_temp_ranges.items()
        ])
        st.dataframe(ranges_df, use_container_width=True, hide_index=True)

        fig_cop_ranges = px.bar(
            ranges_df, x="Zakres temp.", y="Śr. COP",
            title="Średnie COP w różnych zakresach temperatur zewnętrznych",
            labels={"Zakres temp.": "Zakres temperatury [°C]", "Śr. COP": "COP"},
            color="Śr. COP", color_continuous_scale="RdYlGn"
        )
        fig_cop_ranges.update_layout(coloraxis_showscale=False)
        st.plotly_chart(fig_cop_ranges, use_container_width=True)

    opt_range = weather.optimal_temp_range
    if opt_range[0] != opt_range[1]:
        st.success(f"🎯 **Optymalny zakres temperatur dla najlepszego COP:** {opt_range[0]:.1f}°C do {opt_range[1]:.1f}°C")


def _render_cop_scatter(df_pivot: pd.DataFrame):
    """Scatter COP vs temperatura zewnętrzna."""
    st.subheader("📈 Korelacja COP z temperaturą zewnętrzną")

    if 'amb_temp' not in df_pivot.columns or df_pivot['amb_temp'].isna().all():
        return

    scatter_df = df_pivot[['czas', 'COP', 'amb_temp', 'P_el_kw', 'Tryb']].dropna().copy()
    if scatter_df.empty:
        return

    fig_scatter = px.scatter(
        scatter_df, x='amb_temp', y='COP', color='Tryb', size='P_el_kw',
        hover_data=['czas'],
        title="Zależność COP od temperatury zewnętrznej (rozmiar = moc elektryczna)",
        labels={'amb_temp': 'Temperatura zewnętrzna [°C]', 'COP': 'COP', 'Tryb': 'Tryb pracy'},
        color_discrete_map={"CO": "#2ECC71", "CWU": "#E67E22"}
    )

    if len(scatter_df) > 10:
        z = np.polyfit(scatter_df['amb_temp'].dropna(), scatter_df['COP'].dropna(), 1)
        p = np.poly1d(z)
        fig_scatter.add_trace(go.Scatter(
            x=scatter_df['amb_temp'].sort_values(),
            y=p(scatter_df['amb_temp'].sort_values()),
            mode='lines', name='Trend liniowy',
            line=dict(color='red', width=2, dash='dash')
        ))

    st.plotly_chart(fig_scatter, use_container_width=True)


def _render_temp_comparison(df_pivot: pd.DataFrame, weather_df: pd.DataFrame, time_offset_hours: int):
    """Porównanie temp: serwis pogodowy vs pompa."""
    st.subheader("🌡️ Porównanie temperatury: Serwis pogodowy vs Pompa ciepła")

    if weather_df.empty:
        st.info("Brak danych pogodowych z serwisu internetowego.")
        return
    if 'amb_temp' not in df_pivot.columns:
        st.info("Brak danych o temperaturze zewnętrznej z pompy ciepła.")
        return

    weather_df_copy = weather_df.copy()
    weather_df_copy['timestamp'] = pd.to_datetime(weather_df_copy['timestamp'], unit='s')
    weather_df_copy['timestamp'] = weather_df_copy['timestamp'] + pd.Timedelta(hours=time_offset_hours)

    if df_pivot.empty or 'czas' not in df_pivot.columns:
        st.info("Brak danych temperaturowych z pompy ciepła.")
        return

    min_time = df_pivot['czas'].min()
    max_time = df_pivot['czas'].max()
    weather_filtered = weather_df_copy[
        (weather_df_copy['timestamp'] >= min_time) &
        (weather_df_copy['timestamp'] <= max_time)
    ].copy()

    if weather_filtered.empty:
        st.info("Brak danych pogodowych w wybranym zakresie czasu.")
        return

    fig_compare = go.Figure()
    fig_compare.add_trace(go.Scatter(
        x=weather_filtered['timestamp'], y=weather_filtered['temperature'],
        mode='lines', name='Serwis pogodowy (Open-Meteo)',
        line=dict(color='#3498DB', width=2)
    ))

    pump_temp_df = df_pivot[df_pivot['amb_temp'].notna()].copy()
    if not pump_temp_df.empty:
        fig_compare.add_trace(go.Scatter(
            x=pump_temp_df['czas'], y=pump_temp_df['amb_temp'],
            mode='lines', name='Pompa ciepła (odczyt)',
            line=dict(color='#E74C3C', width=2, dash='dash')
        ))

    fig_compare.update_layout(
        title="Porównanie temperatury zewnętrznej: dane pogodowe vs odczyt z pompy",
        xaxis=dict(title="Czas"), yaxis=dict(title="Temperatura [°C]"),
        hovermode='x unified', legend=dict(x=0, y=1.1, orientation='h')
    )
    st.plotly_chart(fig_compare, use_container_width=True)


def _render_temp_cop_dual_axis(df_pivot: pd.DataFrame):
    """Wykres dwuosiowy: temp zewn. vs COP."""
    st.subheader("📊 Przebieg czasowy: Temperatura zewnętrzna i COP")

    if 'amb_temp' not in df_pivot.columns or df_pivot['amb_temp'].isna().all():
        return

    temp_df = df_pivot[df_pivot['amb_temp'].notna()].copy()
    if temp_df.empty:
        st.info("Brak danych o temperaturze zewnętrznej w wybranym zakresie czasu.")
        return

    fig_dual = go.Figure()
    fig_dual.add_trace(go.Scatter(
        x=temp_df['czas'], y=temp_df['amb_temp'],
        mode='lines', name='Temp. zewn. [°C]',
        line=dict(color='#3498DB', width=2), yaxis='y1'
    ))
    fig_dual.add_trace(go.Scatter(
        x=df_pivot['czas'], y=df_pivot['COP'],
        mode='lines', name='COP',
        line=dict(color='#E67E22', width=2), yaxis='y2'
    ))
    fig_dual.update_layout(
        title="Temperatura zewnętrzna vs COP w czasie",
        xaxis=dict(title="Czas"),
        yaxis=dict(title="Temperatura [°C]", overlaying='y2'),
        yaxis2=dict(title="COP", side='right', overlaying='y'),
        hovermode='x unified', legend=dict(x=0, y=1.1, orientation='h')
    )
    st.plotly_chart(fig_dual, use_container_width=True)


def _render_weather_table(weather_df: pd.DataFrame, time_offset_hours: int):
    """Tabela ostatnich danych pogodowych."""
    st.subheader("📋 Ostatnie dane pogodowe z bazy")

    if weather_df.empty:
        st.info("Brak zapisanych danych pogodowych w bazie. Upewnij się że usługa pobierania pogody działa.")
        return

    now_local = datetime.now() + timedelta(hours=time_offset_hours)
    start_of_day_local = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
    start_query_time = start_of_day_local - timedelta(hours=time_offset_hours)
    weather_today = weather_df[weather_df['timestamp'] >= start_query_time.timestamp()].copy()

    if weather_today.empty:
        st.info("Brak danych pogodowych w wybranym zakresie (dzisiejszy dzień).")
        return

    weather_display = weather_today[['timestamp', 'temperature', 'humidity', 'pressure', 'wind_speed']].copy()
    weather_display['timestamp'] = pd.to_datetime(weather_display['timestamp'], unit='s')
    weather_display['timestamp'] = weather_display['timestamp'] + pd.Timedelta(hours=time_offset_hours)
    weather_display['timestamp'] = weather_display['timestamp'].dt.strftime('%Y-%m-%d %H:%M')
    weather_display.columns = ['Czas', 'Temp. [°C]', 'Wilgotność [%]', 'Ciśnienie [hPa]', 'Wiatr [m/s]']
    st.dataframe(weather_display.head(20), use_container_width=True, hide_index=True)
