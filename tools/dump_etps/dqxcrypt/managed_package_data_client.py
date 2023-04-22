import os
import struct
from pprint import pprint

# def get_internal_id_for_filename(filename: str) -> int:
#     LEGACY_SUBPACKAGE_PREFIX = "smldt_msg_pkg_"
#     LEGACY_SUBPACKAGE_INDEX = [
#         "2DMAP", 
#         "BATTLE", 
#         "BG_AGENT_NAME", 
#         "BG_GIMMICK", 
#         "CAFE_PLAYMODECHANGE", 
#         "COMMANDWINDOW", 
#         "COMMUNICATIONWINDOW", 
#         "CONTINENTAL_NAME", 
#         "DUBBLE_SURECHIGAI", 
#         "EVENT", 
#         "GUILD", 
#         "HOUSING", 
#         "ITEM", 
#         "KEYNAME", 
#         "LIVE", 
#         "LIVE_SAVE", 
#         "LOADING_TIPS", 
#         "LOCATIONTITLE", 
#         "MENU_LOADING", 
#         "NORIMONO", 
#         "NPC_DB", 
#         "PC_SAVE_POPPOINT_NAME", 
#         "SHOP", 
#         "STAGE_ID", 
#         "SYSTEM", 
#         "SYSTEM_MENU",
#     ]

#     if filename.startswith(LEGACY_SUBPACKAGE_PREFIX):
#         # Determine legacy "smldt_msg_pkg_" subpackages by the text type, looked up via table.
#         legacy_type = filename[len(LEGACY_SUBPACKAGE_PREFIX):].split('.')[0]
#         internal_id = LEGACY_SUBPACKAGE_INDEX.index(legacy_type)
#         assert(internal_id >= 0 and internal_id <= 25)
#     else:
#         # Determine by subpackage number (offset by legacy subpackage IDs)
#         # "subPackage%02dClient.*.etp"
#         offset_id = int(filename[len('subPackage'):len('subPackage')+2])
#         internal_id = offset_id+len(LEGACY_SUBPACKAGE_INDEX)-1
#         assert(internal_id > 25)

#     return internal_id

class ManagedPackageDataClient():
    class group_header():
        def __init__(self, unk0, unk1, keys_count, ranges_count) -> None:
            self.unk0 = unk0
            self.unk1 = unk1
            self.keys_count = keys_count
            self.ranges_count = ranges_count

        def __repr__(self) -> str:
            return str(self.__dict__)

    class group_range():
        def __init__(self, lo, hi) -> None:
            self.lo = lo
            self.hi = hi

        def __repr__(self) -> str:
            return str(self.__dict__)

    def __init__(self):
        self.group_headers: list[ManagedPackageDataClient.group_header]
        self.group_ranges: list[ManagedPackageDataClient.group_range]
        self.group_keys: list[list[str]]

    def read_from(self, filename):
        with open(filename, 'rb') as f:
            # Read header
            (self.group_count, self.header_unk0, self.header_unk1, self.format_version) = struct.unpack('<IIII', f.read(16))
            # print(self.group_count, self.header_unk0, self.header_unk1, self.format_version)

            # Read group header table
            self.group_headers = []
            for group_id in range(self.group_count):
                (group_header_unk0, group_header_unk1, keys_count, ranges_count) = struct.unpack('<IIII', f.read(16))
                self.group_headers.append(ManagedPackageDataClient.group_header(group_header_unk0, group_header_unk1, keys_count, ranges_count))
            
            # 16-byte alignment
            f.seek(f.tell()%16, os.SEEK_CUR)

            # Read group ranges table
            self.group_ranges = []
            for group_id in range(self.group_count):
                ranges = []
                for j in range(self.group_headers[group_id].ranges_count//2):
                    (lo, hi) = struct.unpack('<II', f.read(8))
                    ranges.append(ManagedPackageDataClient.group_range(lo,  hi))
                self.group_ranges.append(ranges)
            
            # 16-byte alignment
            f.seek(f.tell()%16, os.SEEK_CUR)

            # Read group keys table
            self.group_keys = []
            for group_id in range(self.group_count):
                keys = []
                for j in range(self.group_headers[group_id].keys_count):
                    # Just decrypt/transform the keys when we first get them
                    transformed_key = ''.join([chr(b ^ 0x4D) for b in f.read(16)])
                    keys.append(transformed_key)
                self.group_keys.append(keys)

    # def get_adjusted_key_index_thing(self, group_id: int, internal_id:int) -> int:
    #     total_range_count = len(self.group_ranges[group_id])
    #     i = 0
    #     group_range = self.group_ranges[group_id][i]
    #     used_id = internal_id
    #     if total_range_count > 0:
    #         while internal_id >= group_range.lo:
    #             # Return -1 if in range.
    #             if internal_id <= group_range.hi:
    #                 return -1
                
    #             used_id = group_range.lo - group_range.hi + used_id - 1

    #             i += 1                
    #             if i >= total_range_count:
    #                 return used_id
                
    #             group_range = self.group_ranges[group_id][i]

    #     return used_id

    # def get_key_for_id(self, internal_id: int):
    #     if internal_id < 26:
    #         # Legacy "smldt_msg_pkg_" subpackages.
    #         group_id = 2
    #     else:
    #         group_id = 0
    #         internal_id = internal_id-25

    #     assert(group_id < self.group_count)

    #     if self.format_version == 2:
    #         used_id = self.get_adjusted_key_index_thing(group_id, internal_id)
    #     else:
    #         used_id = internal_id
        
    #     if used_id < self.group_headers[group_id].keys_count:
    #         if used_id != -1:
    #             return self.group_keys[group_id][used_id]
    #     else:
    #         return self.group_keys[group_id][0]

    #     #raise RuntimeError(f'No key for group_id={group_id}, internal_id={internal_id}, used_id={used_id}')
        
def unittests():
    reader = ManagedPackageDataClient()
    reader.read_from(r'C:\Users\Ando\Desktop\dqx_dat_dump\out\data00000000.win32.dat0\800718ca783ff612_rps\ManagedPackageDataClient.win32.pkg')
    pprint(reader.group_headers)
    pprint(reader.group_ranges)
    pprint(reader.group_keys)
    
    expected = [
        ('smldt_msg_pkg_COMMANDWINDOW.*.etp', '9)R6F3ZRr)FuijVY'),
        ('smldt_msg_pkg_NPC_DB.*.etp', 'E,*6URe#2NS2u.!S'),
        ('subPackage01Client.*.etp', 'ycRX5zq|33ytRye5'),
        ('subPackage02Client.*.etp', 'g#_tfrQs.TE45fw.'),
        ('subPackage04Client.*.etp', ';}r$!l?:|)5wf7H{'),
        #('subPackage07Client.*.etp', '!X-m?DapMm+HC9Hz'), # fails
        ('subPackage16Client.*.etp', '9Bb|8BJ!|*K3zhCK'),
        ('subPackage27Client.*.etp', 'u_D4KMe(Vxu5k#m2'),
        ('subPackage29Client.*.etp', '3mZ)9]INmWu*{i31'),
        ('subPackage36Client.*.etp', 'A4V-aScfqArEFqVh'),
        ('subPackage37Client.*.etp', 'v_VYprtU~6gGkiwh'),
        ('subPackage39Client.*.etp', 'eNf59RJB_J(jhtuX'),
        ('subPackage40Client.*.etp', 'Js.tYMZ(5Ayh3RuY'),
        ('subPackage41Client.*.etp', '_iw3GDKYdCk-(w!P'),
        ('subPackage68Client.*.etp', 'V5Lgo+p;_qR?K?yt'),
        ('subPackage96Client.*.etp', 'Abe4wec+Vff_TPKe'),
        #('subPackage127Client.*.etp', ')X*RB9jAWv~-lWhJ'), # fails
        #('subPackage128Client.*.etp', 'KnP#eX_a(cgW%rgH'), # fails
    ]

    for (filename, want) in expected:
        
        print(f'==== {filename} start')
        id = get_internal_id_for_filename(filename)
        got = reader.try_get_key_for_id(id)
        print(f'{filename}: want:"{want}", got:"{got}"')
        assert(want == got)

if __name__ == '__main__':
    unittests()
    os.exit(1)
    reader = ManagedPackageDataClient()
    reader.read_from(r'C:\Users\Ando\Desktop\dqx_dat_dump\out\data00000000.win32.dat0\800718ca783ff612_rps\ManagedPackageDataClient.win32.pkg')
    #print(get_internal_id_for_filename("smldt_msg_pkg_COMMANDWINDOW.*.etp"))
    #print(get_internal_id_for_filename("subPackage04Client.*.etp")) # 29

    pprint(reader.group_headers)
    pprint(reader.group_ranges)
    pprint(reader.group_keys)

    for i in [5, 20, 26, 27, 29]:
        print(i)
        print(reader.get_key_for_id(i))