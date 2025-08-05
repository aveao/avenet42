from helpers import _write_to_i2c, debug_print
from machine import I2C
import math
import struct


def _calc_crc8(data: bytes) -> int:
    crc = 0xFF
    for data_byte in data:
        crc ^= data_byte
        for _ in range(8):
            if crc & 0x80:
                crc = (crc << 1) ^ 0x31
            else:
                crc = crc << 1
    # return the first byte
    return crc & 0xFF


class SCD41:
    def __init__(self, i2c_instance: I2C):
        self.i2c_instance = i2c_instance

    async def start_periodic_measurement(self, low_power: bool = False):
        command = b"\x21\xac" if low_power else b"\x21\xb1"
        await _write_to_i2c(self.i2c_instance, command)

    async def stop_periodic_measurement(self):
        await _write_to_i2c(self.i2c_instance, b"\x3f\x86", command_wait_s=0.5)

    async def measure_single_shot(self, rht_only: bool = False):
        command = b"\x21\x96" if rht_only else b"\x21\x9d"
        appropriate_wait_s = 0.05 if rht_only else 5
        await _write_to_i2c(
            self.i2c_instance, command, command_wait_s=appropriate_wait_s
        )

    async def get_data_ready_status(self) -> bool:
        # TODO: Use a bitmask here instead of comparing directly
        # if 11 lsb are 0, then data is not ready
        return (
            await _write_to_i2c(self.i2c_instance, b"\xe4\xb8", read_bytes=3)
            != b"\x80\x00\xa2"
        )

    async def get_automatic_self_calibration_enabled(self) -> bool:
        response = await _write_to_i2c(self.i2c_instance, b"\x23\x13", read_bytes=3)
        parsed_result = struct.unpack(">H", response[0:2])[0]
        return bool(parsed_result)

    async def set_automatic_self_calibration_enabled(self, asc_status: bool):
        parameters = struct.pack(">H", int(asc_status))
        parameters += bytes([_calc_crc8(parameters)])
        await _write_to_i2c(self.i2c_instance, b"\x24\x16" + parameters)

    async def get_sensor_altitude(self) -> int:
        response = await _write_to_i2c(self.i2c_instance, b"\x23\x22", read_bytes=3)
        sensor_altitude_masl = struct.unpack(">H", response[0:2])[0]
        return sensor_altitude_masl

    async def set_sensor_altitude(self, sensor_altitude_masl: int):
        parameters = struct.pack(">H", sensor_altitude_masl)
        parameters += bytes([_calc_crc8(parameters)])
        await _write_to_i2c(self.i2c_instance, b"\x24\x27" + parameters)

    async def get_temperature_offset_raw(self) -> float:
        response = await _write_to_i2c(self.i2c_instance, b"\x23\x18", read_bytes=3)
        temp_offset = 175 * (struct.unpack(">H", response[0:2])[0] / 2**16)
        return temp_offset

    async def get_temperature_offset(self) -> float:
        raw_temp_offset = await self.get_temperature_offset_raw()
        return math.ceil(raw_temp_offset * 10) / 10

    async def set_temperature_offset(self, temperature_offset: float):
        current_temp_offset = await self.get_temperature_offset()
        if current_temp_offset == temperature_offset:
            debug_print("Avoiding setting SCD41 temperature offset as it's already set to same.")
        parameters = struct.pack(">H", int((temperature_offset * 2**16) / 175))
        parameters += bytes([_calc_crc8(parameters)])
        await _write_to_i2c(self.i2c_instance, b"\x24\x1d" + parameters)

    async def set_ambient_pressure(self, ambient_mbar: int):
        parameters = struct.pack(">H", ambient_mbar)
        parameters += bytes([_calc_crc8(parameters)])
        await _write_to_i2c(self.i2c_instance, b"\xe0\x00" + parameters)

    async def persist_settings(self):
        await _write_to_i2c(self.i2c_instance, b"\x36\x15", command_wait_s=0.8)

    async def perform_factory_reset(self):
        await _write_to_i2c(self.i2c_instance, b"\x36\x32", command_wait_s=1.2)

    async def reinit(self):
        await _write_to_i2c(self.i2c_instance, b"\x36\x46", command_wait_s=0.02)

    async def perform_forced_recalibration(self, reference_co2_ppm: int) -> tuple:
        parameters = struct.pack(">H", reference_co2_ppm)
        parameters += bytes([_calc_crc8(parameters)])
        response = await _write_to_i2c(
            self.i2c_instance,
            b"\x36\x2f" + parameters,
            read_bytes=3,
            command_wait_s=0.4,
        )
        co2_drift = struct.unpack(">h", response[0:2]) - 0x8000
        return ((co2_drift != 0x7FFF), co2_drift)

    async def get_serial_number(self) -> int:
        sn_response = await _write_to_i2c(self.i2c_instance, b"\x36\x82", read_bytes=9)
        # this has to be a mess bc micropython does not support starargs properly
        # https://github.com/micropython/micropython/issues/1329
        sn = struct.unpack(
            ">Q",
            bytes(
                [
                    0,
                    0,
                    sn_response[0],
                    sn_response[1],
                    sn_response[3],
                    sn_response[4],
                    sn_response[6],
                    sn_response[7],
                ]
            ),
        )[0]
        return sn

    async def perform_self_test(self) -> bool:
        return (
            await _write_to_i2c(
                self.i2c_instance, b"\x36\x39", read_bytes=3, command_wait_s=10
            )
            == b"\x00\x00\x81"
        )

    async def power_down(self) -> bool:
        return await _write_to_i2c(self.i2c_instance, b"\x36\xe0")

    async def wake_up(self) -> bool:
        return await _write_to_i2c(self.i2c_instance, b"\x36\xf6", command_wait_s=0.02)

    async def read_measurement(self) -> tuple:
        measurement_data = await _write_to_i2c(
            self.i2c_instance, b"\xec\x05", read_bytes=9
        )
        # If we failed to read the measurement data, return fake data
        if not measurement_data:
            return False, 0, 0, 0

        co2 = (measurement_data[0] << 8) + measurement_data[1]
        celsius = -45 + (
            175 * ((measurement_data[3] << 8) + measurement_data[4]) / ((2**16) - 1)
        )
        relative_humidity = (
            100 * ((measurement_data[6] << 8) + measurement_data[7]) / ((2**16) - 1)
        )
        debug_print(
            "co2 ppm:", co2, "temp celsius:", celsius, "rh %:", relative_humidity
        )
        return True, co2, celsius, relative_humidity
