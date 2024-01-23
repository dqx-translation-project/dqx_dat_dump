from pathlib import Path
import sys

# if your game data directory differs, update it here.
GAME_DATA_DIR = "C:/Program Files (x86)/SquareEnix/DRAGON QUEST X/Game/Content/Data"

PROJECT_ROOT = Path(__file__).parent.parent.as_posix()
GITHUB_URL = "https://github.com/dqx-translation-project/dqx_translations/archive/refs/heads/main.zip"

# current number of vanilla dats before any modifications.
ORIG_NUM_DATS = {
    "data00000000.win32.idx": 1,
    "data00010000.win32.idx": 7,
    "data00020000.win32.idx": 4,
    "data00030000.win32.idx": 1,
    "data00040000.win32.idx": 2,
    "data00080000.win32.idx": 1,
    "data00130000.win32.idx": 2,
    "data00160000.win32.idx": 1,
    "data00250000.win32.idx": 1,
}


def check_game_path(path=GAME_DATA_DIR):
    if not Path(path).is_dir():
        sys.exit(f"Did not find game directory at {GAME_DATA_DIR}. Please edit tools/globals.py and set a valid path.")
    return GAME_DATA_DIR


GAME_DATA_DIR = check_game_path(GAME_DATA_DIR)
