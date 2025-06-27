import serial
import logging
from utils import calc_crc, bcd_pack, bcd_unpack
import settings

# MKR5 DART-уровень-3 коды команд (DCC)
RETURN_STATUS        = 0x00
RETURN_PUMP_PARAMS   = 0x02
RETURN_PUMP_IDENTITY = 0x03
# ...

# Префиксы транзакций (TRANS)
CD1 = 0x01  # команда
# ...

class MKR5Driver:
    def __init__(self, port: str, baudrate: int = settings.BAUDRATE, timeout: float = settings.TIMEOUT):
        self.port_name = port
        self.baudrate  = baudrate
        self.timeout   = timeout
        self.ser       = None
        self._tx_number = 0

    def open(self):
        self.ser = serial.Serial(self.port_name,
                                 self.baudrate,
                                 bytesize=8,
                                 parity=serial.PARITY_ODD,
                                 stopbits=1,
                                 timeout=self.timeout)
        logging.info(f"Opened serial port {self.port_name}")

    def close(self):
        if self.ser and self.ser.is_open:
            self.ser.close()
            logging.info("Serial port closed")

    def _next_tx(self) -> int:
        # счётчик блока (1–15)
        self._tx_number = (self._tx_number % 0x0F) + 1
        return self._tx_number

    def send_command(self, pump_id: int, dcc: int, payload: bytes = b"") -> bytes:
        """
        Формирует и отправляет DART-блок с одной транзакцией CD1.
        pump_id: 0..31 => физический адрес = 0x50+ pump_id
        dcc: код команды из DCC (например, RETURN_STATUS)
        payload: дополнительные байты, если нужно
        """
        if not self.ser or not self.ser.is_open:
            raise RuntimeError("Serial port is not open")

        addr = 0x50 + pump_id
        txn = self._next_tx()
        # __CTRL__: бит7=1 (master→slave), биты6-4 = txn, биты3-0=0
        ctrl = 0x80 | ((txn & 0x0F) << 4)

        # формируем уровень-3: CD1,DCC
        data3 = bytes([CD1, 1]) + bytes([dcc])
        # если payload есть — его инъектим внутрь (хотя для CD1 у нас payload==b"")
        block = bytes([addr, ctrl]) + data3

        # считаем CRC уровня-2
        crc = calc_crc(block)
        crc_bytes = bytes([crc & 0xFF, (crc >> 8) & 0xFF])

        # ETX=0x03, SF=0xFA
        packet = block + crc_bytes + b"\x03\xFA"

        logging.debug(f"→ [{pump_id}] " + packet.hex())
        self.ser.reset_input_buffer()
        self.ser.write(packet)

        # читаем до стоп-флага 0xFA
        resp = self.ser.read_until(expected=b"\xFA")
        logging.debug(f"← [{pump_id}] " + resp.hex())
        return resp

    def parse_response(self, resp: bytes) -> dict:
        """
        Разбирает поступивший блок (ориентируясь на DCC=0x01 → DC транзакции).
        Возвращает словарь с ключами:
          - pump_status
          - current_volume, current_amount
          - current_nozzle, nozzle_out, current_price
          - pump_identity (str)
          - grades_mask (int)  ← из DC7
        """
        data = {}
        # отбрасываем addr,ctrl
        core = resp[2:-2]   # до CRC и ETX/SF
        # проверяем CRC
        recv_crc = core[-2] | (core[-1] << 8)
        calc = calc_crc(resp[0:-4])
        if recv_crc != calc:
            raise RuntimeError("CRC mismatch")

        i = 0
        while i < len(core):
            trans = core[i]
            ln    = core[i+1]
            content = core[i+2 : i+2+ln]
            # DC1: статус
            if trans == 0x01:
                st = content[0]
                mapping = {
                    0: "NOT_PROGRAMMED", 1: "RESET", 2: "AUTHORIZED",
                    4: "FILLING",        5: "FILLING_COMPLETE",
                    6: "MAX_REACHED",    7: "SWITCHED_OFF"
                }
                data["pump_status"] = mapping.get(st, f"UNKNOWN({st})")
            # DC2: vol+amt
            elif trans == 0x02:
                vol = bcd_unpack(content[0:4], decimals=settings.VOL_DECIMALS)
                amt = bcd_unpack(content[4:8], decimals=settings.AMT_DECIMALS)
                data["current_volume"] = vol
                data["current_amount"] = amt
            # DC3: nozzle+price
            elif trans == 0x03:
                price = bcd_unpack(content[0:3], decimals=settings.PRICE_DECIMALS)
                noz   = content[3] & 0x0F
                outf  = bool((content[3] & 0x10) >> 4)
                data["current_nozzle"] = noz or None
                data["nozzle_out"] = outf
                data["current_price"] = price
            # DC7: pump parameters (16-ый транзакций — DART full impl.)  
            elif trans == 0x07:
                # content: [..., GRADE1, GRADE2, ...] – здесь один бит = существование града
                # допустим, каждый байт LSB бит0 = 1 → есть nozzle №(idx+1)
                grades = 0
                # смещение: первые 1(reserved22)+1+1+1+5 +4+2 = 36 байт, потом 15 байт grades
                # для простоты: берем последние 15 байт
                grade_bytes = content[-15:]
                for idx, b in enumerate(grade_bytes):
                    if b != 0:
                        grades |= (1 << idx)
                data["grades_mask"] = grades
            # DC9: identity
            elif trans == 0x09:
                # 5-байт BCD
                pid = "".join(f"{b:02X}" for b in content)
                data["pump_identity"] = pid
            else:
                logging.debug(f"Unknown DC trans {trans:02X}")
            i += 2 + ln
        return data