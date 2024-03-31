from machine import SoftSPI, Pin
import gc
import time
import comic_code_24
import comic_code_48
from helpers import debug_print, config, wlan_enabled, bt_enabled

CS_PIN = Pin(config["pins"]["screen_cs"], mode=Pin.OUT, value=1)
SCK_CLK_PIN = Pin(config["pins"]["screen_scl_clk"], mode=Pin.OUT)
DIN_MOSI_PIN = Pin(config["pins"]["screen_din_mosi"], mode=Pin.OUT)
BUSY_PIN = Pin(config["pins"]["screen_busy"], mode=Pin.IN)
DC_PIN = Pin(config["pins"]["screen_dc"], mode=Pin.OUT)

DUMMY_PIN = Pin(config["pins"]["screen_dummy"], mode=Pin.IN)

EPD_WIDTH = config["screen"]["width"]
EPD_HEIGHT = config["screen"]["height"]

spi = SoftSPI(
    baudrate=2000000,
    firstbit=SoftSPI.MSB,
    sck=SCK_CLK_PIN,
    mosi=DIN_MOSI_PIN,
    miso=DUMMY_PIN,
)


LINE_WIDTH = int(EPD_WIDTH / 8) if (EPD_WIDTH % 8 == 0) else int(EPD_WIDTH / 8 + 1)


gc.collect()
fbuf = [0xFF] * int(LINE_WIDTH * EPD_HEIGHT)


def wait_until_idle():
    while BUSY_PIN.value() != 0:
        time.sleep(0.1)


def spi_transfer(data: bytes):
    CS_PIN(0)
    spi.write(data)
    CS_PIN(1)


def send_command(command: int):
    DC_PIN(0)
    spi_transfer(bytes([command]))


def send_data(data: int):
    DC_PIN(1)
    spi_transfer(bytes([data]))


def display(frame_buf):
    send_command(0x24)
    for h in range(EPD_HEIGHT):
        for w in range(LINE_WIDTH):
            data = frame_buf[w + h * LINE_WIDTH]
            send_data(data)

    # DISPLAY REFRESH
    send_command(0x22)
    send_data(0xC7)
    send_command(0x20)
    wait_until_idle()
    debug_print("Display updated")


def send_lut_full_update_data(file_handle, byte_count):
    file_handle.seek(byte_count)
    send_data(file_handle.read(1)[0])


def init_display():
    lut_full_update_file = open("waveshare_lut_full_update.bin", "rb")
    wait_until_idle()
    send_command(0x12)  # soft reset
    wait_until_idle()

    send_command(0x74)  # set analog block control
    send_data(0x54)
    send_command(0x7E)  # set digital block control
    send_data(0x3B)

    send_command(0x01)  # Driver output control
    send_data(0xF9)
    send_data(0x00)
    send_data(0x00)

    send_command(0x11)  # data entry mode
    send_data(0x01)

    send_command(0x44)  # set Ram-X address start/end position
    send_data(0x00)
    send_data(0x0F)  # 0x0C-->(15+1)*8=128

    send_command(0x45)  # set Ram-Y address start/end position
    send_data(0xF9)  # 0xF9-->(249+1)=250
    send_data(0x00)
    send_data(0x00)
    send_data(0x00)

    send_command(0x3C)  # BorderWavefrom
    send_data(0x03)

    send_command(0x2C)  # VCOM Voltage
    send_data(0x55)

    send_command(0x03)
    send_lut_full_update_data(lut_full_update_file, 70)

    send_command(0x04)
    send_lut_full_update_data(lut_full_update_file, 71)
    send_lut_full_update_data(lut_full_update_file, 72)
    send_lut_full_update_data(lut_full_update_file, 73)

    send_command(0x3A)  # Dummy Line
    send_lut_full_update_data(lut_full_update_file, 74)
    send_command(0x3B)  # Gate time
    send_lut_full_update_data(lut_full_update_file, 75)

    send_command(0x32)
    for i in range(70):
        send_lut_full_update_data(lut_full_update_file, i)

    send_command(0x4E)  # set RAM x address count to 0
    send_data(0x00)
    send_command(0x4F)  # set RAM y address count to 0X127
    send_data(0xF9)
    send_data(0x00)
    wait_until_idle()
    lut_full_update_file.close()
    debug_print("Display initialized")


def fbuf_pixel(x, y, color=1):
    global fbuf
    newx = EPD_WIDTH - (x - 1)
    if color == 1:
        fbuf[int(newx / 8) + y * LINE_WIDTH] &= ~(0x80 >> (newx % 8))
    else:
        fbuf[int(newx / 8) + y * LINE_WIDTH] |= 0x80 >> (newx % 8)


def fbuf_horizontal_line(xoff, yoff, width, color=1):
    global fbuf
    full_color = 0x00 if color else 0xFF

    # first pixels before 8-blocks
    for x in range(8 - (xoff % 8)):
        fbuf_pixel(xoff + x, yoff, color)

    # the in-between 8-blocks
    for x in range(width // 8):
        newx = EPD_WIDTH - (xoff + (xoff % 8) + (x * 8))
        fbuf[(newx // 8) + yoff * LINE_WIDTH] = full_color

    # last pixels after 8-blocks
    for x in range((width % 8) + 1):
        fbuf_pixel(xoff + (width - x), yoff, color)


def fbuf_rect(xoff, yoff, width, height, color=1):
    for y in range(height):
        fbuf_horizontal_line(xoff, y + yoff, width, color)
    gc.collect()


def draw_character(
    xoff,
    yoff,
    character,
    font,
    font_file,
    invert=False,
    transparent_color=-1,
    rot=0,
    scale=1,
):
    if character not in font.chars:
        if character != " ":
            debug_print(f"Cannot draw character {character} as it's not in font")
        return

    char_index = font.chars.index(character)
    char_width = int(font.width / 8)

    for y in range(font.height):
        bit_offset = int(char_width * char_index + (len(font.chars) * char_width * y))
        for x in range(char_width):
            font_file.seek(bit_offset + x)
            font_x_byte = font_file.read(1)[0]
            for xi in range(8):
                pixel_bit = int((font_x_byte & (2**xi)) == (2**xi))
                # pixel_bit = font_x_byte & (2 ** xi)

                if not invert:
                    pixel_bit = int(not bool(pixel_bit))

                if pixel_bit == transparent_color:
                    continue

                newx = (x * 8) + xi
                newy = y

                if rot == 1:
                    newx = font.height - y
                    newy = (x * 8) + xi

                pixels = [(xoff + newx, yoff + newy, pixel_bit)]

                if scale != 1:
                    pixels = []
                    newx *= scale
                    newy *= scale
                    for scalex in range(scale):
                        for scaley in range(scale):
                            pixels.append(
                                (
                                    xoff + newx + scalex,
                                    yoff + newy + scaley,
                                    pixel_bit,
                                )
                            )

                for pixel in pixels:
                    fbuf_pixel(*pixel)
    gc.collect()


def draw_text(
    text,
    xoff,
    yoff,
    font,
    invert=False,
    offset_for_length=1,
    transparent_color=-1,
    rot=0,
    scale=1,
):
    char_count = 0
    font_file = open(font.bin_filename, "rb")
    if offset_for_length:
        offset_amount = font.width * ((len(text) / 2) * offset_for_length) * scale
        if rot == 0:
            xoff -= offset_amount
        elif rot == 1:
            yoff -= offset_amount
    for character in text:
        extra_space = char_count * font.width * scale
        extra_xoff = extra_yoff = 0
        if rot == 0:
            extra_xoff = extra_space
        elif rot == 1:
            extra_yoff = extra_space
        draw_character(
            int(xoff + extra_xoff),
            int(yoff + extra_yoff),
            character,
            font,
            font_file,
            invert=invert,
            transparent_color=transparent_color,
            rot=rot,
            scale=scale,
        )
        char_count += 1
    font_file.close()


def clean_fbuf():
    global fbuf
    for i in range(int(LINE_WIDTH * EPD_HEIGHT)):
        fbuf[i] = 0xFF


def draw_display(co2_ppm, celsius, rh):
    clean_fbuf()
    gc.collect()
    top_bar_height = int(EPD_WIDTH / 3)

    fbuf_rect(
        int(EPD_WIDTH - top_bar_height),
        0,
        top_bar_height,
        EPD_HEIGHT,
        1,
    )

    draw_text(
        "{:.1f}°C".format(celsius),
        EPD_WIDTH - comic_code_24.height - 2,
        5,
        comic_code_24,
        rot=1,
        invert=True,
        transparent_color=1,
        offset_for_length=False,
    )

    co2_text = "{}".format(co2_ppm)
    co2_offset = int(comic_code_48.width * (len(co2_text) / 2))
    # 1.5 for len("ppd") / 2
    ppd_offset = int(comic_code_24.width * 1.5)
    draw_text(
        co2_text,
        int(EPD_WIDTH / 3) - comic_code_24.height,
        int(EPD_HEIGHT / 2) - ppd_offset,
        comic_code_48,
        transparent_color=0,
        rot=1,
    )
    draw_text(
        "ppm",
        int(EPD_WIDTH / 3) - comic_code_24.height + 12,
        int(EPD_HEIGHT / 2) + co2_offset,
        comic_code_24,
        transparent_color=0,
        rot=1,
    )

    draw_text(
        "{:.0f}% RH".format(rh),
        EPD_WIDTH - comic_code_24.height - 2,
        EPD_HEIGHT - 5,
        comic_code_24,
        rot=1,
        invert=True,
        transparent_color=1,
        offset_for_length=2,
    )

    if bt_enabled():
        draw_text(
            "Є",
            0,
            0,
            comic_code_24,
            rot=1,
            transparent_color=0,
            offset_for_length=False,
        )
    if wlan_enabled():
        draw_text(
            "$",
            comic_code_24.height,
            0,
            comic_code_24,
            rot=1,
            transparent_color=0,
            offset_for_length=False,
        )

    if config["screen"]["debug"]:
        draw_text(
            "{}".format(gc.mem_free()),
            0,
            EPD_HEIGHT - comic_code_24.height,
            comic_code_24,
            transparent_color=0,
            offset_for_length=False,
        )

    display(fbuf)


if __name__ == "__main__":
    init_display()
    draw_display(6969, 10.42, 50.69)
    draw_display(420, 10.42, 50.69)
