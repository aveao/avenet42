import urequests
from helpers import debug_print, config

INFLUX_WRITE_URL = f"{config['influx']['host']}/api/v2/write?bucket={config['influx']['bucket']}&u={config['influx']['username']}&p={config['influx']['password']}"


def send_metrics_to_influx(co2, temp, rh):
    try:
        res = urequests.post(
            INFLUX_WRITE_URL, data=f"{config['influx']['datapoint']} co2={co2},temp={temp},humidity={rh}"
        )
        debug_print("ureq status:", res.status_code)
        res.close()
    # broad exception handling my beloved, necessary as ECONNRESET can kill the code
    except Exception as e:
        debug_print("error while ureq:", e)
