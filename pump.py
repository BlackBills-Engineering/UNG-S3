# router/pump.py
from fastapi import APIRouter, HTTPException
import pump_service
from schemas import PumpStatusResponse, NozzlesStatusResponse, PriceUpdateRequest, PresetRequest, PumpList, NozzleList

router = APIRouter()

@router.get("/", response_model=PumpList)
async def get_all_pumps():
    pumps = pump_service.list_pumps()
    return {"pump_ids": pumps}

@router.get("/{pump_id}/nozzles", response_model=NozzleList)
async def get_pump_nozzles(pump_id: int):
    try:
        nos = pump_service.list_nozzles(pump_id)
        return {"nozzles": nos}
    except RuntimeError as e:
        raise HTTPException(status_code=404, detail=str(e))

@router.get("/{pump_id}/status", response_model=PumpStatusResponse, summary="Получить статус колонки", description="Возвращает текущий статус ТРК (состояние и активный пистолет).")
def get_pump_status(pump_id: int):
    """Эндпоинт для получения статуса колонки (Pump status)."""
    status = pump_service.get_status(pump_id)
    if status is None:
        raise HTTPException(status_code=404, detail="Pump not found")
    return status

@router.get("/{pump_id}/nozzles", response_model=NozzlesStatusResponse, summary="Статусы пистолетов", description="Возвращает статусы всех пистолетов данной колонки (поднят/опущен, текущая цена и т.д.).")
def get_nozzles_status(pump_id: int):
    """Эндпоинт для получения статуса всех пистолетов (Nozzle status and price)."""
    data = pump_service.get_nozzles_status(pump_id)
    if data is None:
        raise HTTPException(status_code=404, detail="Pump not found")
    return data

@router.put("/{pump_id}/price", response_model=None, summary="Установить цену топлива", description="Устанавливает новую цену на топливо для всех пистолетов колонки.")
def set_price(pump_id: int, request: PriceUpdateRequest):
    """Эндпоинт для установки цены на топливо на колонке (Price update)."""
    success = pump_service.set_price(pump_id, request.prices)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to update price")
    return {"message": "Prices updated successfully"}

@router.post("/{pump_id}/allow", response_model=None, summary="Разрешить заправку", description="Разрешает колонке начать заправку (снятие блокировки). Опционально можно указать конкретный пистолет.")
def authorize_pump(pump_id: int, nozzle: int = None):
    """Эндпоинт для авторизации колонки (команда AUTHORIZE, опционально ограничена пистолетом)."""
    pump_service.authorize(pump_id, nozzle)
    return {"message": "Pump authorized"}

@router.post("/{pump_id}/authenticate", response_model=None, summary="Предустановленная заправка", description="Авторизует колонку с предустановленным объёмом или суммой (предварительная оплата).")
def preset_and_authorize(pump_id: int, request: PresetRequest):
    """
    Эндпоинт для установки лимита (объём или сумма) и разрешения заправки.
    Если указаны оба параметра (volume и amount), будет использован volume.
    """
    pump_service.preset_and_authorize(pump_id, request)
    return {"message": "Pump authorized with preset"}