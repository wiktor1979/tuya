"""Dashboard Streamlit — orkiestrator modułów UI."""
import datetime
import pandas as pd
import streamlit as st

from app.services.data_loader import (
    get_pump_status_for_refresh,
    load_pump_data,
    process_telemetry,
    compute_daily_stats,
    compute_scop_metrics,
    compute_operational_stats,
)
from app.services.database import get_weather_data
from app.services.analytics import generate_diagnostic_report
from app.ui.styles import inject_css
from app.ui.sidebar import render_sidebar
from app.ui import tab_main, tab_scop, tab_diagnostics, tab_weather, tab_meter, tab_export

# --- KONFIGURACJA STRONY ---
st.set_page_config(page_title="Monitor Pompy Ciepła", layout="wide", page_icon="🔥")
inject_css()

# --- NAGŁÓWEK I SIDEBAR (poza fragmentem — nie migają) ---
st.markdown(
    '<h3 style="margin:0;padding:0.2rem 0;">🔥 Monitor Pompy Ciepła</h3>',
    unsafe_allow_html=True,
)
settings = render_sidebar()

# --- STATUS POMPY I INTERWAŁ ---
pump_running = get_pump_status_for_refresh()
interval_sec = 60 if pump_running else 300

if st.button("🔄 Odśwież dane"):
    st.rerun()


# --- FRAGMENT Z DANYMI — odświeżany automatycznie co interval_sec ---
@st.fragment(run_every=interval_sec)
def render_dashboard(settings):
    """Główna treść dashboardu — odświeżana automatycznie."""

    # Status z aktualnym czasem
    status_icon = "🟢" if get_pump_status_for_refresh() else "⚪"
    status_text = "Pompa pracuje — co 1 min" if get_pump_status_for_refresh() else "Pompa stoi — co 5 min"
    now_str = datetime.datetime.now().strftime("%H:%M:%S")
    st.caption(f"{status_icon} {status_text} · Odświeżono: {now_str}")

    # --- ŁADOWANIE DANYCH ---
    is_today_range = (settings.selected_range == "Dzisiaj")
    df = load_pump_data(settings.hours_back, is_today=is_today_range)
    df_all_time = load_pump_data(settings.hours_back, all_time=True)

    # Przetwarzanie telemetrii
    df_pivot = process_telemetry(
        df.copy(), settings.time_offset_hours,
        settings.cos_phi, settings.standby_power_w, settings.active_power_w,
        settings.resample_rule
    )

    df_pivot_all = process_telemetry(
        df_all_time.copy(), settings.time_offset_hours,
        settings.cos_phi, settings.standby_power_w, settings.active_power_w,
        None
    )

    # Statystyki dzienne
    daily_df = compute_daily_stats(df_pivot, settings.time_offset_hours)
    daily_df_all = compute_daily_stats(df_pivot_all, settings.time_offset_hours)

    # Metryki SCOP i operacyjne
    scop = compute_scop_metrics(df_pivot)
    ops = compute_operational_stats(daily_df, df_pivot)

    # --- DANE POGODOWE ---
    weather_df = pd.DataFrame()
    if df_pivot is not None and not df_pivot.empty:
        try:
            weather_data = get_weather_data(days=max(30, settings.hours_back // 24 + 1), is_today=is_today_range)
            if weather_data and len(weather_data) > 0 and len(weather_data[0]) >= 8:
                weather_df = pd.DataFrame(weather_data, columns=['id', 'timestamp', 'temperature', 'humidity', 'windspeed', 'precipitation', 'latitude', 'longitude', 'direct_radiation', 'diffuse_radiation'][:len(weather_data[0])])
                weather_df = weather_df.rename(columns={'windspeed': 'wind_speed'})
                if 'pressure' not in weather_df.columns:
                    weather_df['pressure'] = 1013.0
                if 'cloud_cover' not in weather_df.columns:
                    weather_df['cloud_cover'] = 0.0
        except Exception as e:
            st.warning(f"Nie udało się załadować danych pogodowych: {e}")

    # --- RAPORT DIAGNOSTYCZNY ---
    diagnostic_report = None
    if df_pivot is not None and not df_pivot.empty:
        try:
            diagnostic_report = generate_diagnostic_report(
                df=df_pivot,
                weather_df=weather_df,
                electricity_price=settings.electricity_price
            )
        except Exception as e:
            st.warning(f"Błąd generowania raportu diagnostycznego: {e}")

    # --- ZAKŁADKI ---
    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
        "📊 Panel Główny",
        "🏆 Bilans Energetyczny & SCOP",
        "🏥 Diagnostyka Pompy",
        "🌤️ Kontekst Pogodowy",
        "⚡ Fizyczny Licznik Energii",
        "📁 Eksport Danych"
    ])

    with tab1:
        tab_main.render(df, df_pivot, settings.resample_rule, settings.time_offset_hours)

    with tab2:
        tab_scop.render(df.empty, scop, ops, daily_df_all)

    with tab3:
        tab_diagnostics.render(df.empty, df_pivot, daily_df_all, diagnostic_report)

    with tab4:
        tab_weather.render(df_pivot, weather_df, diagnostic_report, settings.time_offset_hours)

    with tab5:
        tab_meter.render(daily_df_all, settings.time_offset_hours)

    with tab6:
        tab_export.render(df, df_pivot, daily_df, settings.hours_back)


# Uruchomienie fragmentu
render_dashboard(settings)
