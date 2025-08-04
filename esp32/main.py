from machine import I2C, SoftI2C, Pin
import gc
import uos
import utime
import machine
import network
from helpers import (
    debug_print,
    appropriate_sleep,
    appropriate_async_sleep,
    ensure_wlan_connected,
    DATA_FORMAT_ID,
    config,
    update_config,
    wlan_enabled,
    bt_enabled,
    pressure_to_altitude,
)
from influx_helpers import send_metrics_to_influx
from web_server import set_webserver_status_data
from scd41 import SCD41

if config["screen"]:
    import waveshare213

import uasyncio
import struct


if config["i2c"]["use_softi2c"]:
    i2c = SoftI2C(
        scl=Pin(config["pins"]["i2c_scl"]),
        sda=Pin(config["pins"]["i2c_sda"]),
        freq=config["i2c"]["frequency"],
    )
else:
    i2c = I2C(
        config["i2c"]["peripheral_id"],
        scl=Pin(config["pins"]["i2c_scl"]),
        sda=Pin(config["pins"]["i2c_sda"]),
        freq=config["i2c"]["frequency"],
    )
i2c_peripherals = i2c.scan()
debug_print("I2C peripherals:", i2c_peripherals)

# if scd41 sensor is not present, don't do anything
while 0x62 not in i2c_peripherals:
    appropriate_sleep(10)
    i2c_peripherals = i2c.scan()
    debug_print("I2C peripherals:", i2c_peripherals)

use_bmp180 = 0x77 in i2c_peripherals
use_bmp280 = 0x76 in i2c_peripherals

if use_bmp180:
    from bmp180 import BMP180
if use_bmp280:
    from bmp280 import BMP280

if config["bluetooth"]["enabled"]:
    import aioble
    from helpers import (
        _ENV_SENSE_UUID,
        _ENV_SENSE_CO2_UUID,
        _ENV_SENSE_TEMP_UUID,
        _ENV_SENSE_RH_UUID,
        _ENV_SENSE_ELEVATION_UUID,
        _ENV_SENSE_PRESSURE_UUID,
        _ENV_SENSE_CO2_HISTORIC_UUID,
        _ADV_APPEARANCE_GENERIC_THERMOMETER,
        _ENV_CONFIG_UUID,
        _ENV_COMPLEX_COMMS_UUID,
    )

    ble_service = aioble.Service(_ENV_SENSE_UUID)
    co2_characteristic = aioble.Characteristic(
        ble_service, _ENV_SENSE_CO2_UUID, read=True, notify=True
    )
    temp_characteristic = aioble.Characteristic(
        ble_service, _ENV_SENSE_TEMP_UUID, read=True, notify=True
    )
    rh_characteristic = aioble.Characteristic(
        ble_service, _ENV_SENSE_RH_UUID, read=True, notify=True
    )
    if use_bmp180 or use_bmp280:
        elevation_characteristic = aioble.Characteristic(
            ble_service, _ENV_SENSE_ELEVATION_UUID, read=True, notify=True
        )
        pressure_characteristic = aioble.Characteristic(
            ble_service, _ENV_SENSE_PRESSURE_UUID, read=True, notify=True
        )
    config_characteristic = aioble.BufferedCharacteristic(
        ble_service, _ENV_CONFIG_UUID, read=False, write=True, max_len=512
    )
    complex_comms_characteristic = aioble.BufferedCharacteristic(
        ble_service, _ENV_COMPLEX_COMMS_UUID, read=True, write=True, max_len=512
    )
    co2_historic_characteristic = aioble.Characteristic(
        ble_service, _ENV_SENSE_CO2_HISTORIC_UUID, read=True
    )
    aioble.register_services(ble_service)

wlan = network.WLAN(network.STA_IF)

if config["pins"].get("led"):
    led_pin = Pin(config["pins"]["led"], machine.Pin.OUT)


async def bluetooth_task():
    aioble.config(gap_name=config["bluetooth"]["name"])

    while True:
        if not bt_enabled():
            await appropriate_async_sleep(5)
            continue

        # Broad try-except as BT can die randomly with CancelledError, lol
        try:
            async with await aioble.advertise(
                config["bluetooth"]["advertisement_freq_us"],
                name=config["bluetooth"]["name"],
                services=[_ENV_SENSE_UUID],
                appearance=_ADV_APPEARANCE_GENERIC_THERMOMETER,
            ) as connection:
                debug_print("Connection from", connection.device)
                await connection.disconnected(timeout_ms=None)
        except Exception as e:
            debug_print("Exception during BT:", e)
            continue


async def bt_complex_comms_task():
    scd41 = SCD41(i2c)
    while True:
        complex_comms_characteristic.write(b"ready")
        characteristic_data = complex_comms_characteristic.read()
        while characteristic_data == b"ready":
            await uasyncio.sleep(1)
            characteristic_data = complex_comms_characteristic.read()

        debug_print("got complex command:", characteristic_data)

        if characteristic_data == b"reset":
            await scd41.stop_periodic_measurement()
            await scd41.perform_factory_reset()
            machine.reset()


async def bmp180_task(
    bmp180_inst: BMP180,
    scd41_inst: SCD41,
) -> (float, float):
    # Read and set ambient pressure to increase accuracy
    oversampling_level = (
        config["bmp180"]["oversampling_wlan"]
        if wlan_enabled()
        else config["bmp180"]["oversampling"]
    )
    pressure_pa = await bmp180_inst.read_pressure(oversample_mode=oversampling_level)
    elevation_m = pressure_to_altitude(pressure_pa / 100)

    debug_print(
        "pressure Pa:",
        pressure_pa,
        "elevation m:",
        elevation_m,
    )

    if (
        pressure_pa > config["bmp180"]["upper_pressure"]
        or config["bmp180"]["lower_pressure"] > pressure_pa
    ):
        debug_print("Rejecting pressure due to drift")
        return pressure_pa, 0.0

    await scd41_inst.set_ambient_pressure(int(pressure_pa / 100))
    # Notify the pressure-related stuff early
    if config["bluetooth"]["enabled"]:
        pressure_characteristic.write(
            struct.pack("<I", int(pressure_pa * 10)), send_update=True
        )
        elevation_characteristic.write(
            struct.pack("<I", int(elevation_m * 100)), send_update=True
        )
    return pressure_pa, elevation_m


async def bmp280_task(
    bmp280_inst: BMP280, scd41_inst: SCD41, temperature: float
) -> (float, float):
    pressure_pa = bmp280_inst.pressure_with_ext_temp(temperature)
    elevation_m = pressure_to_altitude(pressure_pa / 100)

    debug_print(
        "pressure Pa:",
        pressure_pa,
        "elevation m:",
        elevation_m,
    )

    if (
        pressure_pa > config["bmp280"]["upper_pressure"]
        or config["bmp280"]["lower_pressure"] > pressure_pa
    ):
        debug_print("Rejecting pressure due to drift")
        return pressure_pa, 0.0

    await scd41_inst.set_ambient_pressure(int(pressure_pa / 100))
    # Notify the pressure-related stuff early
    if config["bluetooth"]["enabled"]:
        pressure_characteristic.write(
            struct.pack("<I", int(pressure_pa * 10)), send_update=True
        )
        elevation_characteristic.write(
            struct.pack("<I", int(elevation_m * 100)), send_update=True
        )
    return pressure_pa, elevation_m


async def sensor_task():
    scd41 = SCD41(i2c)
    if use_bmp180:
        bmp180 = BMP180(i2c)
        await bmp180.init()
    elif use_bmp280:
        bmp280 = BMP280(i2c)
        bmp_usecase = (
            config["bmp280"]["usecase_wlan"]
            if wlan_enabled()
            else config["bmp280"]["usecase"]
        )
        bmp280.use_case(bmp_usecase)
        bmp280.normal_measure()
    # account for hot restarts
    await scd41.stop_periodic_measurement()

    serial_number = await scd41.get_serial_number()
    await scd41.set_automatic_self_calibration_enabled(config["scd41"]["asc"])
    asc_status = await scd41.get_automatic_self_calibration_enabled()
    if "temp_offset" in config["scd41"]:
        await scd41.set_temperature_offset(config["scd41"]["temp_offset"])
    sensor_altitude_masl = await scd41.get_sensor_altitude()
    temp_offset = await scd41.get_temperature_offset()
    free_storage = uos.statvfs("/")[1] * uos.statvfs("/")[3]
    debug_print(
        "scd41 serial number:",
        serial_number,
        "asc:",
        asc_status,
        "sensor masl:",
        sensor_altitude_masl,
        "temperature offset:",
        temp_offset,
        "free storage b:",
        free_storage,
    )
    self_test_result = await scd41.perform_self_test()
    debug_print("self test result:", self_test_result)
    # TODO: act on self test maybe?

    log_files = {}

    for log_entry in config["logs"]:
        log_files[log_entry] = open(f"logs/{log_entry}.log", "ab")
        log_files[log_entry].write(
            b"AN42"
            + bytes([DATA_FORMAT_ID[log_entry], int(config["scd41"]["low_power"])])
        )
        # pressure is 3 bytes per datapoint
        if log_entry == "pressure":
            log_files[log_entry].write(b"\x00")

    await scd41.start_periodic_measurement(low_power=config["scd41"]["low_power"])

    if config["screen"]["enabled"]:
        waveshare213.init_display()
        waveshare213.draw_display_booting()

    low_power_bytes = bytes([int(config["scd41"]["low_power"])])
    if config.get("history_size"):
        historic_co2_data = low_power_bytes + bytes(config["history_size"] * 2)

    last_run = utime.ticks_ms() / 1000
    screen_refresh_wait = 1
    celsius = None

    while True:
        # running GC regularly manually is recommended
        # https://docs.micropython.org/en/latest/reference/speed_python.html#controlling-gc
        gc.collect()
        debug_print("free mem:", gc.mem_free())

        debug_print("wlan:", wlan_enabled(), "bt:", bt_enabled())
        wlan.active(wlan_enabled())

        if use_bmp180:
            pressure_pa, elevation_m = await bmp180_task(bmp180, scd41)
            if "pressure" in log_files:
                # drop the first byte, always 0
                log_files["pressure"].write(
                    struct.pack(">I", int(pressure_pa * 10))[1:]
                )
        elif use_bmp280 and (celsius is not None):
            pressure_pa, elevation_m = await bmp280_task(bmp280, scd41, celsius)
            if "pressure" in log_files:
                # drop the first byte, always 0
                log_files["pressure"].write(
                    struct.pack(">I", int(pressure_pa * 10))[1:]
                )
        else:
            pressure_pa = elevation_m = None

        while not await scd41.get_data_ready_status():
            await appropriate_async_sleep(1)

        (
            measurement_status,
            co2,
            celsius,
            relative_humidity,
        ) = await scd41.read_measurement()

        if config.get("history_size"):
            historic_co2_data = (
                low_power_bytes
                + historic_co2_data[(config["history_size"] * -2) + 2 :]
                + struct.pack(">H", co2)
            )

        if measurement_status:
            if "co2" in log_files:
                log_files["co2"].write(struct.pack(">H", co2))
            if "c" in log_files:
                log_files["c"].write(struct.pack(">H", int(celsius * 100)))
            if "rh" in log_files:
                log_files["rh"].write(struct.pack(">H", int(relative_humidity * 100)))

            if config["bluetooth"]["enabled"]:
                co2_characteristic.write(
                    (
                        str(co2).encode()
                        if config["bluetooth"].get("co2_as_string", False)
                        else struct.pack("<H", co2)
                    ),
                    send_update=True,
                )
                temp_characteristic.write(
                    struct.pack("<H", int(celsius * 100)), send_update=True
                )
                rh_characteristic.write(
                    struct.pack("<I", int(relative_humidity * 100)), send_update=True
                )
                if config.get("history_size"):
                    co2_historic_characteristic.write(historic_co2_data)

            led_co2_trigger_value = config["led"][
                "co2_trigger_wlan" if wlan_enabled() else "co2_trigger"
            ]

            if led_co2_trigger_value != -1 and config["pins"].get("led"):
                led_pin.value(int(co2 >= led_co2_trigger_value))

            # Only refresh the screen every x cycles
            if config["screen"]["enabled"] and screen_refresh_wait == 0:
                waveshare213.draw_display(
                    co2,
                    celsius,
                    relative_humidity,
                    altitude=(
                        elevation_m
                        if config["screen"].get("show_altitude") and elevation_m
                        else None
                    ),
                )
                screen_refresh_wait = (
                    config["screen"]["refresh_rate_wlan"]
                    if wlan_enabled()
                    else config["screen"]["refresh_rate"]
                )
            elif config["screen"]["enabled"]:
                screen_refresh_wait -= 1

            if await ensure_wlan_connected(wlan):
                if config["webserver"]["enabled"]:
                    await set_webserver_status_data(
                        {
                            "co2_ppm": co2,
                            "temp_celsius": celsius,
                            "relative_humidity": relative_humidity,
                            "pressure_pa": pressure_pa,
                            "elevation_m": elevation_m,
                        }
                    )
                if config["influx"].get("enabled", False):
                    send_metrics_to_influx(co2, celsius, relative_humidity)

        total_sleep_time = 30 if config["scd41"]["low_power"] else 5
        current_ticks_s = utime.ticks_ms() / 1000
        sleep_duration = total_sleep_time - (current_ticks_s % total_sleep_time)

        # don't sleep if we've overshot our 5/30s
        if current_ticks_s - last_run > total_sleep_time:
            sleep_duration = 0

        last_run = utime.ticks_ms() / 1000
        debug_print("Sleeping for", sleep_duration, "seconds")

        await appropriate_async_sleep(sleep_duration)

        if config["bluetooth"]["enabled"]:
            config_changes = config_characteristic.read()
            if config_changes:
                await update_config(config_changes)


async def main():
    tasks = []
    if "cpu_frequency" in config:
        machine.freq(config["cpu_frequency"])
    debug_print("CPU frequency set to", machine.freq())

    tasks.append(uasyncio.create_task(sensor_task()))
    if config["bluetooth"]["enabled"]:
        tasks.append(uasyncio.create_task(bluetooth_task()))
        tasks.append(uasyncio.create_task(bt_complex_comms_task()))
    await uasyncio.gather(*tasks)


uasyncio.run(main())
