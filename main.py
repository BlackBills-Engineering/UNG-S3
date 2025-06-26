# main.py
from fastapi import FastAPI
from router import pump  # наш роутер колонок
from config import settings
import logging

# Инициализация логирования (запись в файл и консоль, уровень DEBUG)
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("pump_api.log"),
        logging.StreamHandler()
    ]
)

app = FastAPI(title="Mekser MKR5 Pump API", description="API для управления ТРК Mekser (MKR5)", version="1.0")

# Подключение роутеров
app.include_router(pump.router, prefix="/pumps", tags=["pumps"])

# При старте приложения открываем соединение с COM-портом
from serial.driver import MKR5Driver

driver = MKR5Driver(port=settings.COM_PORT, baudrate=settings.BAUDRATE)
driver.open()  # установить соединение

# Можно использовать events: startup/shutdown для автоматического управления ресурсами
@app.on_event("startup")
def startup_event():
    driver.open()

@app.on_event("shutdown")
def shutdown_event():
    driver.close()