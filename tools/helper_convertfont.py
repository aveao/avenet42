from PIL import Image

# note: font width needs to be 8-aligned

input_name = "font_small.png"
output_name = "comic_code_24.py"
output_name_bin = "comic_code_24.bin"
font_width = 16
font_height = 36
font_chars = "CRHpm1234567890.°%$Є"
# input_name = "font_large.png"
# output_name = "comic_code_48.py"
# output_name_bin = "comic_code_48.bin"
# font_width = 32
# font_height = 72
# font_chars = "1234567890"


def convert_image_to_bits(image_path):
    # partly generated with chatgpt :skull:
    image = Image.open(image_path)
    image = image.convert('1')

    pixel_data = image.load()

    w, h = image.size

    bits_array = []

    for y in range(h):
        for x in range(w):
            pixel = pixel_data[x, y]
            bit = 1 if pixel == 255 else 0
            bits_array.append(bit)

    return bits_array


def convert_bits_to_bytes(bits_array):
    bytes_array = []
    new_byte = 0
    bit_count = 0
    for bit in bits_array:
        if bit:
            new_byte |= 2 ** (bit_count % 8)
        bit_count += 1
        if (bit_count % 8) == 0:
            bytes_array.append(new_byte)
            new_byte = 0

    return bytes_array


def bits_get_character(bits_array, character):
    if character not in font_chars:
        return

    char_bits = []

    char_index = font_chars.index(character)
    char_width = font_width

    for y in range(font_height):
        bit_offset = int(char_width * char_index + (len(font_chars) * char_width * y))
        for x in range(char_width):
            pixel_bit = bits_array[bit_offset + x]
            char_bits.append(pixel_bit)

    return char_bits


def bytes_get_character(bytes_array, character):
    if character not in font_chars:
        return

    char_bits = []

    char_index = font_chars.index(character)
    char_width = int(font_width / 8)

    for y in range(font_height):
        bit_offset = int(char_width * char_index + (len(font_chars) * char_width * y))
        for x in range(char_width):
            for xi in range(8):
                pixel_bit = int((int(bytes_array[bit_offset + x]) & (2 ** xi)) == (2 ** xi))
                char_bits.append(pixel_bit)

    return char_bits


bits_array = convert_image_to_bits(input_name)

bytes_array = convert_bits_to_bytes(bits_array)

# verify the bit/byte conversion
for font_char in font_chars:
    assert bits_get_character(bits_array, font_char) == bytes_get_character(bytes_array, font_char)


with open(output_name, "w") as f:
    f.write(f"width = {font_width}\n")
    f.write(f"height = {font_height}\n")
    f.write(f"chars = \"{font_chars}\"\n")
    f.write(f"bin_filename = \"{output_name_bin}\"\n")


with open(output_name_bin, "wb") as f:
    f.write(bytes(bytes_array))
