"""Game catalog & viral hashtag injector for Clipiest."""
import re

GAMES = {
    "gta6": ("Grand Theft Auto VI", ["GTA6", "GTA6Game", "ViceCity", "RockstarGames", "GTA6Launch", "GTA"]),
    "gta5": ("Grand Theft Auto V", ["GTA5", "GTAOnline", "GTARP", "RockstarGames", "NoPixel"]),
    "fortnite": ("Fortnite", ["Fortnite", "FortniteClips", "FortniteMemes", "FortniteBattleRoyale"]),
    "valorant": ("Valorant", ["Valorant", "ValorantClips", "RiotGames", "VCT", "ValorantHighlights"]),
    "minecraft": ("Minecraft", ["Minecraft", "MinecraftMemes", "MinecraftBuilds", "MinecraftClips"]),
    "elden_ring": ("Elden Ring", ["EldenRing", "ShadowOfTheErdtree", "FromSoftware", "SoulsBorne"]),
    "roblox": ("Roblox", ["Roblox", "RobloxClips", "RobloxMemes"]),
    "cod": ("Call of Duty", ["CallOfDuty", "Warzone", "CODWarzone", "MW3"]),
    "apex": ("Apex Legends", ["ApexLegends", "ApexClips", "PlayApex"]),
    "cs2": ("Counter-Strike 2", ["CS2", "CounterStrike", "CSGO", "CS2Clips"]),
    "league": ("League of Legends", ["LeagueOfLegends", "LOLClips", "RiotGames"]),
    "overwatch": ("Overwatch 2", ["Overwatch2", "OW2", "OverwatchClips"]),
    "marvel_rivals": ("Marvel Rivals", ["MarvelRivals", "Marvel", "MarvelGames"]),
    "cyberpunk": ("Cyberpunk 2077", ["Cyberpunk2077", "PhantomLiberty", "CDProjektRed"]),
    "helldivers": ("Helldivers 2", ["Helldivers2", "Helldivers", "ArrowheadGame"]),
    "palworld": ("Palworld", ["Palworld", "PocketPair"]),
    "rocket_league": ("Rocket League", ["RocketLeague", "RLClips"]),
    "r6": ("Rainbow Six Siege", ["R6Siege", "RainbowSixSiege", "R6Clips"]),
    "bgmi": ("BGMI", ["BGMI", "BattlegroundsMobileIndia", "BGMIClips"]),
    "freefire": ("Free Fire", ["FreeFire", "FFClips", "GarenaFreeFire"]),
    "pubg": ("PUBG", ["PUBG", "PUBGClips", "PUBGMobile"]),
    "fifa": ("EA Sports FC", ["FC25", "FIFA25", "EASportsFC"]),
    "deadlock": ("Deadlock", ["Deadlock", "ValveDeadlock", "Valve"])
}

PATTERNS = [
    (r"\bgta\s*vi\b|\bgta\s*6\b|grand theft auto vi|grand theft auto 6", "gta6"),
    (r"\bgta\s*v\b|\bgta\s*5\b|grand theft auto v|grand theft auto 5|gta rp", "gta5"),
    (r"\bfortnite\b", "fortnite"),
    (r"\bvalorant\b|\bvct\b|\bjett\b|\breyna\b|\bradiant\b", "valorant"),
    (r"\bminecraft\b", "minecraft"),
    (r"\belden ring\b", "elden_ring"),
    (r"\broblox\b", "roblox"),
    (r"\bwarzone\b|\bcall of duty\b|\bmw3\b|\bblack ops\b", "cod"),
    (r"\bapex legends\b", "apex"),
    (r"\bcs2\b|\bcounter[- ]strike\b", "cs2"),
    (r"\bleague of legends\b|\blol\b", "league"),
    (r"\boverwatch\b|\bow2\b", "overwatch"),
    (r"\bmarvel rivals\b", "marvel_rivals"),
    (r"\bcyberpunk\b", "cyberpunk"),
    (r"\bhelldivers\b", "helldivers"),
    (r"\bpalworld\b", "palworld"),
    (r"\brocket league\b", "rocket_league"),
    (r"\brainbow six\b|\br6\b", "r6"),
    (r"\bbgmi\b", "bgmi"),
    (r"\bfree fire\b", "freefire"),
    (r"\bdeadlock\b", "deadlock")
]

def detect_game(*text_sources) -> tuple[str | None, list[str]]:
    """Detects game key and returns (game_name, hashtags)."""
    joined = " ".join(str(s or "").lower() for s in text_sources)
    for pattern, key in PATTERNS:
        if re.search(pattern, joined):
            name, tags = GAMES[key]
            return name, tags
    return None, ["ViralShorts", "Trending", "Clips"]
