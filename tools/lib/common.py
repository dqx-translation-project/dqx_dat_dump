from binascii import hexlify
import csv
import os
from struct import unpack
import sqlite3


def write_file(path: str, data):
    with open(path, "wb") as game_file:
        game_file.write(data)


def write_hashed_filename(hashed_filename: str, filename="", hex="", dat_file="", hex_dict="lookup.csv") -> dict:
    """
    Writes the hashed filename to lookup.csv.
    :param hashed_filename: Name of the hashed filename.
    :param filename: (Optional) Name of the friendly filename.
    :param hex: (Optional) First 64 bytes of the hex string of the INDX header of the file.
    """
    if type(hex) is bytes:
        hex = split_hex(hexlify(hex).decode())

    # read original data in first
    orig_data = []
    with open(hex_dict, "r") as file:
        reader = csv.reader(file)
        for row in reader:
            orig_data.append(row)
    count = 0
    for row in orig_data:
        if row[2] == filename:
            orig_data[count][0] = hashed_filename
            orig_data[count][1] = dat_file
            found = True
            break
        count += 1
        found = False
    if not found:
        orig_data.append([hashed_filename, dat_file, filename, hex])

    # write modified data
    with open(hex_dict, "w", newline="") as file:
        writer = csv.writer(file)
        writer.writerows(orig_data)


def read_le(byte_str: bytes):
    return unpack("<i", byte_str)[0]


def split_hex(hex_str: str):
    """Split hex string into spaces."""
    spaced_str = " ".join(hex_str[i : i + 2] for i in range(0, len(hex_str), 2))
    return spaced_str.upper()


def get_filename(hex, filename="", hashed_filename="", hex_dict="lookup.csv"):
    """
    Search the lookup.csv file for a record. Can supply either filename, hex string or hashed_filename.
    :param filename: Name of the friendly filename.
    :param hex: First 64 bytes of the hex string of the INDX header of the file.
    :param hashed_filename: Name of the hashed filename.
    :returns: List of the found csv entry in [hashed_filename, filename, hex] format.
    """
    if hex:
        if type(hex) is bytes:
            hex = split_hex(hexlify(hex).decode())
    with open(hex_dict, encoding="utf-8") as file:
        reader = csv.reader(file)
        for row in reader:
            if hashed_filename:
                if row[0] == hashed_filename:
                    return row
            if filename:
                if row[2] == filename:
                    return row
            if hex:
                if row[3] == hex:
                    return row
        return False


def sqlite_read(query):
    escaped_text = query.replace("'", "''")

    try:
        db_file = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "filedb.db"))
        conn = sqlite3.connect(db_file)
        cursor = conn.cursor()
        selectQuery = query
        cursor.execute(selectQuery)
        results = cursor.fetchone()

        if results is not None:
            return results[0].replace("''", "'")
        else:
            return None

    except sqlite3.Error as e:
        raise Exception(e)
    finally:
        if conn:
            conn.close()


def get_file_by_hex(hex):
    if type(hex) is bytes:
        hex = split_hex(hexlify(hex).decode())
    else:
        hex = split_hex(hex)

    return sqlite_read(f"SELECT friendly_name FROM files WHERE hex_string = '{hex}'")
