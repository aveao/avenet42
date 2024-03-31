import uasyncio
import network
from helpers import debug_print, config, ensure_wlan_connected

WEBSERVER_RUNNING = False
STATUS_JSON_DATA = '{"co2_ppm": null, "temp_celcius": null, "relative_humidity": null}'

STATUS_CODE_TEXT = {200: "OK", 404: "Not Found"}


def generate_response(
    status_code: int, response_body: str, content_type: str = "text/html"
) -> str:
    resp = "".join(
        [
            f"HTTP/1.1 {status_code} {STATUS_CODE_TEXT.get(status_code, '')}\r\n",
            "Connection: close\r\n",
            f"Content-Length: {len(response_body)}\r\n",
            f"Content-Type: {content_type}\r\n\r\n",
            response_body,
        ]
    )
    return resp


async def server_callback(reader: uasyncio.StreamReader, writer: uasyncio.StreamWriter):
    global STATUS_JSON_DATA
    try:
        try:
            req_header = await uasyncio.wait_for(
                reader.readline(), config["webserver"]["conn_timeout"]
            )
        except uasyncio.TimeoutError:
            req_header = b""

        debug_print("serving:", req_header)

        if req_header == b"":
            raise OSError

        if req_header.startswith(b"GET /status.json"):
            resp = generate_response(
                200, STATUS_JSON_DATA, content_type="application/json"
            )
        elif req_header.startswith(b"GET /"):
            resp = generate_response(200, 'try <a href="/status.json">/status.json</a>')
        else:
            resp = generate_response(404, "404 :(")

        await writer.awrite(resp)
        await writer.drain()
    except Exception as e:
        debug_print("HTTP error:", str(e))
    finally:
        reader.close()
        writer.close()
        await reader.wait_closed()
        await writer.wait_closed()


async def set_webserver_status_json(json_data: str):
    global STATUS_JSON_DATA
    global WEBSERVER_RUNNING

    if not WEBSERVER_RUNNING:
        await setup_webserver()

    STATUS_JSON_DATA = json_data


async def setup_webserver():
    global WEBSERVER_RUNNING
    if WEBSERVER_RUNNING:
        return

    await uasyncio.start_server(server_callback, "0.0.0.0", config["webserver"]["port"])
    debug_print("Initialized webserver")

    WEBSERVER_RUNNING = True


async def _run():
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    await ensure_wlan_connected(wlan)
    await setup_webserver()
    while True:
        await uasyncio.sleep(10)


if __name__ == "__main__":
    uasyncio.run(_run())
