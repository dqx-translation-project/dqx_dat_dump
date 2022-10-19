# dqx_dat_dump

This project dumps the game dat files for DQX.

Unfortunately, all of the filenames and filepaths are hashed in the index table and I don't know where/how to obtain their true names, so the filenames will dump as their literal hex'd <filename><folder_name> values from the index table. On the plus side, this makes it easy to figure out which index entry is looking at which file, which could be useful for repacking.

The clarity project uses this to dump the ETP (dialog) files out of the game, so this script may evolve over time for its use, but it could be used for other files too.

At this time, this tool does not repack anything, just unpack.

# idx and dat* files

This game uses both an ".idx" and ".dat*" file type. "idx" files are "Index" files and they are a mapping of where the data exists in the ".dat*" or "Data" files.

We care about the Index files and that is what this script uses to figure out where the data is packed.

# How to use

- Install a recent version of Python (I used 3.9.7 for this). As I've used all core Python libraries, no additional modules need to be installed
- Clone this repository down, or download the zip of the project and extract it
- Open `main.py` in a text editor
- Update the `idx_file` variable at the top of the file and provide it the full path to an idx file
- Save it
- Open a command line/terminal/Powershell window
- Type `python main.py` and wait for the dump to complete. Some of the dat files can take several minutes to complete
- Inside the same directory where you ran the command, you will see an `out` directory with the files inside

This tool does not modify the original game files; it only reads them and outputs their contents to a separate directory.

# General contents of each dat

```
data00000000.idx -> astb, etp, mdlb, sedbres files (most of what we care about is in here)
data00010000.idx -> sedbsdb, looks like texture files
data00020000.idx -> all sedbres files
data00030000.idx -> all efx files
data00040000.idx -> sedbdsb, sedbscb files
data00080000.idx -> mostly dds and efx files
data00130000.idx -> sedbsscf (audio) files
data00160000.idx -> astb, mdlb, old xml files, etp files. everything in here looks like Wii files
data00250000.idx -> xml files, looks like automated testing scripts

All of the Game\Content\Ex?000 dats have sedbsscf (audio) tracks in them for their respective expansion.
```

This list is not conclusive, but just a quick summary from a few minutes of looking around.

Some files are encrypted and I don't have a way to view them as of now. Off the top of my head, some of the ETP files inside of the sedbres files are, as well as all of the PNG files.

My guess is that the encryption looks to be something specific to the Crystal Tools engine, given the "CRY" header that's prepended to some of the the files before the data.

# File extension explanations

I'm running off the assumption that "SEDB***" stands for "Square Enix Database <something>".

- `astb`: No idea
- `etp`: Static dialog files for various items in game (menus, cutscenes, vendors, etc.)
- `mdlb`: No idea
- `sedbres`: These are container files that contain more files inside of them. They must be unpacked to get to the contents inside of these files. The resources inside of each file can be seen at the bottom of each file
- `efx`: Assuming effect/animation files?
- `dds`: Images
- `sedbsscf`: Square Enix audio file. You can play these in [vgmstream](https://github.com/vgmstream/vgmstream). I believe vgmstream can also re-encode them to a different audio format so they'll play natively in your player of choice
- `sedbsdb`: Texture files

This list is not conclusive. More filetypes can be found inside of the `sedbres` files, but I have not extensively looked around.

Most of the files won't natively open with what you have installed (and are not meant to be). Some need specialized tools or just may be data files the game uses. Opening them in a hex editor that supports UTF-8 encoding would be recommended to get a better idea.

# Acknowledgements

IonCannon for their work in reversing these files. FFXIV shares a ton of similarities to DQX on the backend, so I was able to use this work to write most of the unpacking:
- https://bitbucket.org/Ioncannon/ffxiv-explorer/src/develop/research/sqpack%20index%20files.txt
- https://bitbucket.org/Ioncannon/ffxiv-explorer/src/develop/research/sqpack%20dat%20files.txt

NotAdam's Lumina project for helping me understand how dats spanned across multiple files are evaluated:
- https://github.com/NotAdam/Lumina/blob/9cf00f703c1a9eb120d3ecf11a5287e3b077f5ce/src/Lumina/Data/Structs/SqPackIndexHeader.cs#L31

@Andoryuuta for reversing how the RPS info struct table is put together to calculate the filenames/extensions.
- https://gist.github.com/Andoryuuta/cab93882cd616ea519522b21d663a65f#file-sedbres_parser-py-L27
