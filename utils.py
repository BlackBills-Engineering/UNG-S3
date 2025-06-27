# utils.py
"""
Вспомогательные функции: CRC-16-CCITT, упаковка/распаковка BCD.
"""

def calc_crc(data: bytes) -> int:
    """
    Вычисляет 16-битный CRC-CCITT (poly 0x1021, init 0x0000).
    Возвращает целое (0-0xFFFF).
    """
    crc = 0x0000
    for b in data:
        crc ^= b << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = (crc << 1) ^ 0x1021
            else:
                crc <<= 1
            crc &= 0xFFFF
    return crc


def _int_to_bcd(value: int, digit_count: int) -> bytes:
    """Преобразует целое value в BCD длиной digit_count цифр."""
    s = f"{value:0{digit_count}d}"
    return bytes(int(s[i : i + 2], 10) for i in range(0, digit_count, 2))


def bcd_pack(number: float, *, decimals: int, length: int) -> bytes:
    """
    Упаковывает число `number` в BCD-последовательность длиной `length` байт.
    `decimals` – сколько цифр после запятой хранится.
    """
    scaled = int(round(number * (10 ** decimals)))
    digit_count = length * 2   # 1 байт = 2 цифры
    return _int_to_bcd(scaled, digit_count)


def bcd_unpack(bcd: bytes, *, decimals: int) -> float:
    """
    Распаковывает BCD-последовательность `bcd` обратно в float
    с учётом `decimals` знаков после запятой.
    """
    digits = "".join(f"{byte:02d}" for byte in bcd)
    int_val = int(digits)
    return int_val / (10 ** decimals)
