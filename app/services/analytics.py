"""Zaawansowana analityka pompy ciepła - diagnostyka, wykrywanie anomalii, korelacje pogodowe."""
import numpy as np
import pandas as pd
from typing import Dict, List, Tuple, Optional
from datetime import datetime, timedelta
from dataclasses import dataclass, field


@dataclass
class ShortCycleEvent:
    """Reprezentuje pojedynczy cykl krótki."""
    start_time: datetime
    end_time: datetime
    duration_sec: int
    off_duration_sec: int  # Czas wyłączenia przed kolejnym startem
    cop_avg: float
    energy_wasted_kwh: float


@dataclass
class InverterAnalysis:
    """Wyniki analizy pracy inwertera."""
    avg_frequency: float
    max_frequency: float
    min_frequency: float
    std_frequency: float
    stability_score: float  # 0-100, gdzie 100 = idealna stabilność
    modulation_efficiency: float  # % czasu w optymalnym zakresie
    frequent_starts: int  # Liczba startów ze stanu 0
    optimal_range_pct: float  # % czasu w zakresie 30-60 Hz


@dataclass
class ModeAnalysis:
    """Analiza czasów pracy trybów."""
    co_runtime_hours: float
    cwu_runtime_hours: float
    co_energy_kwh: float
    cwu_energy_kwh: float
    co_avg_cop: float
    cwu_avg_cop: float
    co_start_count: int
    cwu_start_count: int
    mode_transitions: int  # Liczba przełączeń CO <-> CWU


@dataclass
class WeatherCorrelation:
    """Korelacja między warunkami pogodowymi a wydajnością."""
    temp_outside_avg: float
    cop_vs_temp_correlation: float  # Współczynnik korelacji Pearsona
    cop_at_temp_ranges: Dict[str, float]  # Średnie COP w zakresach temperatur
    efficiency_drop_per_degree: float  # Spadek COP na każdy °C spadku temperatury
    optimal_temp_range: Tuple[float, float]  # Zakres temperatur dla najlepszego COP
    heating_degree_days: float  # HDD dla analizowanego okresu


@dataclass
class DiagnosticReport:
    """Kompleksowy raport diagnostyczny."""
    timestamp: datetime
    short_cycles: List[ShortCycleEvent] = field(default_factory=list)
    inverter_analysis: Optional[InverterAnalysis] = None
    mode_analysis: Optional[ModeAnalysis] = None
    weather_correlation: Optional[WeatherCorrelation] = None
    estimated_annual_cost: float = 0.0
    recommendations: List[str] = field(default_factory=list)
    
    def to_dict(self) -> dict:
        """Konwertuje raport do słownika JSON-compatible."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "short_cycles_count": len(self.short_cycles),
            "short_cycles": [
                {
                    "start": e.start_time.isoformat(),
                    "end": e.end_time.isoformat(),
                    "duration_sec": e.duration_sec,
                    "off_duration_sec": e.off_duration_sec,
                    "cop_avg": round(e.cop_avg, 2),
                    "energy_wasted_kwh": round(e.energy_wasted_kwh, 3)
                }
                for e in self.short_cycles
            ],
            "inverter_analysis": {
                "avg_frequency": round(self.inverter_analysis.avg_frequency, 1) if self.inverter_analysis else None,
                "max_frequency": round(self.inverter_analysis.max_frequency, 1) if self.inverter_analysis else None,
                "min_frequency": round(self.inverter_analysis.min_frequency, 1) if self.inverter_analysis else None,
                "stability_score": round(self.inverter_analysis.stability_score, 1) if self.inverter_analysis else None,
                "modulation_efficiency": round(self.inverter_analysis.modulation_efficiency, 1) if self.inverter_analysis else None,
                "optimal_range_pct": round(self.inverter_analysis.optimal_range_pct, 1) if self.inverter_analysis else None
            } if self.inverter_analysis else None,
            "mode_analysis": {
                "co_runtime_hours": round(self.mode_analysis.co_runtime_hours, 2) if self.mode_analysis else None,
                "cwu_runtime_hours": round(self.mode_analysis.cwu_runtime_hours, 2) if self.mode_analysis else None,
                "co_energy_kwh": round(self.mode_analysis.co_energy_kwh, 2) if self.mode_analysis else None,
                "cwu_energy_kwh": round(self.mode_analysis.cwu_energy_kwh, 2) if self.mode_analysis else None,
                "co_avg_cop": round(self.mode_analysis.co_avg_cop, 2) if self.mode_analysis else None,
                "cwu_avg_cop": round(self.mode_analysis.cwu_avg_cop, 2) if self.mode_analysis else None,
                "mode_transitions": self.mode_analysis.mode_transitions if self.mode_analysis else None
            } if self.mode_analysis else None,
            "weather_correlation": {
                "temp_outside_avg": round(self.weather_correlation.temp_outside_avg, 1) if self.weather_correlation else None,
                "cop_vs_temp_correlation": round(self.weather_correlation.cop_vs_temp_correlation, 3) if self.weather_correlation else None,
                "efficiency_drop_per_degree": round(self.weather_correlation.efficiency_drop_per_degree, 3) if self.weather_correlation else None,
                "optimal_temp_range": self.weather_correlation.optimal_temp_range if self.weather_correlation else None,
                "heating_degree_days": round(self.weather_correlation.heating_degree_days, 1) if self.weather_correlation else None,
                "cop_at_temp_ranges": {
                    k: round(v, 2) for k, v in self.weather_correlation.cop_at_temp_ranges.items()
                } if self.weather_correlation else None
            } if self.weather_correlation else None,
            "recommendations": self.recommendations,
            "estimated_annual_cost": round(self.estimated_annual_cost, 2)
        }


def detect_short_cycles(
    df: pd.DataFrame,
    min_off_time_sec: int = 180,  # Minimalny czas wyłączenia by uznać za nowy cykl
    max_on_time_sec: int = 300,   # Maksymalny czas pracy by uznać za krótki cykl
    min_power_kw: float = 0.5     # Minimalna moc by uznać pompę za pracującą
) -> List[ShortCycleEvent]:
    """
    Wykrywa cykle krótkie (short cycling) - szkodliwe częste starty/stop pompy.
    
    Args:
        df: DataFrame z kolumnami: czas, P_el_kw, comp_freq
        min_off_time_sec: Minimalny czas wyłączenia między cyklami
        max_on_time_sec: Maksymalny czas pracy by uznać za krótki cykl
        min_power_kw: Próg mocy uznawanej za pracę pompy
    
    Returns:
        Lista zdarzeń短 cycle
    """
    if df.empty or 'P_el_kw' not in df.columns:
        return []
    
    df = df.copy().sort_values('czas')
    df['is_running'] = df['P_el_kw'] >= min_power_kw
    
    # Znajdź zmiany stanu
    df['state_changed'] = df['is_running'].astype(int).diff().fillna(0)
    
    cycles = []
    current_off_start = None
    current_on_start = None
    
    for idx, row in df.iterrows():
        if row['state_changed'] == 1:  # Start pompy
            if current_off_start is not None and current_on_start is not None:
                off_duration = (current_off_start - current_on_start).total_seconds()
                
                # Sprawdź czy poprzedni cykl był krótki
                if off_duration > min_off_time_sec:
                    pass  # To był normalny czas wyłączenia
            
            current_on_start = row['czas']
            
        elif row['state_changed'] == -1:  # Stop pompy
            if current_on_start is not None:
                on_duration = (row['czas'] - current_on_start).total_seconds()
                
                # Sprawdź czy to był krótki cykl
                if on_duration < max_on_time_sec and on_duration > 30:  # Ignoruj bardzo krótkie błędy
                    # Oblicz średni COP i energię dla tego cyklu
                    cycle_data = df[
                        (df['czas'] >= current_on_start) & 
                        (df['czas'] <= row['czas'])
                    ]
                    
                    cop_avg = cycle_data['COP'].mean() if 'COP' in cycle_data.columns else 0.0
                    energy_wasted = (cycle_data['P_el_kw'] * cycle_data['czas'].diff().dt.total_seconds() / 3600).sum()
                    
                    off_duration = 0
                    if current_off_start is not None:
                        off_duration = (current_on_start - current_off_start).total_seconds()
                    
                    cycles.append(ShortCycleEvent(
                        start_time=current_on_start,
                        end_time=row['czas'],
                        duration_sec=int(on_duration),
                        off_duration_sec=int(off_duration),
                        cop_avg=cop_avg if not np.isnan(cop_avg) else 0.0,
                        energy_wasted_kwh=energy_wasted if not np.isnan(energy_wasted) else 0.0
                    ))
            
            current_off_start = row['czas']
    
    return cycles


def analyze_inverter_performance(df: pd.DataFrame) -> InverterAnalysis:
    """
    Analizuje pracę inwertera (sprężarki) pod kątem stabilności i efektywności.
    
    Args:
        df: DataFrame z kolumnami: czas, comp_freq, P_el_kw
    
    Returns:
        InverterAnalysis z metrykami wydajności
    """
    if df.empty or 'comp_freq' not in df.columns:
        return InverterAnalysis(
            avg_frequency=0.0, max_frequency=0.0, min_frequency=0.0,
            std_frequency=0.0, stability_score=0.0, modulation_efficiency=0.0,
            frequent_starts=0, optimal_range_pct=0.0
        )
    
    df = df.copy()
    freq = df['comp_freq'].dropna()
    
    if len(freq) == 0:
        return InverterAnalysis(
            avg_frequency=0.0, max_frequency=0.0, min_frequency=0.0,
            std_frequency=0.0, stability_score=0.0, modulation_efficiency=0.0,
            frequent_starts=0, optimal_range_pct=0.0
        )
    
    # Filtruj dane - uwzględnij tylko gdy sprężarka pracuje (powyżej 3 Hz)
    freq_running = freq[freq > 3]
    
    if len(freq_running) == 0:
        return InverterAnalysis(
            avg_frequency=0.0, max_frequency=0.0, min_frequency=0.0,
            std_frequency=0.0, stability_score=0.0, modulation_efficiency=0.0,
            frequent_starts=0, optimal_range_pct=0.0
        )
    
    # Podstawowe statystyki tylko dla czasu pracy sprężarki
    avg_freq = freq_running.mean()
    max_freq = freq_running.max()
    min_freq = freq_running.min()
    std_freq = freq_running.std() if len(freq_running) > 1 else 0.0
    
    # Stabilność: niższe odchylenie = wyższy score (0-100)
    # Przyjmujemy że std < 5 Hz to excellent, std > 30 Hz to poor
    stability_score = max(0, min(100, 100 - (std_freq * 2.5)))
    
    # Efektywność modulacji: % czasu w optymalnym zakresie 30-60 Hz
    # Obliczamy tylko dla czasu gdy sprężarka pracuje (powyżej 3 Hz)
    optimal_mask = (freq_running >= 30) & (freq_running <= 60)
    optimal_range_pct = (optimal_mask.sum() / len(freq_running)) * 100 if len(freq_running) > 0 else 0.0
    
    # Liczba startów ze stanu 0 lub bliskiego 0
    df_sorted = df.sort_values('czas')
    df_sorted['freq_was_zero'] = df_sorted['comp_freq'].shift(1).fillna(0) <= 5
    df_sorted['freq_now_active'] = df_sorted['comp_freq'] > 5
    frequent_starts = (df_sorted['freq_was_zero'] & df_sorted['freq_now_active']).sum()
    
    # Modulation efficiency: jak często inwerter pracuje w zakresie vs on/off
    running_mask = freq > 0
    modulation_efficiency = (optimal_mask.sum() / running_mask.sum() * 100) if running_mask.sum() > 0 else 0.0
    
    return InverterAnalysis(
        avg_frequency=avg_freq,
        max_frequency=max_freq,
        min_frequency=min_freq,
        std_frequency=std_freq,
        stability_score=stability_score,
        modulation_efficiency=modulation_efficiency,
        frequent_starts=int(frequent_starts),
        optimal_range_pct=optimal_range_pct
    )


def analyze_mode_runtime(df: pd.DataFrame) -> ModeAnalysis:
    """
    Analizuje czasy pracy w trybach CO (centralne ogrzewanie) i CWU (ciepła woda użytkowa).
    
    Args:
        df: DataFrame z kolumnami: czas, Tryb, P_el_kw, E_el_kwh, COP
    
    Returns:
        ModeAnalysis z podsumowaniem czasów i energii
    """
    if df.empty or 'Tryb' not in df.columns:
        return ModeAnalysis(
            co_runtime_hours=0.0, cwu_runtime_hours=0.0,
            co_energy_kwh=0.0, cwu_energy_kwh=0.0,
            co_avg_cop=0.0, cwu_avg_cop=0.0,
            co_start_count=0, cwu_start_count=0, mode_transitions=0
        )
    
    df = df.copy().sort_values('czas')
    
    # Oblicz czasy trwania każdego wpisu
    df['dt_hours'] = df['czas'].diff().dt.total_seconds().fillna(0) / 3600
    
    # Filtruj tylko gdy pompa pracuje
    working_df = df[df['P_el_kw'] > 0.1].copy() if 'P_el_kw' in df.columns else df.copy()
    
    # Czasy pracy
    co_mask = working_df['Tryb'] == 'CO'
    cwu_mask = working_df['Tryb'] == 'CWU'
    
    co_runtime = working_df.loc[co_mask, 'dt_hours'].sum()
    cwu_runtime = working_df.loc[cwu_mask, 'dt_hours'].sum()
    
    # Energia
    co_energy = working_df.loc[co_mask, 'E_el_kwh'].sum() if 'E_el_kwh' in working_df.columns else 0.0
    cwu_energy = working_df.loc[cwu_mask, 'E_el_kwh'].sum() if 'E_el_kwh' in working_df.columns else 0.0
    
    # Średnie COP
    co_cop = working_df.loc[co_mask, 'COP'].mean() if 'COP' in working_df.columns and co_mask.any() else 0.0
    cwu_cop = working_df.loc[cwu_mask, 'COP'].mean() if 'COP' in working_df.columns and cwu_mask.any() else 0.0
    
    co_cop = co_cop if not np.isnan(co_cop) else 0.0
    cwu_cop = cwu_cop if not np.isnan(cwu_cop) else 0.0
    
    # Liczba startów (zmiana z 0/nic na CO/CWU)
    working_df['prev_mode'] = working_df['Tryb'].shift(1)
    co_starts = ((working_df['prev_mode'] != 'CO') & (working_df['Tryb'] == 'CO')).sum()
    cwu_starts = ((working_df['prev_mode'] != 'CWU') & (working_df['Tryb'] == 'CWU')).sum()
    
    # Przełączenia między trybami
    df_all = df[df['Tryb'].notna()].copy()
    df_all['prev_mode'] = df_all['Tryb'].shift(1)
    transitions = (
        ((df_all['prev_mode'] == 'CO') & (df_all['Tryb'] == 'CWU')).sum() +
        ((df_all['prev_mode'] == 'CWU') & (df_all['Tryb'] == 'CO')).sum()
    )
    
    return ModeAnalysis(
        co_runtime_hours=co_runtime,
        cwu_runtime_hours=cwu_runtime,
        co_energy_kwh=co_energy,
        cwu_energy_kwh=cwu_energy,
        co_avg_cop=co_cop,
        cwu_avg_cop=cwu_cop,
        co_start_count=int(co_starts),
        cwu_start_count=int(cwu_starts),
        mode_transitions=int(transitions)
    )


def correlate_weather_performance(
    df: pd.DataFrame,
    weather_df: pd.DataFrame,
    base_temp: float = 20.0  # Temperatura bazowa dla HDD
) -> WeatherCorrelation:
    """
    Analizuje korelację między warunkami pogodowymi a wydajnością pompy.
    
    Args:
        df: DataFrame z danymi pompy (czas, COP, P_th_kw, amb_temp)
        weather_df: DataFrame z danymi pogodowymi (timestamp, temperature)
        base_temp: Temperatura bazowa dla Heating Degree Days
    
    Returns:
        WeatherCorrelation z analizą zależności
    """
    if df.empty or 'COP' not in df.columns:
        return WeatherCorrelation(
            temp_outside_avg=0.0,
            cop_vs_temp_correlation=0.0,
            cop_at_temp_ranges={},
            efficiency_drop_per_degree=0.0,
            optimal_temp_range=(0.0, 0.0),
            heating_degree_days=0.0
        )
    
    df = df.copy().sort_values('czas')
    
    # Użyj temperatury zewnętrznej z pompy jeśli dostępna, inaczej z weather
    if 'amb_temp' in df.columns and df['amb_temp'].notna().any():
        temp_col = 'amb_temp'
        temp_series = df['amb_temp'].dropna()
    elif not weather_df.empty and 'temperature' in weather_df.columns:
        # Interpoluj dane pogodowe do timestamps z df
        weather_df = weather_df.copy()
        weather_df['timestamp'] = pd.to_datetime(weather_df['timestamp'], unit='s')
        weather_df = weather_df.set_index('timestamp')['temperature']
        temp_series = df['czas'].map(weather_df).dropna()
        temp_col = 'temp_interpolated'
        df[temp_col] = temp_series
    else:
        return WeatherCorrelation(
            temp_outside_avg=0.0,
            cop_vs_temp_correlation=0.0,
            cop_at_temp_ranges={},
            efficiency_drop_per_degree=0.0,
            optimal_temp_range=(0.0, 0.0),
            heating_degree_days=0.0
        )
    
    # Średnia temperatura
    temp_avg = temp_series.mean()
    
    # Korelacja COP vs temperatura (tylko gdy COP jest valid)
    valid_mask = df['COP'].notna() & (df['COP'] > 0.5) & (df['COP'] < 10)
    if valid_mask.sum() > 10 and temp_col in df.columns:
        cop_valid = df.loc[valid_mask, 'COP']
        temp_valid = df.loc[valid_mask, temp_col] if temp_col in df.columns else df['czas'].map(
            weather_df.set_index('timestamp')['temperature'] if not weather_df.empty else pd.Series()
        ).dropna()
        
        if len(cop_valid) == len(temp_valid) and len(cop_valid) > 10:
            correlation = np.corrcoef(cop_valid, temp_valid)[0, 1] if len(cop_valid) > 1 else 0.0
        else:
            correlation = 0.0
    else:
        correlation = 0.0
    
    # COP w zakresach temperatur
    temp_ranges = {
        "<0°C": df[(df[temp_col] < 0) & (df['COP'] > 0.5) & (df['COP'] < 10)]['COP'].mean() if temp_col in df.columns else 0.0,
        "0-5°C": df[(df[temp_col] >= 0) & (df[temp_col] < 5) & (df['COP'] > 0.5) & (df['COP'] < 10)]['COP'].mean() if temp_col in df.columns else 0.0,
        "5-10°C": df[(df[temp_col] >= 5) & (df[temp_col] < 10) & (df['COP'] > 0.5) & (df['COP'] < 10)]['COP'].mean() if temp_col in df.columns else 0.0,
        "10-15°C": df[(df[temp_col] >= 10) & (df[temp_col] < 15) & (df['COP'] > 0.5) & (df['COP'] < 10)]['COP'].mean() if temp_col in df.columns else 0.0,
        ">15°C": df[(df[temp_col] >= 15) & (df['COP'] > 0.5) & (df['COP'] < 10)]['COP'].mean() if temp_col in df.columns else 0.0
    }
    temp_ranges = {k: (v if not np.isnan(v) else 0.0) for k, v in temp_ranges.items()}
    
    # Spadek efektywności na stopień (regresja liniowa)
    if valid_mask.sum() > 10 and temp_col in df.columns:
        cop_valid = df.loc[valid_mask, 'COP'].values
        temp_valid = df.loc[valid_mask, temp_col].values
        
        if len(cop_valid) > 10:
            coeffs = np.polyfit(temp_valid, cop_valid, 1)
            efficiency_drop = coeffs[0]  # Nachylenie prostej
        else:
            efficiency_drop = 0.0
    else:
        efficiency_drop = 0.0
    
    # Optymalny zakres temperatur (gdzie COP jest najwyższy)
    best_temp_range = (0.0, 0.0)
    if temp_col in df.columns:
        df_temp = df[[temp_col, 'COP']].dropna()
        df_temp = df_temp[(df_temp['COP'] > 0.5) & (df_temp['COP'] < 10)]
        
        if len(df_temp) > 10:
            df_temp['temp_bin'] = pd.cut(df_temp[temp_col], bins=10)
            avg_cop_by_bin = df_temp.groupby('temp_bin', observed=False)['COP'].mean()
            best_bin = avg_cop_by_bin.idxmax()
            
            if best_bin:
                best_temp_range = (best_bin.left, best_bin.right)
    
    # Heating Degree Days
    if temp_col in df.columns:
        daily_temp = df.set_index('czas')[temp_col].resample('D').mean()
        hdd = max(0, (base_temp - daily_temp).sum())
    else:
        hdd = 0.0
    
    return WeatherCorrelation(
        temp_outside_avg=temp_avg,
        cop_vs_temp_correlation=correlation if not np.isnan(correlation) else 0.0,
        cop_at_temp_ranges=temp_ranges,
        efficiency_drop_per_degree=efficiency_drop,
        optimal_temp_range=best_temp_range,
        heating_degree_days=hdd
    )


def generate_recommendations(
    short_cycles: List[ShortCycleEvent],
    inverter: InverterAnalysis,
    modes: ModeAnalysis,
    weather: WeatherCorrelation
) -> List[str]:
    """Generuje rekomendacje na podstawie wyników analiz."""
    recommendations = []
    
    # Short cycling
    if len(short_cycles) > 5:
        total_wasted = sum(sc.energy_wasted_kwh for sc in short_cycles)
        recommendations.append(
            f"Wykryto {len(short_cycles)} cykli krótkich. Szacowana strata energii: {total_wasted:.2f} kWh. "
            "Rozważ zwiększenie histerezy termostatu lub dodanie bufora ciepła."
        )
    
    # Inverter stability
    if inverter.stability_score < 50:
        recommendations.append(
            f"Niska stabilność pracy inwertera (score: {inverter.stability_score:.0f}/100). "
            "Sprawdź ustawienia sterowania lub czy nie ma zakłóceń w zasilaniu."
        )
    
    if inverter.optimal_range_pct < 40:
        recommendations.append(
            f"Inwerter rzadko pracuje w optymalnym zakresie 30-60 Hz ({inverter.optimal_range_pct:.0f}% czasu). "
            "Rozważ optymalizację nastaw lub dobór pompy do obciążenia."
        )
    
    # Mode transitions
    if modes.mode_transitions > 20:
        recommendations.append(
            f"Wysoka liczba przełączeń między CO a CWU ({modes.mode_transitions}). "
            "Rozważ zmianę harmonogramu grzania CWU na godziny nocne lub mniejszego zapotrzebowania na CO."
        )
    
    # Weather correlation
    if abs(weather.cop_vs_temp_correlation) > 0.7:
        temp_effect = "dodatnia" if weather.cop_vs_temp_correlation > 0 else "ujemna"
        recommendations.append(
            f"Silna korelacja {temp_effect} między temperaturą zewnętrzną a COP "
            f"(r={weather.cop_vs_temp_correlation:.2f}). Wydajność mocno zależy od pogody."
        )
    
    if weather.efficiency_drop_per_degree < -0.05:
        recommendations.append(
            f"Wydajność spada o {abs(weather.efficiency_drop_per_degree):.2f} COP na każdy °C niższej temperatury. "
            "To typowe zachowanie, ale warto sprawdzić izolację budynku."
        )
    
    # Overall efficiency
    if modes.co_avg_cop < 2.5 and modes.co_runtime_hours > 10:
        recommendations.append(
            f"Niski średni COP w trybie CO ({modes.co_avg_cop:.2f}). "
            "Sprawdź nastawy temperaturowe, przepływy lub stan czynnika chłodniczego."
        )
    
    if not recommendations:
        recommendations.append("Brak istotnych anomalii. Pompa pracuje prawidłowo.")
    
    return recommendations


def estimate_annual_cost(
    daily_energy_kwh: float,
    electricity_price_pln: float = 0.85  # zł/kWh - domyślna wartość, można zmienić w UI
) -> float:
    """Szacuje roczny koszt energii na podstawie dziennego zużycia."""
    return daily_energy_kwh * 365 * electricity_price_pln


def generate_diagnostic_report(
    df: pd.DataFrame,
    weather_df: pd.DataFrame = None,
    electricity_price: float = 0.85  # zł/kWh - domyślna wartość, można zmienić w UI
) -> DiagnosticReport:
    """
    Generuje kompletny raport diagnostyczny z wszystkich analiz.
    
    Args:
        df: DataFrame z danymi pompy (wymagane: czas, P_el_kw, comp_freq, Tryb, COP, E_el_kwh)
        weather_df: DataFrame z danymi pogodowymi
        electricity_price: Cena energii w PLN/kWh
    
    Returns:
        DiagnosticReport z pełną analizą
    """
    now = datetime.now()
    
    # Wykonaj wszystkie analizy
    short_cycles = detect_short_cycles(df)
    inverter = analyze_inverter_performance(df)
    modes = analyze_mode_runtime(df)
    weather = correlate_weather_performance(df, weather_df) if weather_df is not None and not weather_df.empty else None
    
    # Rekomendacje
    recommendations = generate_recommendations(
        short_cycles, inverter, modes, 
        weather if weather else WeatherCorrelation(0.0, 0.0, {}, 0.0, (0.0, 0.0), 0.0)
    )
    
    # Szacowany koszt roczny
    daily_energy = modes.co_energy_kwh + modes.cwu_energy_kwh
    days_span = 1
    if 'czas' in df.columns and len(df) > 1:
        time_span = (df['czas'].max() - df['czas'].min()).days
        days_span = max(time_span, 1)
    
    daily_avg = daily_energy / days_span
    annual_cost = estimate_annual_cost(daily_avg, electricity_price)
    
    return DiagnosticReport(
        timestamp=now,
        short_cycles=short_cycles,
        inverter_analysis=inverter,
        mode_analysis=modes,
        weather_correlation=weather,
        estimated_annual_cost=annual_cost,
        recommendations=recommendations
    )
