import sys
import struct

with open(sys.argv[1], "rb") as f:
    log_file = f.read()


DATA_SIZE_TO_STRUCT = {2: ">H", 3: ">I"}
DATA_FORMAT_ID = {
    0x00: {"name": "CO2", "suffix": "ppm", "size": 2, "divide": 1},
    0x01: {"name": "Temperature", "suffix": "C", "size": 2, "divide": 100},
    0x02: {"name": "Relative Humidity", "suffix": "%", "size": 2, "divide": 100},
    0x03: {"name": "Pressure", "suffix": "Pa", "size": 3, "divide": 10},
}

parsed_data = ""

sessions = log_file.split(b"AN42")

session_counter = 0
for session in sessions:
    if not session:
        continue
    session_low_power = False
    datapoint_counter = 0
    session_counter += 1
    data_format = DATA_FORMAT_ID[session[0]]
    data_size = data_format["size"]
    session_low_power = bool(session[1])

    parsed_data += f"Session {session_counter} ({data_format['name']})\n"

    for i in range(1, int(len(session) / data_size)):
        rel_bytes = session[i * data_size : (i + 1) * data_size]
        if data_size == 3:
            rel_bytes = bytes(1) + rel_bytes
        datapoint = (
            struct.unpack(DATA_SIZE_TO_STRUCT[data_size], rel_bytes)[0]
            / data_format["divide"]
        )
        passed_time = datapoint_counter * (30 if session_low_power else 5)
        parsed_data += f"+{passed_time}: {datapoint}{data_format['suffix']}\n"
        datapoint_counter += 1

parsed_data = parsed_data.strip()

print(parsed_data)
