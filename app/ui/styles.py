"""Style CSS i stałe wizualne dashboardu. """
import streamlit as st

# PARAM_INFO i get_param_label przeniesione do app.config (jedno źródło prawdy)
from app.config import PARAM_INFO, get_param_label  # noqa: F401 — re-export dla kompatybilności


def inject_css():
    """Wstrzykuje style CSS do strony Streamlit."""
    st.markdown("""
    <style>
    /* Redukcja pustej przestrzeni na górze strony */
    .block-container {
        padding-top: 2.5rem !important;
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
