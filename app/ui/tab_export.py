"""Zakładka: Eksport Danych do CSV."""
import pandas as pd
import streamlit as st
from datetime import datetime


def render(df: pd.DataFrame, df_pivot: pd.DataFrame, daily_df: pd.DataFrame, hours_back: int):
    """Renderuje zakładkę Eksport Danych."""
    st.header("📁 Eksport Danych do CSV")
    st.markdown("""
    **Funkcjonalności eksportu:**
    - 📊 **Dane surowe**: Wszystkie pomiary z pompy ciepła
    - 📈 **Dane przetworzone**: Obliczone parametry (COP, moc, energia)
    - 📅 **Podsumowanie dzienne**: Statystyki dobowe
    
    Wybierz zakres czasu i format danych, a następnie kliknij przycisk pobierania.
    """)

    if df.empty:
        st.warning("Brak danych do eksportu w wybranym zakresie czasowym.")
        return

    exp_col1, exp_col2 = st.columns(2)
    with exp_col1:
        export_format = st.selectbox(
            "Format danych:",
            ["Dane surowe telemetryczne", "Dane przetworzone (z obliczeniami)", "Podsumowanie dzienne"],
            index=1
        )

    if export_format == "Dane surowe telemetryczne":
        export_df = df.copy()
        filename = f"pompa_dane_surowe_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
        st.subheader("📊 Podgląd danych surowych")
        st.dataframe(export_df.head(10), use_container_width=True)

    elif export_format == "Dane przetworzone (z obliczeniami)":
        export_df = df_pivot.copy() if df_pivot is not None else pd.DataFrame()
        filename = f"pompa_dane_przetworzone_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
        st.subheader("📈 Podgląd danych przetworzonych")
        st.dataframe(export_df.head(10), use_container_width=True)

    elif export_format == "Podsumowanie dzienne":
        export_df = daily_df.copy()
        filename = f"pompa_podsumowanie_dzienne_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
        st.subheader("📅 Podgląd podsumowania dziennego")
        st.dataframe(export_df.head(10), use_container_width=True)
    else:
        export_df = pd.DataFrame()
        filename = "export.csv"

    if not export_df.empty:
        csv_data = export_df.to_csv(index=False, decimal=';', sep=';').encode('utf-8')

        st.download_button(
            label="⬇️ Pobierz plik CSV",
            data=csv_data,
            file_name=filename,
            mime="text/csv",
            use_container_width=True
        )

        st.info(f"📝 Plik będzie zawierał {len(export_df)} wierszy danych z zakresu: {hours_back} godzin")
