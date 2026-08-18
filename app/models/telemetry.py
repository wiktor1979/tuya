"""Modele danych dla aplikacji."""
from dataclasses import dataclass
from typing import Optional, Any
from datetime import datetime


@dataclass
class TelemetryRecord:
    """Pojedynczy rekord telemetryczny."""
    timestamp: int
    device_id: str
    code: str
    val_num: Optional[float]
    val_str: Optional[str]
    
    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "device_id": self.device_id,
            "code": self.code,
            "val_num": self.val_num,
            "val_str": self.val_str
        }


@dataclass
class ProcessedReading:
    """Przetworzony odczyt z obliczeniami."""
    czas: datetime
    out_water_temp: Optional[float]
    in_water_temp: Optional[float]
    flow_rate: Optional[float]
    ac_vol: Optional[float]
    ac_curr: Optional[float]
    comp_freq: Optional[float]
    disc_temp: Optional[float]
    amb_temp: Optional[float]
    valve: float
    heat_temp_set: Optional[float]
    defrost: Optional[int]
    tryb: str
    P_el_kw: Optional[float]
    P_th_kw: Optional[float]
    COP: Optional[float]
    E_th_kwh: Optional[float]
    E_el_kwh: Optional[float]
