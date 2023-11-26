from pathlib import Path
import sys
sys.path.append("../../")  # hack to use tools
from tools.py_globals import GAME_DATA_DIR
from tools.lib.extensions import EXTENSIONS
from tools.lib.idxfile import IdxFile
from tools.lib.datentry import DatEntry


# update to the idx file you want to dump
IDX_FILE = "data00000000.win32.idx"


def unpack_idx():
    idx = IdxFile(f"{GAME_DATA_DIR}/{IDX_FILE}")
    print(f"{len(idx.records)} rows found.")

    for record in idx.records:
        dat_file = Path(f"{GAME_DATA_DIR}/{record['dat_file']}")
        dat = DatEntry(dat_file=dat_file, offset=record['dat_offset'])
        file_data = dat.data

        if file_data:
            if record['filename'] and record['folder']:
                filename = f"{record['folder']}/{record['filename']}"
            else:
                ext = file_data[0:7]
                if ext in EXTENSIONS:
                    filename = record['hashed_filename'] + EXTENSIONS[ext]
                else:
                    filename = record['hashed_filename']

            to_write = '/'.join(['out', record['dat_file'], filename])
            Path(to_write).parent.mkdir(parents=True, exist_ok=True)

            with open(to_write, 'wb') as f:
                f.write(file_data)


if __name__ == '__main__':
    unpack_idx()
