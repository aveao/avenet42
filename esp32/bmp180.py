from helpers import _write_to_i2c
from machine import I2C
import struct


# based on https://github.com/adafruit/Adafruit_BMP085_Unified/blob/master/Adafruit_BMP085_U.cpp
# and https://github.com/micropython-IMU/micropython-bmp180
class BMP180:
    i2c_address = 0x77

    def __init__(self, i2c_instance: I2C):
        self.i2c_instance = i2c_instance
        self.calibration = {}

    async def init(self):
        registers = {
            "AC1": [0xAA, ">h"],
            "AC2": [0xAC, ">h"],
            "AC3": [0xAE, ">h"],
            "AC4": [0xB0, ">H"],
            "AC5": [0xB2, ">H"],
            "AC6": [0xB4, ">H"],
            "VB1": [0xB6, ">h"],
            "VB2": [0xB8, ">h"],
            "MB": [0xBA, ">h"],
            "MC": [0xBC, ">h"],
            "MD": [0xBE, ">h"],
        }

        for register_name, register_data in registers.items():
            i2c_response = await _write_to_i2c(
                self.i2c_instance,
                bytes([register_data[0]]),
                i2c_device=self.i2c_address,
                read_bytes=2,
            )
            self.calibration[register_name] = struct.unpack(
                register_data[1], i2c_response
            )[0]

    def _compute_b5(self, temp_raw):
        X1 = (temp_raw - self.calibration["AC6"]) * (self.calibration["AC5"]) >> 15
        X2 = (self.calibration["MC"] << 11) / (X1 + self.calibration["MD"])
        return X1 + X2

    async def read_temperature(self) -> int:
        await _write_to_i2c(
            self.i2c_instance,
            b"\xF4\x2E",
            i2c_device=self.i2c_address,
            command_wait_s=0.005,
        )
        temp_raw = await _write_to_i2c(
            self.i2c_instance, b"\xF6", i2c_device=self.i2c_address, read_bytes=2
        )
        temp_raw = struct.unpack(">h", temp_raw)[0]

        B5 = self._compute_b5(temp_raw)
        t = int(B5 + 8) >> 4
        t /= 10

        return t

    async def read_pressure(self, oversample_mode: int = 3) -> int:
        temp = await self.read_temperature()
        await _write_to_i2c(
            self.i2c_instance,
            bytes([0xF4, 0x34 + (0x40 * oversample_mode)]),
            i2c_device=self.i2c_address,
            command_wait_s=(0.007 * oversample_mode),
        )
        pressure_raw = await _write_to_i2c(
            self.i2c_instance, b"\xF6", i2c_device=self.i2c_address, read_bytes=3
        )
        # TODO: improve this
        B5_raw = (int(temp * 10) << 4) - 8
        UP = ((pressure_raw[0] << 16) + (pressure_raw[1] << 8) + pressure_raw[2]) >> (
            8 - oversample_mode
        )
        B6 = B5_raw - 4000
        X1 = (self.calibration["VB2"] * (B6**2 / 2**12)) / 2**11
        X2 = self.calibration["AC2"] * B6 / 2**11
        X3 = X1 + X2
        B3 = ((int((self.calibration["AC1"] * 4 + X3)) << oversample_mode) + 2) / 4
        X1 = self.calibration["AC3"] * B6 / 2**13
        X2 = (self.calibration["VB1"] * (B6**2 / 2**12)) / 2**16
        X3 = ((X1 + X2) + 2) / 2**2
        B4 = abs(self.calibration["AC4"]) * (X3 + 32768) / 2**15
        B7 = (abs(UP) - B3) * (50000 >> oversample_mode)
        if B7 < 0x80000000:
            pascal = (B7 * 2) / B4
        else:
            pascal = (B7 / B4) * 2
        X1 = (pascal / 2**8) ** 2
        X1 = (X1 * 3038) / 2**16
        X2 = (-7357 * pascal) / 2**16
        return pascal + (X1 + X2 + 3791) / 2**4
