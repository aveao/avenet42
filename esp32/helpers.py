from machine import I2C, lightsleep, Pin
import json
import utime
import machine
import network
import uasyncio
import ubinascii
import bluetooth


with open("config.json") as f:
    config = json.load(f)


wlan_pin = Pin(config["pins"]["wlan"], Pin.IN, Pin.PULL_UP)
bt_pin = Pin(config["pins"]["bt"], Pin.IN, Pin.PULL_UP)


DATA_FORMAT_ID = {"co2": 0, "c": 1, "rh": 2, "pressure": 3}


# org.bluetooth.service.environmental_sensing
_ENV_SENSE_UUID = bluetooth.UUID(0x181A)
# org.bluetooth.characteristic.co2_concentration
_ENV_SENSE_CO2_UUID = bluetooth.UUID(0x2B8C)
# org.bluetooth.characteristic.temperature
_ENV_SENSE_TEMP_UUID = bluetooth.UUID(0x2A6E)
# org.bluetooth.characteristic.humidity
_ENV_SENSE_RH_UUID = bluetooth.UUID(0x2A6F)
# org.bluetooth.characteristic.elevation
_ENV_SENSE_ELEVATION_UUID = bluetooth.UUID(0x2A6C)
# org.bluetooth.characteristic.pressure
_ENV_SENSE_PRESSURE_UUID = bluetooth.UUID(0x2A6D)
# co2 historic
_ENV_SENSE_CO2_HISTORIC_UUID = bluetooth.UUID(0x6969)
# config
_ENV_CONFIG_UUID = bluetooth.UUID(0x6970)
# complex comms
_ENV_COMPLEX_COMMS_UUID = bluetooth.UUID(0x6971)
# org.bluetooth.characteristic.gap.appearance.xml
_ADV_APPEARANCE_GENERIC_THERMOMETER = 0x0300


async def update_config(new_config_bytes: bytes):
    global config

    try:
        new_config = json.loads(new_config_bytes.decode())
        config.update(new_config)
    except Exception as e:
        debug_print("caught error while trying to update config:", e, "with config", new_config_bytes)
        return

    with open("config.json", "w") as f:
        f.write(json.dumps(config))

    # some time to ensure it is written
    await uasyncio.sleep(1)

    # reset to ensure config applies everywhere
    machine.reset()


async def replace_config(new_config_bytes: bytes):
    with open("config.json", "wb") as f:
        f.write(json.dumps(new_config_bytes))

    # some time to ensure it is written
    await uasyncio.sleep(1)

    # reset to ensure config applies everywhere
    machine.reset()


def wlan_enabled() -> bool:
    return bool(wlan_pin.value())


def bt_enabled() -> bool:
    return bool(bt_pin.value())


def rf_used() -> bool:
    return wlan_enabled() or bt_enabled()


def appropriate_sleep(duration_s: int):
    if config["lightsleep"] and not rf_used():
        lightsleep(duration_s * 1000)
    else:
        utime.sleep(duration_s)


async def appropriate_async_sleep(duration_s: int):
    if config["lightsleep"] and not rf_used():
        lightsleep(duration_s * 1000)
    else:
        await uasyncio.sleep(duration_s)


def debug_print(*args, log_level=1):
    if log_level > config["debug"]:
        return
    print(*args)


async def ensure_wlan_connected(wlan: network.WLAN) -> bool:
    try:
        while not wlan.isconnected():
            # If WLAN pin is switched off at this point, stop attempting
            if not wlan_enabled():
                return False

            wlan.connect(config["wlan"]["ssid"], config["wlan"]["password"])
            await appropriate_async_sleep(config["wlan"]["connection_wait_s"])
        return True
    except Exception as e:
        debug_print("Handled wifi error:", e)
        return False


async def _write_to_i2c(
    i2c_instance: I2C,
    command: bytes,
    i2c_device: int = 0x62,
    read_bytes: int = 0,
    command_wait_s: int = 0.001,
):
    debug_print(">", i2c_device, ubinascii.hexlify(command).decode(), log_level=2)
    i2c_instance.writeto(i2c_device, command)
    await uasyncio.sleep(command_wait_s)
    if read_bytes:
        try:
            read_data = i2c_instance.readfrom(i2c_device, read_bytes)
            debug_print(
                "<", i2c_device, ubinascii.hexlify(read_data).decode(), log_level=2
            )
            return read_data
        except OSError as e:
            debug_print("Handled read error:", e, "on command", command)
