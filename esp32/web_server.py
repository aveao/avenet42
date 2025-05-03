import uasyncio
import network
import json
from helpers import debug_print, config, ensure_wlan_connected

WEBSERVER_RUNNING = False
STATUS_DATA = {}
STATUS_RESPONSE_CACHES = {
    "json": '{"co2_ppm": null, "temp_celsius": null, "relative_humidity": null, "pressure_pa": null, "elevation_m": null}'
}

STATUS_CODE_TEXT = {200: "OK", 404: "Not Found"}


def generate_status_prometheus(status: dict):
    """Generate prometheus text-based exposition file."""
    body = []
    for key, value in status.items():
        # do not report non-existent values
        if value is None:
            continue

        body += [f"# TYPE {key} gauge", f"{key} {value}", ""]

    return "\n".join(body)


def generate_status_json(status: dict):
    """Generate status json file."""
    return json.dumps(STATUS_DATA)


def generate_status_body(status_type: str, status: dict):
    """Generate a status body of a given type, doing caching in the process."""
    global STATUS_RESPONSE_CACHES

    if status_type not in STATUS_RESPONSE_CACHES:
        debug_print("webserver cache miss for:", status_type)

        if status_type == "prometheus":
            STATUS_RESPONSE_CACHES[status_type] = generate_status_prometheus(status)
        elif status_type == "json":
            STATUS_RESPONSE_CACHES[status_type] = generate_status_json(status)

    return STATUS_RESPONSE_CACHES[status_type]


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
    global STATUS_DATA
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
                200,
                generate_status_body("json", STATUS_DATA),
                content_type="application/json",
            )
        elif req_header.startswith(b"GET /prometheus"):
            resp = generate_response(
                200,
                generate_status_body("prometheus", STATUS_DATA),
                content_type="text/plain; version=0.0.4",
            )
        elif req_header.startswith(b"GET / "):
            resp = generate_response(
                200,
                (
                    "<head><title>avenet42</title></head>\n"
                    'hi! this is an <a href="https://github.com/aveao/avenet42">avenet42</a>.<br>\n'
                    'try <a href="/status.json">/status.json</a> or <a href="/prometheus">/prometheus</a>.'
                ),
            )
        else:
            resp = generate_response(
                404,
                (
                    "<head><title>avenet42</title></head>\n"
                    '<head><meta http-equiv="refresh" content="5; url=/"></head>\n'
                    "404 :("
                ),
            )

        await writer.awrite(resp)
        await writer.drain()
    except Exception as e:
        debug_print("HTTP error:", str(e))
    finally:
        reader.close()
        writer.close()
        await reader.wait_closed()
        await writer.wait_closed()


async def set_webserver_status_data(data: dict):
    global STATUS_DATA
    global STATUS_RESPONSE_CACHES
    global WEBSERVER_RUNNING

    if not WEBSERVER_RUNNING:
        await setup_webserver()

    STATUS_DATA = data
    # wipe the response caches
    STATUS_RESPONSE_CACHES = {}


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
