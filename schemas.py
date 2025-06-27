# schemas.py
from pydantic import BaseModel, Field
from typing import Dict, List, Optional

class PumpStatusResponse(BaseModel):
    pump_id: int = Field(..., description="Номер колонки")
    status: str = Field(..., description="Состояние колонки (напр. RESET, AUTHORIZED, FILLING и т.д.)")
    active_nozzle: Optional[int] = Field(None, description="Номер пистолета, который поднят/активен (если есть)")
    volume: Optional[float] = Field(None, description="Отпущенный объём с начала текущей заправки (если идёт отпуск)")
    amount: Optional[float] = Field(None, description="Отпущенная сумма с начала текущей заправки (если идёт отпуск)")

class NozzleStatus(BaseModel):
    nozzle: int = Field(..., description="Номер пистолета")
    is_lifted: bool = Field(..., description="True, если пистолет поднят (независимо от авторизации)")
    price: float = Field(..., description="Текущая установленная цена на топливо для данного пистолета")

class NozzlesStatusResponse(BaseModel):
    pump_id: int
    nozzles: List[NozzleStatus] = Field(..., description="Список всех пистолетов с их состоянием")

class PriceUpdateRequest(BaseModel):
    prices: Dict[int, float] = Field(..., description="Новые цены: ключ – номер пистолета, значение – цена")

class PresetRequest(BaseModel):
    nozzle: Optional[int] = Field(None, description="Номер пистолета для заправки (если None – не ограничено)")
    volume: Optional[float] = Field(None, description="Предустановленный объём (литры)")
    amount: Optional[float] = Field(None, description="Предустановленная сумма (валюта)")
    # Валидация: хотя бы один из volume/amount должен быть задан
    # ... (можно реализовать метод .validate() или использование Pydantic Validators)