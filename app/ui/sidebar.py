"""Panel boczny dashboardu — ustawienia zakresu czasu, kalibracji, kosztów."""
import streamlit as st
from dataclasses import dataclass

from app.services.database import get_current_work_mode, get_current_auto_target

# Mapowanie work_mode na ikonę i opis (z oficjalnej specyfikacji modelu Tuya)
WORK_MODE_DISPLAY = {
    "heat": ("🔥", "Ogrzewanie (CO)"),
    "hot_water": ("🚿", "Ciepła woda (CWU)"),
    "heat_hot_water": ("🔥🚿", "CO + CWU"),
    "cool": ("❄️", "Chłodzenie"),
    "cool_hot_water": ("❄️🚿", "Chłodzenie + CWU"),
    "auto": ("🔄", "Auto"),
    "auto_dhw": ("🔄🚿", "Auto + CWU"),
}

# Podikona auto_run_tar_mode: co pompa faktycznie robi w trybie auto
AUTO_TARGET_ICON = {
    "0": "❄️",  # chłodzenie
    "1": "🔥",  # ogrzewanie
}


@dataclass
class SidebarSettings:
    """Ustawienia użytkownika z panelu bocznego."""
    hours_back: int
    selected_range: str
    resample_rule: str | None
    cos_phi: float
    standby_power_w: int
    active_power_w: int
    time_offset_hours: int
    electricity_price: float
    gas_price: float


def render_sidebar() -> SidebarSettings:
    """Renderuje panel boczny i zwraca ustawienia użytkownika."""
    st.sidebar.header("⏱️ Zakres danych")
    time_range_map = {
        "Dzisiaj": 24,
        "Ostatnie 3 dni": 72,
        "Ostatnie 7 dni": 168,
        "Ostatnie 30 dni": 720,
        "Ostatnie 90 dni": 2160
    }
    selected_range = st.sidebar.selectbox("Wybierz zakres czasu:", list(time_range_map.keys()), index=0)
    hours_back = time_range_map[selected_range]

    st.sidebar.header("📊 Optymalizacja wykresów")
    resample_map = {
        "Brak (Surowe dane)": None,
        "Co 1 minuta": "1min",
        "Co 5 minut": "5min",
        "Co 15 minut": "15min"
    }
    selected_resample = st.sidebar.selectbox("Agregacja punktów:", list(resample_map.keys()), index=1)
    resample_rule = resample_map[selected_resample]

    # Sekcje zwinięte
    with st.sidebar.expander("⚙️ Kalkulator COP i Kalibracja"):
        from app.services.database import get_setting, set_setting
        saved_cos_phi = float(get_setting("cos_phi", "1.00"))
        saved_standby = int(get_setting("standby_power_w", "15"))
        saved_active = int(get_setting("active_power_w", "130"))

        cos_phi = st.slider("Współczynnik mocy (cos φ)", 0.80, 1.00, saved_cos_phi, 0.01)
        st.subheader("🛠️ Kalibracja strat mocy")
        standby_power_w = st.number_input("Pobór w spoczynku (elektronika) [W]", min_value=0, max_value=100, value=saved_standby, step=5)
        active_power_w = st.number_input("Pobór pracy (wentylator, pompa obieg.) [W]", min_value=0, max_value=300, value=saved_active, step=10)

        # Zapisz zmiany do bazy
        if cos_phi != saved_cos_phi:
            set_setting("cos_phi", str(cos_phi))
        if standby_power_w != saved_standby:
            set_setting("standby_power_w", str(standby_power_w))
        if active_power_w != saved_active:
            set_setting("active_power_w", str(active_power_w))

    with st.sidebar.expander("🕐 Korekta czasu i Koszty"):
        time_offset_hours = st.slider(
            "Przesunięcie czasu (godziny)",
            min_value=-12,
            max_value=12,
            value=2,
            step=1,
            help="Dodaje przesunięcie do czasu serwera, aby wyświetlać prawidłowy czas lokalny"
        )
        st.subheader("💰 Ceny energii")
        saved_el_price = float(get_setting("electricity_price", "1.10"))
        saved_gas_price = float(get_setting("gas_price", "0.37"))

        electricity_price = st.number_input(
            "Cena prądu [zł/kWh]",
            min_value=0.0,
            max_value=5.0,
            value=saved_el_price,
            step=0.01,
            help="Cena energii elektrycznej używana do obliczeń kosztów eksploatacji pompy ciepła"
        )
        gas_price = st.number_input(
            "Cena gazu [zł/kWh]",
            min_value=0.0,
            max_value=5.0,
            value=saved_gas_price,
            step=0.01,
            help="Cena gazu używana do porównania kosztów (próg opłacalności SCOP)"
        )

        if electricity_price != saved_el_price:
            set_setting("electricity_price", str(electricity_price))
        if gas_price != saved_gas_price:
            set_setting("gas_price", str(gas_price))

    # Tryb pracy pompy — na dole panelu bocznego
    st.sidebar.markdown("---")
    st.sidebar.caption("Tryb pracy")
    work_mode = get_current_work_mode()
    if work_mode:
        icon, _ = WORK_MODE_DISPLAY.get(work_mode, ("❓", ""))
        # W trybie auto — pokaż co pompa faktycznie robi (grzeje/chłodzi)
        sub_icon = ""
        if work_mode in ("auto", "auto_dhw"):
            auto_target = get_current_auto_target()
            if auto_target is not None:
                sub_icon = AUTO_TARGET_ICON.get(str(auto_target), "")
    else:
        icon = "⚪"
        sub_icon = ""

    icon_html = f'{icon}'
    if sub_icon:
        icon_html += f'<span style="font-size:1.5rem;"> → {sub_icon}</span>'
    st.sidebar.markdown(
        f'<div style="text-align:center;font-size:3rem;line-height:1.2;">{icon_html}</div>',
        unsafe_allow_html=True,
    )

    with st.sidebar.expander("ℹ️ About"):
        st.markdown(
            "**Heat Pump Monitor** v1.0\n\n"
            "Monitoring pompy ciepła w czasie rzeczywistym "
            "przez Tuya Pulsar API.\n\n"
            "📊 SCOP, COP, bilans energetyczny\n"
            "📈 Krzywa grzewcza, diagnostyka\n"
            "🚨 Alerty awarii (Telegram)\n"
            "🌤️ Korelacja z pogodą\n\n"
            "Dane: SQLite · UI: Streamlit + Plotly\n\n"
            "✉️ wiktor79@o2.pl"
        )

    return SidebarSettings(
        hours_back=hours_back,
        selected_range=selected_range,
        resample_rule=resample_rule,
        cos_phi=cos_phi,
        standby_power_w=standby_power_w,
        active_power_w=active_power_w,
        time_offset_hours=time_offset_hours,
        electricity_price=electricity_price,
        gas_price=gas_price,
    )
