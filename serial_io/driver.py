# serial/driver.py
import serial_io
import logging
from utils import calc_crc, bcd_pack, bcd_unpack

class MKR5Driver:
    def __init__(self, port: str, baudrate: int = 9600, timeout: float = 0.5):
        self.port_name = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.ser = None  # объект serial.Serial будет храниться здесь

    def open(self):
        """Открывает последовательный порт."""
        self.ser = serial_io.Serial(self.port_name, self.baudrate, bytesize=8, parity=serial.PARITY_NONE, stopbits=1, timeout=self.timeout)
        logging.info(f"Opened serial port {self.port_name} at {self.baudrate} baud.")

    def close(self):
        """Закрывает последовательный порт."""
        if self.ser and self.ser.is_open:
            self.ser.close()
            logging.info("Serial port closed.")

    def send_command(self, pump_id: int, transactions: bytes) -> bytes:
        """
        Формирует и отправляет пакет с транзакциями на указанный насос.
        `transactions` – байтовая последовательность, представляющая данные транзакций уровня 3 (без адреса, CRC и окончаний).
        Возвращает сырые данные ответа (без разбора).
        """
        if not self.ser or not self.ser.is_open:
            raise RuntimeError("Serial port is not open")

        # Формирование полного блока протокола MKR5
        addr = 0x50 + pump_id  # адрес устройства (например, pump_id=1 -> адрес 0x51) [oai_citation:1‡file-lfc395pd3vvpi91fm1wkxs](file://file-LFc395PD3vvpi91fm1WKXs#:~:text=Each%20pump%20has%20a%20device,block%20is%20addressed%20to%20the)
        # CTRL: формируем управляющий байт (Master->Slave сообщение с номером блока)
        # Для простоты: мастер (бит7=1), TX# возьмём 1..F циклично, например:
        ctrl = 0x80 | (pump_id & 0x0F)  # 0x80 устанавливает бит мастера; низкие 4 бита – условный номер транзакции
        # Начало блока: адрес, контроль
        packet = bytearray([addr, ctrl])
        # Если несколько транзакций, добавляем разделитель SD (Start Delimiter). 
        # В протоколе MKR5 используются специальные разделители и окончания:
        SD = 0xF1  # (пример: предположим 0xF1 как старт транзакции, в реальности согласно спецификации) 
        packet += SD.to_bytes(1, 'little') + transactions  # добавляем транзакционные данные
        # Вычисляем CRC-16 (CCITT) по всему пакету (ADR...последний байт данных)
        crc_value = calc_crc(packet)
        crc_low = crc_value & 0xFF
        crc_high = (crc_value >> 8) & 0xFF
        packet += bytes([crc_low, crc_high])
        # Добавляем окончание пакета: ETX и Stop-flag (0x03 и 0xFA согласно спецификации) [oai_citation:2‡file-lfc395pd3vvpi91fm1wkxs](file://file-LFc395PD3vvpi91fm1WKXs#:~:text=ADR%20CTRL%20SD%20OPC%20Data,H%20ETX%20SF)
        packet += b'\x03\xFA'

        # Логируем пакет на отправку (в шестнадцатеричном виде для отладки)
        logging.debug(f"Sending packet to pump {pump_id}: " + packet.hex())
        # Отправляем данные в порт
        self.ser.write(packet)
        # Читаем ответ до получения стоп-байта 0xFA
        response = self.ser.read_until(expected=b'\xFA')
        logging.debug(f"Received raw response from pump {pump_id}: " + response.hex())
        return response

    def parse_response(self, response: bytes) -> dict:
        """
        Разбор ответа насоса. Возвращает структуру данных с результатами.
        (Для упрощения рассматриваем случай одного блока с одной-двумя транзакциями.)
        """
        data = {}
        if len(response) < 5:
            logging.error("Response too short or empty")
            return data
        # Проверка контрольных символов окончания
        if response[-2] == 0x03 and response[-1] == 0xFA:
            # Убираем ETX и SF для парсинга
            core_data = response[:-2]
        else:
            logging.warning("Response does not end with ETX+SF as expected")
            core_data = response
        # Проверка CRC
        recv_crc_low = core_data[-2]
        recv_crc_high = core_data[-1]
        core_wo_crc = core_data[:-2]
        calc = calc_crc(core_wo_crc)
        if ((calc & 0xFF) != recv_crc_low) or (((calc >> 8) & 0xFF) != recv_crc_high):
            logging.error("CRC mismatch in response!")
            data['error'] = "CRC_ERROR"
            # продолжим разбор даже при ошибке CRC (для диагностики)
        # Теперь core_wo_crc содержит: ADR, CTRL, SD, транзакции... 
        # Пропустим адрес и контроль:
        adr = core_wo_crc[0]
        ctrl = core_wo_crc[1]
        # Остальные байты могут включать несколько транзакций
        # Для простоты предположим максимум две транзакции: Pump Status (DC1) и Nozzle Status (DC3).
        # Ищем коды транзакций в данных
        # Спецификация: код транзакции – первый байт каждого блока транзакции.
        payload = core_wo_crc[2:]  # данные после ADR и CTRL
        # В ответе от колонки транзакции начинаются сразу (возможно с разделителем, опустим).
        # Разбор в зависимости от кода:
        i = 0
        while i < len(payload):
            trans_code = payload[i]
            length = payload[i+1]
            content = payload[i+2 : i+2+length]
            if trans_code == 0x01:  # Pump status (DC1) [oai_citation:3‡file-lfc395pd3vvpi91fm1wkxs](file://file-LFc395PD3vvpi91fm1WKXs#:~:text=STATUS%201%20Pump%20status)
                status_code = content[0]
                data['pump_status_code'] = status_code
                # Расшифруем статус в текст, согласно протоколу:
                status_map = {0: "PUMP NOT PROGRAMMED", 1: "RESET", 2: "AUTHORIZED", 
                              4: "FILLING", 5: "FILLING COMPLETE", 6: "MAX REACHED", 7: "SWITCHED OFF"}
                data['pump_status'] = status_map.get(status_code, f"UNKNOWN({status_code})")
            elif trans_code == 0x03:  # Nozzle status and filling price (DC3) [oai_citation:4‡file-lfc395pd3vvpi91fm1wkxs](file://file-LFc395PD3vvpi91fm1WKXs#:~:text=3)
                # Первый элемент PRI (3 байта цены BCD), второй NOZIO (1 байт с номером и флагом)
                if len(content) >= 4:
                    price_bcd = content[0:3]
                    nozzle_info = content[3]
                    price = bcd_unpack(price_bcd, decimals=settings.PRICE_DECIMALS)
                    nozzle_num = nozzle_info & 0x0F  # младшие 4 бита – номер пистолета
                    nozzle_out = (nozzle_info & 0x10) >> 4  # 5-й бит – признак поднятия (1=out) [oai_citation:5‡file-lfc395pd3vvpi91fm1wkxs](file://file-LFc395PD3vvpi91fm1WKXs#:~:text=NOZIO%20bits%200,NOZIO)
                    data['current_nozzle'] = nozzle_num if nozzle_num != 0 else None
                    data['nozzle_out'] = bool(nozzle_out)
                    data['current_price'] = price
            elif trans_code == 0x02:  # Filled volume and amount (DC2)
                # Контент: 4 байта объём (BCD) + 4 байта сумма (BCD)
                vol_bcd = content[0:4]
                amt_bcd = content[4:8]
                volume = bcd_unpack(vol_bcd, decimals=settings.VOL_DECIMALS)
                amount = bcd_unpack(amt_bcd, decimals=settings.AMT_DECIMALS)
                data['current_volume'] = volume
                data['current_amount'] = amount
            else:
                logging.info(f"Unknown transaction code in response: {trans_code}")
            i += 2 + length  # перейти к следующей транзакции
        return data