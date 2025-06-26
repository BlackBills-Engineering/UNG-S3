# services/pump_service.py
from serial_io.driver import MKR5Driver
from schemas import PumpStatusResponse, NozzlesStatusResponse

# Предполагаем, что driver открыт и готов к работе (инициализирован в main.py)
driver = MKR5Driver(port="/dev/ttyS0", baudrate=9600)
# ... (в реальном коде driver лучше передавать через зависимость или глобально)

def get_status(pump_id: int) -> PumpStatusResponse:
    """
    Запрос статуса колонки: отправляет команду RETURN STATUS и ждёт ответа.
    Возвращает объект PumpStatusResponse с полями pump_id, status, active_nozzle и т.д.
    """
    # Формируем транзакцию команды: CD1 с кодом 0x0 (RETURN STATUS) [oai_citation:19‡file-lfc395pd3vvpi91fm1wkxs](file://file-LFc395PD3vvpi91fm1WKXs#:~:text=)
    trans_code = 0x01  # CD1
    dcc_return_status = 0x00  # команда "Return Status"
    data_bytes = bytes([dcc_return_status])
    length = len(data_bytes)
    # Поле длины (LNG) и сами данные
    transaction = bytes([trans_code, length]) + data_bytes
    # Отправляем и получаем ответ
    response = driver.send_command(pump_id, transaction)
    parsed = driver.parse_response(response)
    if not parsed:
        return None
    # Формируем ответную модель
    return PumpStatusResponse(
        pump_id=pump_id,
        status=parsed.get('pump_status', "UNKNOWN"),
        active_nozzle=parsed.get('current_nozzle'),
        volume=parsed.get('current_volume'),
        amount=parsed.get('current_amount')
    )

def get_nozzles_status(pump_id: int) -> NozzlesStatusResponse:
    """
    Получение статуса всех пистолетов: фактически также требует запроса Return Status 
    (колонка вернёт информацию о поднятом пистолете и ценах).
    """
    response = driver.send_command(pump_id, transaction)  # (можно повторно использовать транзакцию Return Status)
    parsed = driver.parse_response(response)
    if not parsed:
        return None
    # Из разбора возьмём текущий поднятый пистолет и его состояние. 
    # Для остальных пистолетов считаем, что они не подняты.
    nozzle_count = 4  # допустим, известно, что у данной колонки 4 пистолета
    nozzles = []
    active_nozzle = parsed.get('current_nozzle')
    nozzle_out = parsed.get('nozzle_out', False)
    current_price = parsed.get('current_price')
    for i in range(1, nozzle_count+1):
        is_lifted = (active_nozzle == i and nozzle_out)
        price = current_price if active_nozzle == i else None  # цена указывается для активного, для остальных можно взять из настроек
        nozzles.append({
            "nozzle": i,
            "is_lifted": is_lifted,
            "price": price or 0.0  # здесь можно хранить последнюю известную цену
        })
    return NozzlesStatusResponse(pump_id=pump_id, nozzles=nozzles)

def set_price(pump_id: int, prices: dict) -> bool:
    """
    Устанавливает цены на колонке. `prices` – словарь {номер_пистолета: цена}.
    Формирует транзакцию Price Update (CD5) и отправляет колонке.
    """
    # Формируем транзакцию CD5 (Price update). Код транзакции = 0x05, данные – по 3 байта BCD на каждую цену.
    trans_code = 0x05
    # Нам нужно отправить цены для всех логических пистолетов по порядку от 1 до N.
    # Определяем N:
    nozzle_numbers = sorted(prices.keys())
    N = nozzle_numbers[-1] if nozzle_numbers else 0
    price_bytes = b''
    for n in range(1, N+1):
        price_val = prices.get(n, 0.0)
        # Конвертируем price_val во внутренний формат: упакуем в 3 байта BCD [oai_citation:20‡file-lfc395pd3vvpi91fm1wkxs](file://file-LFc395PD3vvpi91fm1WKXs#:~:text=PRI%20is%20the%20price%20in,logical%20nozzle%20number%201%2C%20PRI2).
        price_bcd = bcd_pack(price_val, decimals=settings.PRICE_DECIMALS, length=3)
        price_bytes += price_bcd
    length = len(price_bytes)
    transaction = bytes([trans_code, length]) + price_bytes
    # Отправляем команду
    response = driver.send_command(pump_id, transaction)
    # Обычно колонка не присылает явного подтверждения на установку цены, 
    # но может обновить свой статус. Проверим ответ на ошибки:
    parsed = driver.parse_response(response)
    if 'error' in parsed:
        logging.error(f"Error in price update response: {parsed['error']}")
        return False
    logging.info(f"Price update for pump {pump_id} successful: {prices}")
    return True

def authorize(pump_id: int, nozzle: int = None):
    """
    Разрешает колонке начать выдачу (AUTHORIZE). 
    Если указан конкретный nozzle, сначала отправляется список разрешённых пистолетов.
    """
    transactions = bytearray()
    # Если задан конкретный пистолет, добавляем транзакцию CD2 (Allowed nozzle numbers) [oai_citation:21‡file-lfc395pd3vvpi91fm1wkxs](file://file-LFc395PD3vvpi91fm1WKXs#:~:text=NOZ1%201%20Nozzle%20number)
    if nozzle:
        trans_code = 0x02
        allowed_nozzles = [nozzle]
        data_bytes = bytes(allowed_nozzles)  # список номеров пистолетов
        length = len(data_bytes)
        transactions += bytes([trans_code, length]) + data_bytes
    # Добавляем транзакцию CD1 с командой AUTHORIZE (код команды 0x6) [oai_citation:22‡file-lfc395pd3vvpi91fm1wkxs](file://file-LFc395PD3vvpi91fm1WKXs#:~:text=)
    trans_code = 0x01
    dcc_authorize = 0x06
    transactions += bytes([trans_code, 1, dcc_authorize])
    # Отправляем пакет с одной или двумя транзакциями (в зависимости от наличия nozzle)
    response = driver.send_command(pump_id, transactions)
    parsed = driver.parse_response(response)
    # Проверим, сменился ли статус на AUTHORIZED:
    status = parsed.get('pump_status')
    if status != "AUTHORIZED":
        logging.warning(f"Pump {pump_id} authorize command sent, but status = {status}")
    else:
        logging.debug(f"Pump {pump_id} authorized successfully")
    # (Можно вернуть статус или просто логировать)

def preset_and_authorize(pump_id: int, request):
    """
    Устанавливает предустановленный лимит (объём или сумма) и авторизует колонку.
    """
    nozzle = request.nozzle
    volume = request.volume
    amount = request.amount
    transactions = bytearray()
    # Команда RESET (сброс дисплея) перед выдачей предварительно оплаченной дозы не всегда обязательна, можно выполнить для ясности
    # transactions += bytes([0x01, 1, 0x05])  # CD1: RESET (DCC 0x5)
    # Ограничение по пистолету, если указано
    if nozzle:
        trans_code = 0x02
        data_bytes = bytes([nozzle])
        transactions += bytes([trans_code, len(data_bytes)]) + data_bytes
    # Транзакция предустановки:
    if volume is not None:
        # Используем Preset Volume (CD3) – код транзакции 0x03, 4 байта BCD объёма [oai_citation:23‡file-lfc395pd3vvpi91fm1wkxs](file://file-LFc395PD3vvpi91fm1WKXs#:~:text=VOL%204%20Volume)
        trans_code = 0x03
        vol_bytes = bcd_pack(volume, decimals=settings.VOL_DECIMALS, length=4)
        transactions += bytes([trans_code, len(vol_bytes)]) + vol_bytes
    elif amount is not None:
        # Preset Amount (CD4) – код 0x04, 4 байта BCD суммы [oai_citation:24‡file-lfc395pd3vvpi91fm1wkxs](file://file-LFc395PD3vvpi91fm1WKXs#:~:text=AMO%204%20Amount)
        trans_code = 0x04
        amt_bytes = bcd_pack(amount, decimals=settings.AMT_DECIMALS, length=4)
        transactions += bytes([trans_code, len(amt_bytes)]) + amt_bytes
    # Добавляем команду AUTHORIZE
    trans_code = 0x01
    dcc_authorize = 0x06
    transactions += bytes([trans_code, 1, dcc_authorize])
    # Отправляем пакет из нескольких транзакций: [Allowed Nozzle?] + [Preset] + [Authorize]
    response = driver.send_command(pump_id, transactions)
    parsed = driver.parse_response(response)
    if parsed.get('pump_status') != "AUTHORIZED":
        logging.error(f"Preset authorization failed, status = {parsed.get('pump_status')}")
    else:
        logging.info(f"Pump {pump_id} authorized with preset (volume={volume}, amount={amount})")