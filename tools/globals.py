import os
import sys

GAME_DATA_DIR = "C:/Program Files (x86)/SquareEnix/DRAGON QUEST X/Game/Content/Data"
GITHUB_URL = "https://github.com/dqx-translation-project/dqx_translations/archive/refs/heads/main.zip"


def check_game_path(path=GAME_DATA_DIR):
    if not os.path.exists(path):
        sys.exit(f"Did not find game directory at {GAME_DATA_DIR}. Please edit tools/globals.py and set a valid path.")
    return GAME_DATA_DIR

GAME_DATA_DIR = check_game_path(GAME_DATA_DIR)
