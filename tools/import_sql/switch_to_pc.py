# paths from the romfs of the nintendo switch dump.
# switch doesn't use sqpk and just has the files extracted,
# so this converts switch paths -> sqpk for pc.
PATH_CONVERT = {
    "/Data/bg": "bg",
    "/Conf": "Common/Conf",
    "/Data/Common": "Common",
    "/Data/chr": "common/data/chr",
    "/Data/cloud": "common/data/cloud",
    "/Data/effect": "common/data/effect",
    "/Data/event": "common/data/event",
    "/Data/eventText": "common/data/eventText",
    "/Data/forbiddenWord": "common/data/forbiddenWord",
    "/Data/luaPackage": "common/data/luaPackage",
    "/Data/lubRelease": "common/data/lubRelease",
    "/Data/main": "common/data/main",
    "/Data/menu": "common/data/menu",
    "/Data/movie": "invalid",  # these are not stored in the DATs on Windows, but in Bin/, Ex2000/Bin, Ex3000/Bin, etc.
    "/Data/packresource": "common/data/packresource",
    "/Data/pkg": "common/data/pkg",
    "/Data/rps": "common/data/rps",
    "/Data/share": "common/data/share",
    "/Data/sound": "sound/bin",
}
