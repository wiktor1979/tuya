"""Inicjalizacja pakietu services."""
from app.services.analytics import (
    generate_diagnostic_report,
    detect_short_cycles,
    analyze_inverter_performance,
    analyze_mode_runtime,
    correlate_weather_performance,
    DiagnosticReport,
    ShortCycleEvent,
    InverterAnalysis,
    ModeAnalysis,
    WeatherCorrelation
)

__all__ = [
    'generate_diagnostic_report',
    'detect_short_cycles',
    'analyze_inverter_performance',
    'analyze_mode_runtime',
    'correlate_weather_performance',
    'DiagnosticReport',
    'ShortCycleEvent',
    'InverterAnalysis',
    'ModeAnalysis',
    'WeatherCorrelation'
]
