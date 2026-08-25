"""Warstwa ładowania i przetwarzania danych dla dashboardu."""
import sqlite3
import numpy as np
import pandas as pd
from typing import Optional
from app.config import DB_FILE, HEAT_PUMP_DEV_ID, MANUAL_METER_DEV_ID


def get_pump_status_for_refresh() -> bool:
    """Sprawdza czy pompa aktualnie pracuje (comp_freq > 0)."""
    try:
        conn = sqlite3.connect(DB_FILE)
        query = "SELECT val_num FROM telemetry WHERE device_id = ? AND code = 'comp_freq' ORDER BY timestamp DESC LIMIT 1"
        df = pd.read_sql_query(query, conn, params=(HEAT_PUMP_DEV_ID,))
        conn.close()
        if not df.empty and df['val_num'].iloc[0] and df['val_num'].iloc[0] > 0:
            return True
        return False
    except Exception:
        return False


def load_pump_data(hours: int, all_time: bool = False, is_today: bool = False) -> pd.DataFrame:
    """Ładuje dane wyłącznie ze sterownika pompy ciepła."""
    conn = sqlite3.connect(DB_FILE)
    if all_time:
        query = """
            SELECT 
                datetime(timestamp, 'unixepoch', 'localtime') as czas,
                code, val_num, val_str
            FROM telemetry
            WHERE device_id = ?
            ORDER BY timestamp ASC
        """
        df_data = pd.read_sql_query(query, conn, params=(HEAT_PUMP_DEV_ID,))
    elif is_today:
        query = """
            SELECT 
                datetime(timestamp, 'unixepoch', 'localtime') as czas,
                code, val_num, val_str
            FROM telemetry
            WHERE device_id = ?
              AND date(timestamp, 'unixepoch', 'localtime') = date('now', 'localtime')
            ORDER BY timestamp ASC
        """
        df_data = pd.read_sql_query(query, conn, params=(HEAT_PUMP_DEV_ID,))
    else:
        query = """
            SELECT 
                datetime(timestamp, 'unixepoch', 'localtime') as czas,
                code, val_num, val_str
            FROM telemetry
            WHERE device_id = ?
              AND timestamp >= strftime('%s', 'now', ? || ' hours')
            ORDER BY timestamp ASC
        """
        df_data = pd.read_sql_query(query, conn, params=(HEAT_PUMP_DEV_ID, f"-{hours}"))
    conn.close()
    return df_data


def load_manual_readings(time_offset_hours: int) -> pd.DataFrame:
    """Ładuje całą historię odczytów z licznika ręcznego."""
    conn = sqlite3.connect(DB_FILE)
    query = """
        SELECT 
            id,
            timestamp,
            datetime(timestamp, 'unixepoch', 'localtime') as czas,
            val_num as stan_kwh
        FROM telemetry
        WHERE device_id = ? AND code = 'energy_kwh'
        ORDER BY timestamp ASC
    """
    df_man = pd.read_sql_query(query, conn, params=(MANUAL_METER_DEV_ID,))
    conn.close()
    if not df_man.empty and 'czas' in df_man.columns:
        df_man["czas"] = pd.to_datetime(df_man["czas"])
        df_man = apply_time_correction(df_man, time_offset_hours)
    return df_man


def apply_time_correction(df: pd.DataFrame, offset_hours: int) -> pd.DataFrame:
    """Dodaje przesunięcie czasu do kolumny 'czas' w DataFrame."""
    if df is None or df.empty or 'czas' not in df.columns:
        return df
    df_corrected = df.copy()
    df_corrected['czas'] = pd.to_datetime(df_corrected['czas']) + pd.Timedelta(hours=offset_hours)
    return df_corrected


# --- Stałe do mapowania wartości boolean ---
BOOL_MAP = {
    "True": 1.0, "true": 1.0, "1": 1.0, "1.0": 1.0,
    "False": 0.0, "false": 0.0, "0": 0.0, "0.0": 0.0
}

NEEDED_COLS = [
    "out_water_temp", "in_water_temp", "flow_rate", "ac_vol", "ac_curr",
    "comp_freq", "disc_temp", "amb_temp", "valve", "heat_temp_set", "defrost"
]

RESAMPLE_AGG = {
    "out_water_temp": "mean",
    "in_water_temp": "mean",
    "flow_rate": "mean",
    "ac_vol": "mean",
    "ac_curr": "mean",
    "comp_freq": "mean",
    "disc_temp": "mean",
    "amb_temp": "mean",
    "heat_temp_set": "last",
    "valve": "mean",
    "defrost": "max"
}


def process_telemetry(
    df: pd.DataFrame,
    time_offset_hours: int,
    cos_phi: float,
    standby_power_w: float,
    active_power_w: float,
    resample_rule: Optional[str] = None
) -> Optional[pd.DataFrame]:
    """
    Przetwarza surowe dane telemetryczne na DataFrame z obliczonymi parametrami.
    Zwraca None jeśli df jest pusty.
    """
    if df.empty:
        return None

    df["val_combined"] = df["val_num"]
    mask_str = df["val_combined"].isna() & df["val_str"].notna()
    df.loc[mask_str, "val_combined"] = df.loc[mask_str, "val_str"].map(BOOL_MAP)

    df_pivot = df.pivot_table(index="czas", columns="code", values="val_combined", aggfunc="first").reset_index()
    df_pivot["czas"] = pd.to_datetime(df_pivot["czas"])
    df_pivot = apply_time_correction(df_pivot, time_offset_hours)
    df_pivot = df_pivot.sort_values("czas")

    for col in NEEDED_COLS:
        if col not in df_pivot.columns:
            df_pivot[col] = np.nan
        else:
            df_pivot[col] = df_pivot[col].ffill()

    df_pivot["valve"] = df_pivot["valve"].fillna(0).astype(float)

    if resample_rule:
        df_pivot = df_pivot.set_index("czas").resample(resample_rule).agg(RESAMPLE_AGG).reset_index()
        for col in NEEDED_COLS:
            df_pivot[col] = df_pivot[col].ffill()

    df_pivot["Tryb"] = np.where(df_pivot["valve"] >= 0.5, "CWU", "CO")

    # Obliczenia fizyczne
    curr_a = df_pivot["ac_curr"] / 10
    df_pivot["flow_m3h"] = df_pivot["flow_rate"] / 10.0
    df_pivot["delta_t"] = df_pivot["out_water_temp"] - df_pivot["in_water_temp"]

    raw_p_el_kw = (df_pivot["ac_vol"] * curr_a * cos_phi) / 1000.0
    is_active = raw_p_el_kw > 0.1
    correction_kw = (standby_power_w / 1000.0) + np.where(is_active, active_power_w / 1000.0, 0.0)

    df_pivot["P_el_kw"] = raw_p_el_kw + correction_kw
    df_pivot["P_th_kw"] = (df_pivot["flow_m3h"] * 4.186 * df_pivot["delta_t"]) / 3.6

    df_pivot["COP"] = np.where(is_active, df_pivot["P_th_kw"] / df_pivot["P_el_kw"], np.nan)
    invalid_mask = (df_pivot["P_th_kw"] <= 0) | (df_pivot["COP"] < 0.5) | (df_pivot["COP"] > 10.0)
    df_pivot.loc[invalid_mask, "COP"] = np.nan
    df_pivot.loc[df_pivot["P_th_kw"] < 0, "P_th_kw"] = 0.0

    # Obliczenie energii
    df_pivot["dt_hours"] = df_pivot["czas"].diff().dt.total_seconds().fillna(0) / 3600.0

    if resample_rule:
        df_pivot["E_th_kwh"] = df_pivot["P_th_kw"] * df_pivot["dt_hours"]
        df_pivot["E_el_kwh"] = df_pivot["P_el_kw"] * df_pivot["dt_hours"]
    else:
        df_pivot["E_th_kwh"] = df_pivot["P_th_kw"].shift(1).fillna(0) * df_pivot["dt_hours"]
        df_pivot["E_el_kwh"] = df_pivot["P_el_kw"].shift(1).fillna(0) * df_pivot["dt_hours"]

    # Wykrywanie cykli defrost i startów sprężarki
    df_pivot["defrost_num"] = df_pivot["defrost"].fillna(0).apply(lambda x: 1 if x else 0)
    df_pivot["defrost_start"] = ((df_pivot["defrost_num"] == 1) & (df_pivot["defrost_num"].shift(1, fill_value=0) == 0)).astype(int)
    df_pivot["comp_on"] = (df_pivot["comp_freq"] > 5).astype(int)
    df_pivot["comp_start"] = ((df_pivot["comp_on"] == 1) & (df_pivot["comp_on"].shift(1, fill_value=0) == 0)).astype(int)
    df_pivot["work_period"] = df_pivot["comp_start"].cumsum()
    df_pivot["dt_hours_work"] = np.where(df_pivot["comp_on"] == 1, df_pivot["dt_hours"], 0.0)

    # Podział energii wg trybu
    df_pivot["E_el_co_row"] = np.where(df_pivot["Tryb"] == "CO", df_pivot["E_el_kwh"], 0.0)
    df_pivot["E_el_cwu_row"] = np.where(df_pivot["Tryb"] == "CWU", df_pivot["E_el_kwh"], 0.0)
    df_pivot["E_th_co_row"] = np.where(df_pivot["Tryb"] == "CO", df_pivot["E_th_kwh"], 0.0)
    df_pivot["E_th_cwu_row"] = np.where(df_pivot["Tryb"] == "CWU", df_pivot["E_th_kwh"], 0.0)

    return df_pivot


def compute_daily_stats(df_pivot: pd.DataFrame, time_offset_hours: int) -> pd.DataFrame:
    """Oblicza statystyki dzienne z przetworzonego DataFrame."""
    if df_pivot is None or df_pivot.empty:
        return pd.DataFrame(columns=[
            "dzień", "E_el_co_row", "E_el_cwu_row", "E_th_co_row", "E_th_cwu_row",
            "amb_temp", "defrost_start", "comp_start", "dt_hours_work"
        ])

    df_pivot["dzień"] = df_pivot["czas"].dt.date

    daily_df = df_pivot.groupby("dzień").agg({
        "E_el_co_row": "sum",
        "E_el_cwu_row": "sum",
        "E_th_co_row": "sum",
        "E_th_cwu_row": "sum",
        "amb_temp": "mean",
        "defrost_start": "sum",
        "comp_start": "sum",
        "dt_hours_work": "sum"
    }).reset_index()

    if not daily_df.empty and 'dzień' in daily_df.columns:
        daily_df['dzień'] = pd.to_datetime(daily_df['dzień']).dt.date + pd.Timedelta(days=1 if time_offset_hours >= 12 else 0)

    daily_df["E_el_total"] = daily_df["E_el_co_row"] + daily_df["E_el_cwu_row"]
    daily_df["E_th_total"] = daily_df["E_th_co_row"] + daily_df["E_th_cwu_row"]
    daily_df["SCOP_dzienny"] = np.where(daily_df["E_el_total"] > 0, daily_df["E_th_total"] / daily_df["E_el_total"], np.nan)

    return daily_df


def compute_scop_metrics(df_pivot: pd.DataFrame) -> dict:
    """Oblicza metryki SCOP z przetworzonego DataFrame."""
    if df_pivot is None or df_pivot.empty:
        return {
            "e_el_co": 0.0, "e_el_cwu": 0.0, "e_th_co": 0.0, "e_th_cwu": 0.0,
            "e_th_total": 0.0, "e_el_total": 0.0,
            "scop_total": 0.0, "scop_co": 0.0, "scop_cwu": 0.0,
        }

    co_mask = (df_pivot["Tryb"] == "CO") & (~df_pivot["COP"].isna())
    cwu_mask = (df_pivot["Tryb"] == "CWU") & (~df_pivot["COP"].isna())

    e_th_co = df_pivot.loc[co_mask, "E_th_kwh"].sum()
    e_el_co = df_pivot.loc[co_mask, "E_el_kwh"].sum()
    scop_co = (e_th_co / e_el_co) if e_el_co > 0 else 0.0

    e_th_cwu = df_pivot.loc[cwu_mask, "E_th_kwh"].sum()
    e_el_cwu = df_pivot.loc[cwu_mask, "E_el_kwh"].sum()
    scop_cwu = (e_th_cwu / e_el_cwu) if e_el_cwu > 0 else 0.0

    e_th_total = e_th_co + e_th_cwu
    e_el_total = e_el_co + e_el_cwu
    scop_total = (e_th_total / e_el_total) if e_el_total > 0 else 0.0

    return {
        "e_el_co": e_el_co, "e_el_cwu": e_el_cwu,
        "e_th_co": e_th_co, "e_th_cwu": e_th_cwu,
        "e_th_total": e_th_total, "e_el_total": e_el_total,
        "scop_total": scop_total, "scop_co": scop_co, "scop_cwu": scop_cwu,
    }


def compute_operational_stats(daily_df: pd.DataFrame, df_pivot: pd.DataFrame) -> dict:
    """Oblicza statystyki operacyjne (średnie dzienne, defrosty, starty)."""
    if daily_df.empty or df_pivot is None or df_pivot.empty:
        return {
            "avg_daily_el_co": 0.0, "avg_daily_el_cwu": 0.0,
            "avg_amb_temp": np.nan, "total_defrosts": 0,
            "total_comp_starts": 0, "total_work_hours": 0.0,
            "avg_work_time_per_start": 0.0,
        }

    num_days = max(len(daily_df), 1)
    avg_daily_el_co = daily_df["E_el_co_row"].sum() / num_days
    avg_daily_el_cwu = daily_df["E_el_cwu_row"].sum() / num_days
    avg_amb_temp = df_pivot["amb_temp"].mean()
    total_defrosts = int(daily_df["defrost_start"].sum())
    total_comp_starts = int(daily_df["comp_start"].sum())
    total_work_hours = daily_df["dt_hours_work"].sum()
    avg_work_time_per_start = (total_work_hours / total_comp_starts * 60) if total_comp_starts > 0 else 0.0

    return {
        "avg_daily_el_co": avg_daily_el_co,
        "avg_daily_el_cwu": avg_daily_el_cwu,
        "avg_amb_temp": avg_amb_temp,
        "total_defrosts": total_defrosts,
        "total_comp_starts": total_comp_starts,
        "total_work_hours": total_work_hours,
        "avg_work_time_per_start": avg_work_time_per_start,
    }
