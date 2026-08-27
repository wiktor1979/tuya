"""Style CSS i stałe wizualne dashboardu."""
import streamlit as st

# --- SŁOWNIK METADANYCH PARAMETRÓW POMPY ---
PARAM_INFO = {
    "in_water_temp": {"label": "Powrót CO", "desc": "Temperatura wody powracającej z instalacji grzewczej"},
    "out_water_temp": {"label": "Zasilanie CO", "desc": "Temperatura wody wychodzącej na dom"},
    "tank_temp": {"label": "Woda CWU", "desc": "Temperatura wody w zasobniku ciepłej wody użytkowej"},
    "amb_temp": {"label": "Temp. zewnętrzna", "desc": "Temperatura powietrza na zewnątrz budynku"},
    "disc_temp": {"label": "Tłoczenie sprężarki", "desc": "Temperatura gazu na wylocie/tłoczeniu sprężarki (Discharge)"},
    "back_temp": {"label": "Powrót do sprężarki", "desc": "Temperatura czynnika na powrocie do sprężarki (Suction)"},
    "tidr": {"label": "Temp. ssania", "desc": "Temperatura czujnika ssania / wymiennika chłodniczego"},
    "heat_temp_set": {"label": "Nastawa CO", "desc": "Docelowa zadana temperatura dla trybu ogrzewania CO"},
    "cool_temp_set": {"label": "Nastawa Chłodzenia", "desc": "Docelowa zadana temperatura dla trybu chłodzenia"},
    "hot_water_temp_set": {"label": "Nastawa CWU", "desc": "Docelowa zadana temperatura dla wody użytkowej"},
    "ac_vol": {"label": "Napięcie AC", "desc": "Napięcie zasilania sieciowego AC podawane do jednostki"},
    "ac_curr": {"label": "Prąd AC", "desc": "Natężenie prądu pobieranego przez urządzenie"},
    "comp_freq": {"label": "Częstotliwość sprężarki", "desc": "Aktualna częstotliwość pracy sprężarki (Hz)"},
    "flow_rate": {"label": "Przepływ", "desc": "Przepływ wody w obiegu hydraulicznym"},
    "m_eev": {"label": "Zawór EEV główny", "desc": "Pozycja otwarcia głównego elektronicznego zaworu rozprężnego"},
    "valve": {"label": "Zawór 3-drożny", "desc": "Stan zaworu przełączającego (0 = CO, 1 = CWU)"},
    "defrost": {"label": "Odszranianie", "desc": "Cykl automatycznego odszraniania parownika"}
}


def get_param_label(code: str) -> str:
    """Zwraca etykietę parametru z kodem w nawiasie."""
    info = PARAM_INFO.get(code)
    return f"{info['label']} ({code})" if info else code


def inject_css():
    """Wstrzykuje style CSS do strony Streamlit."""
    st.markdown("""
    <style>
    /* Redukcja pustej przestrzeni na górze strony */
    .block-container {
        padding-top: 1rem !important;
    }
    header[data-testid="stHeader"] {
        height: 2rem !important;
    }

    /* Wygląd kafelków metryk */
    [data-testid="stMetric"] {
        background-color: #1E1E1E;
        border: 1px solid #333;
        border-radius: 10px;
        padding: 15px;
        box-shadow: 2px 2px 10px rgba(0,0,0,0.3);
    }

    /* Jasny kolor tekstu dla kafelków */
    [data-testid="stMetricValue"] {
        color: #FFFFFF !important;
    }

    [data-testid="stMetricLabel"] {
        color: #CCCCCC !important;
    }

    [data-testid="stMetricDelta"] {
        color: #AAAAAA !important;
    }

    @media (max-width: 768px) {
        [data-testid="stHorizontalBlock"]:has([data-testid="stMetric"]) {
            display: grid !important;
            grid-template-columns: repeat(2, 1fr) !important;
            gap: 10px !important;
        }
        [data-testid="stMetricValue"] {
            font-size: 1.5rem !important;
        }
    }
    </style>
    """, unsafe_allow_html=True)
