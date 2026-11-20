"""Native 9:16 layout geometries and FFmpeg filtergraph generator for Clipiest."""
import math

CATALOG = [
    ("stack", "Face + gameplay", "Camera above the action"),
    ("bottom", "Gameplay + face", "Camera below the action"),
    ("blur", "Blurred fill", "Complete 16:9 frame with aesthetic blurred background"),
    ("fill", "Fill screen", "Full-frame 9:16 centre crop"),
    ("game", "Gameplay only", "Crop directly to the selected gameplay region"),
    ("pip_tl", "Camera top-left", "Floating picture-in-picture webcam top-left"),
    ("pip_tr", "Camera top-right", "Floating picture-in-picture webcam top-right"),
    ("pip_bl", "Camera bottom-left", "Floating picture-in-picture webcam bottom-left"),
    ("pip_br", "Camera bottom-right", "Floating picture-in-picture webcam bottom-right"),
    ("circle", "Circle camera", "Circular masked webcam floating above gameplay"),
    ("side", "Side by side", "Split columns: camera left, gameplay right"),
]

LAYOUT_IDS = {item[0] for item in CATALOG}

def text_positions(name: str, top: float = 0.32, caption_y: int = 1450) -> dict:
    """Computes safe Y-positions for the hook title and subtitles to avoid colliding with facecam."""
    spec = geometry(name, top)
    cam = next((layer for layer in spec.get("layers", []) if layer.get("source") == "cam"), None)
    hook_y = 260
    if cam and cam["y"] < 100:
        hook_y = cam["y"] + cam["h"] + 30
    if name == "side":
        hook_y = 260
    if caption_y == 1450 and cam and cam["y"] > 900:
        caption_y = min(caption_y, cam["y"] - 120)
    return {"hook_y": int(hook_y), "caption_y": int(caption_y)}

def geometry(name: str, top: float = 0.32) -> dict:
    """Computes pixel coordinate boundaries for video layers inside 1080x1920."""
    if name not in LAYOUT_IDS:
        raise ValueError(f"Unknown layout: {name}")
    top = float(top)
    if not math.isfinite(top) or not (0.2 <= top <= 0.5):
        raise ValueError("Speaker height ratio must be between 20% and 50% (0.2 - 0.5).")
    
    h = int(top * 1920) // 2 * 2
    full = {"source": "full", "x": 0, "y": 0, "w": 1080, "h": 1920}
    game = {**full, "source": "game"}

    if name == "blur":
        return {"mode": "blur", "layers": []}
    if name == "fill":
        return {"mode": "layers", "layers": [full]}
    if name == "game":
        return {"mode": "layers", "layers": [game]}
    if name in ("stack", "bottom"):
        cam_y = 0 if name == "stack" else 1920 - h
        game_y = h if name == "stack" else 0
        cam = {"source": "cam", "x": 0, "y": cam_y, "w": 1080, "h": h}
        return {"mode": "layers", "layers": [{**game, "y": game_y, "h": 1920 - h}, cam]}
    if name == "side":
        w = int(top * 1080) // 2 * 2
        return {"mode": "layers", "layers": [{**game, "x": w, "w": 1080 - w}, {"source": "cam", "x": 0, "y": 0, "w": w, "h": 1920}]}
    
    # Floating PiP & Circle
    w = int(top * 1080) // 2 * 2
    size = w if name == "circle" else int(w * 0.9) // 2 * 2
    right = name in ("pip_tr", "pip_br")
    bottom = name in ("pip_bl", "pip_br")
    cam_x = 1080 - w - 36 if right else 36
    cam_y = 1920 - size - 180 if bottom else 72
    return {
        "mode": "layers",
        "layers": [
            game,
            {
                "source": "cam",
                "x": cam_x,
                "y": cam_y,
                "w": w,
                "h": size,
                "circle": name == "circle"
            }
        ]
    }

def render_graph(name: str, rects: list, top: float = 0.32) -> str:
    """Builds the FFmpeg -filter_complex string for this layout given crop rects: [(cam_x,y,w,h), (game_x,y,w,h)]."""
    spec = geometry(name, top)
    if spec["mode"] == "blur":
        return (
            "[0:v]split=2[b][f];"
            "[b]scale=270:480:force_original_aspect_ratio=increase,crop=270:480,boxblur=8:2,"
            "scale=1080:1920,eq=brightness=-0.12:saturation=1.15[bg];"
            "[f]scale=1080:1920:force_original_aspect_ratio=decrease[fg];"
            "[bg][fg]overlay=(W-w)/2:(H-h)/2,setsar=1[base]"
        )
    
    layers = spec["layers"]
    parts = []
    if len(layers) > 1:
        parts.append(f"[0:v]split={len(layers)}" + "".join(f"[s{i}]" for i in range(len(layers))))
    
    for i, layer in enumerate(layers):
        source = f"[s{i}]" if len(layers) > 1 else "[0:v]"
        crop = ""
        if layer["source"] != "full":
            x, y, w, h = rects[0 if layer["source"] == "cam" else 1]
            crop = f"crop={w}:{h}:{x}:{y},"
        lw, lh = layer["w"], layer["h"]
        mask = ""
        if layer.get("circle"):
            # Smooth circular alpha mask equation
            mask = ",format=rgba,geq=r='r(X,Y)':g='g(X,Y)':b='b(X,Y)':a='if(lte(pow(X-W/2,2)+pow(Y-H/2,2),pow(min(W,H)/2,2)),255,0)'"
        parts.append(f"{source}{crop}scale={lw}:{lh}:force_original_aspect_ratio=increase,crop={lw}:{lh},setsar=1{mask}[p{i}]")
    
    first = layers[0]
    parts.append(f"[p0]pad=1080:1920:{first['x']}:{first['y']}:black[b0]")
    for i, layer in enumerate(layers[1:], 1):
        parts.append(f"[b{i-1}][p{i}]overlay={layer['x']}:{layer['y']}:shortest=1[b{i}]")
    parts.append(f"[b{len(layers)-1}]null[base]")
    return ";".join(parts)
