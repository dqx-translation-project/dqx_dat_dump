# .etp

Research by Serany (@jmctune on Github).

ETP files store Japanese strings that the game uses to render things on-screen (menus, cutscenes, items, etc).

These files come in three different varieties (that I'll call v0/v2, v1 and v4).

## Sections:

Think of each section interpreted as an XML file, where there's a tag (section), the contents of the tag (data) and a closing tag ("FOOT" in this case).

All values are read in little endian (LE) unless otherwise noted.

### EVTX (pertains to all file versions)

```
0x000: Signature                4c;     "EVTX"
0x004: Header length            Int32;
0x008: Size of EVTX contents    Int32;  Size of data between "EVTX" and "FOOT"
0x00c: Child tag flag           Short;  "01" if the section has additional sections
                                        within it or "00" if it starts and ends with no
                                        additional sections within.
                                        EVTX flags are always b"\x01\x00".
0x00e: File version             Short;  b"\x00\x00", b"\x00\x01", b"\x00\x02" or b"\x00\x04".
                                        Indicates the type of ETP file this is.
```

### CMNH (Common Header?)

Common amongst all file versions:

```
0x000: Signature                4c;     "CMNH"
0x004: Header length            Int32;
0x008: Unknown                  Int32;  Is seen as b"\x10\x00\x00\x00" across all files.
0x00c: Child tag flag           Short;  CMNH flags are always b"\x00\x00" as this does not contain children.
0x00e: Unknown                  Short;
0x010: Unknown                  Int32;  Always seems to be "b\x64\x00\x00\x00"
0x014: Num. of INDX entries     Int32;  This number is absolute in v0/v2 files.
                                        In v1/v4 files, multiply by 2.
0x018: Unknown                  Int32;
0x01c: Unknown                  Int32;
0x020: "FOOT"                   4c;
0x024: "FOOT" length            Int32;  Always b"\x10\x00\x00\x00"
0x028: Padding                  8x;
```

### BLJA (BL -- Japanese?)

Common amongst all file versions:

```
0x000: Signature                4c;     "BLJA"
0x004: Header length            Int32;
0x008: Size of BLJA contents    Int32;  Size of data between "BLJA" and "FOOT"
0x00c: Child tag flag           Short;  BLJA flags are always b"\x01\x00"
0x00e: Unknown                  Short;  Always b"\x00\x00"
```

### INDX

Parts of this table are common, while others are custom to file versions.

```
0x000: Signature                4c;     "INDX"
0x004: Header length            Int32;  Always b"\x10\x00\x00\x00"
0x008: Size of INDX contents    Int32;  Size of data between "INDX" and "FOOT"
0x00c: Child tag flag           Short;  INDX flags are always b"\x00\x00"
0x00e: Unknown                  Short;  Always b"\x00\x00"
```

See differences between files based on version you're looking at.

Note that all versions are padded out with "00" for 16 byte alignment.

#### v0 + v2

Index entries contain a string identifer and an offset into the TEXT section. Each entry is 8 bytes in size.

Read them like so until all entries have been exhausted:

```
0x000: String id                Int32;
0x004: TEXT offset              Int32;  Absolute offset inside of the TEXT section.
```


#### v1

Index entries do not contain string identifiers in their INDX section, just offsets to the TEXT section. 

Entries are read as unsigned shorts initially. If there are more entries than allows in an unsigned short range (65535), the entries are then immediately transitioned to be read as unsigned ints. If either the unsigned short table is not 4 byte aligned when it's finished, bytes "CD AB" are used to finish the table, along with "00" padding until the file is 16 byte aligned.

```
0x000: # of string ids          Short;  Always b"\x00\x00" in this file version.
0x002: # of ushort offsets      Short;  If there is a uint table, those are not included in this count.
0x004: Padding?                 Int32;  Always b"\x00\x00\x00\x00"
0x008: Padding?                 Int32;  Always b"\x00\x00\x00\x00"
0x00c: Unknown                  Int32;  Always b"\x14\x00\x00\x00"
0x010: Size of contents         Int32;  Size of beginning of INDX to end of ushort table. If there are uints in this
                                        table, they are not included in the size. If the table ends with a "CD AB" byte
                                        for 4 byte alignment, these bytes are included.
```

From here, read the offsets initially as ushorts to look up in the TEXT table. ((offset * 2) + 1) will map you to the correct location. If you reach the end of the ushort table and there are still offsets remaining, read them as uints until the end of the table.

#### v4

Index entries have both a string identifier section and an offset section, with the string table listed first, then offsets. Basically, similar to v1 files, but there is now a string id table to consider.

Otherwise, the same rules apply as the v1 files.

```
0x000: # of string ids          Short;
0x002: # of ushort offsets      Short;
0x004: Unknown                  Int32;  Always b"\x14\x00\x00\x00
0x008: Unknown                  Int32;  Unknown, but looks like a count of something
0x00c: Unknown                  Int32;  Unknown, but is always the same value as the previous 4 bytes
0x010: Size of contents         Int32;  Size of beginning of INDX to end of ushort table. If there are uints in this
                                        table, they are not included in the size. If the table ends with a "CD AB" byte
                                        for 4 byte alignment, these bytes are included.
```

From here, you need to jump between the string table and the offset table sequentially. Read the first record in the string table with the first record in the offset table. There are currently no string tables that transitioned from ushorts to uints, but there are a few offset tables that do transition to needing to be read as uints. ((offset * 2) + 1) will map you to the correct location in TEXT.


Each section in all file versions are concluded with a "FOOT" to close the INDX section, length of foot and padded for alignment to 16 total bytes.

### TEXT

Use the INDX sections to find the text in this table.

All strings are null terminated in all file versions.

For v1 and v4 files specifically, each TEXT entry must be an even number of bytes, with the next entry starting at an odd byte. If the string (including null terminator) contains an odd number of bytes, an additional "00" is added to the end of the string to pad it.

Additionally, v1 files always start with an empty string as the first entry in their TEXT table (b"\x00\x00).

At the end of the file, all remaining sections (TEXT, BLJA and EVTX) are concluded with a "FOOT", length of foot and padded for alignment to 16 total bytes.
