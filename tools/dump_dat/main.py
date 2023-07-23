import os
import sys
sys.path.append("../../")  # hack to use tools
from tools.lib.datfile import DatEntry
from tools.lib.extensions import EXTENSIONS
from tools.lib.idxfile import IdxFile
from tools.lib.rpsfile import RpsFile

# example: C:\Program Files (x86)\SquareEnix\DRAGON QUEST X\Game\Content\Data\data00000000.win32.idx
idx_file = "C:\\Program Files (x86)\\SquareEnix\\DRAGON QUEST X\\Game\\Content\\Data\\data00000000.win32.idx"

def unpack_idx():
    idx = IdxFile(idx_file)
    num_files = idx.records['count']
    print(f"{num_files} rows found.")

    for record in idx.records["records"]:
        dat_offset = record["dat_offset"]
        fq_dat_file = os.path.splitext(idx_file)[0] + ".dat" + record["dat_num"]
        dat_file_name = fq_dat_file.split("\\")[-1]
        filename = record["filename"]

        data = DatEntry(dat_file=fq_dat_file, offset=dat_offset)
        file = data.data()
        if file:
            ext = file[0:7]
            if ext in EXTENSIONS:
                filename = filename + EXTENSIONS[ext]
            os.makedirs(f"out/{dat_file_name}", exist_ok=True)
            with open(f"out/{dat_file_name}/{filename}", "wb") as f:
                f.write(file)

            # if filename.split(".")[-1] == "rps":
            #     rps = RpsFile(f"{os.getcwd()}\\out\\{dat_file_name}\\{filename}")
            #     rps.dump()


if __name__ == "__main__":
    unpack_idx()
