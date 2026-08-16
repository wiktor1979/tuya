from datetime import datetime
from db import save_manual_reading

# --- FORMULARZ RĘCZNEGO ODCZYTU LICZNIKA ENERGII ---
st.sidebar.markdown("---")
st.sidebar.header("📝 Ręczny odczyt licznika")

with st.sidebar.form("manual_energy_form", clear_on_submit=False):
    now = datetime.now()
    
    # Domyślny identyfikator ustawiony na "licznikreczny123"
    dev_id_input = st.text_input("ID Urządzenia", value="licznikreczny123")
    energy_val = st.number_input("Stan licznika [kWh]", min_value=0.0, step=0.1, format="%.2f")
    
    col_date, col_time = st.columns(2)
    with col_date:
        input_date = st.date_input("Data", value=now.date())
    with col_time:
        input_time = st.time_input("Godzina", value=now.time())

    submit_btn = st.form_submit_button("💾 Zapisz do bazy")

    if submit_btn:
        selected_dt = datetime.combine(input_date, input_time)
        selected_ts = int(selected_dt.timestamp())
        
        success = save_manual_reading(
            device_id=dev_id_input,
            code="total_energy_kwh",
            val_num=energy_val,
            timestamp=selected_ts
        )
        
        if success:
            st.success(f"Zapisano odczyt dla urządzenia '{dev_id_input}': {energy_val} kWh ({selected_dt.strftime('%Y-%m-%d %H:%M:%S')})")
            st.rerun()
        else:
            st.error("Błąd zapisu danych do bazy.")
