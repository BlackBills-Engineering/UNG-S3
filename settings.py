# settings.py
"""
Простая конфигурация проекта.
Если нужен .env или динамика — перенесите в pydantic BaseSettings.
"""

COM_PORT   = "/dev/ttyS0"   # <—- измените под свой порт
BAUDRATE   = 9600
TIMEOUT    = 0.5              # сек

# Сколько знаков дробной части храним в BCD у разных величин
PRICE_DECIMALS = 2   # 55.50  =>  "5550"
VOL_DECIMALS   = 3   #  20.345 => "20345"
AMT_DECIMALS   = 2   # 100.00  => "10000"
