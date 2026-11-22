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

def render_graph(name: str, rects: list, top: float = 0.32, background: str = "default", is_whole_game: bool = None) -> str:
    """Builds the FFmpeg -filter_complex string for this layout given crop rects: [(cam_x,y,w,h), (game_x,y,w,h)].
    The gameplay box fits from left to right inside the video under facecam without affecting facecam size.
    The empty space is filled by the selected background:
    - 'default': the same expanded source video blurred to fill empty space
    - 'black': solid black background
    - 'white': solid white background
    """
    spec = geometry(name, top)
    bg = (background or "default").lower().strip()
    if bg == "black":
        bg_filter = "scale=1080:1920,drawbox=x=0:y=0:w=1080:h=1920:color=black:t=fill"
    elif bg == "white":
        bg_filter = "scale=1080:1920,drawbox=x=0:y=0:w=1080:h=1920:color=white:t=fill"
    else:  # default / blur
        bg_filter = (
            "scale=270:480:force_original_aspect_ratio=increase,crop=270:480,boxblur=14:3,"
            "scale=1080:1920,eq=brightness=-0.12:saturation=1.15"
        )

    if spec["mode"] == "blur":
        return (
            f"[0:v]split=2[b][f];"
            f"[b]{bg_filter}[bg];"
            f"[f]scale=1080:1920:force_original_aspect_ratio=decrease[fg];"
            f"[bg][fg]overlay=(W-w)/2:(H-h)/2,setsar=1[base]"
        )
    
    layers = spec["layers"]
    num_splits = 1 + len(layers)
    parts = [f"[0:v]split={num_splits}[s_bg]" + "".join(f"[s{i}]" for i in range(len(layers)))]
    parts.append(f"[s_bg]{bg_filter}[bg]")
    
    for i, layer in enumerate(layers):
        source = f"[s{i}]"
        crop = ""
        is_game_source = layer["source"] in ("game", "full")
        if layer["source"] != "full":
            x, y, w, h = rects[0 if layer["source"] == "cam" else 1]
            w = max(2, int(w) // 2 * 2)
            h = max(2, int(h) // 2 * 2)
            x = max(0, int(x))
            y = max(0, int(y))
            crop = f"crop={w}:{h}:{x}:{y},"

        lw, lh = layer["w"], layer["h"]
        mask = ""
        if layer.get("circle"):
            # Smooth circular alpha mask equation
            mask = ",format=rgba,geq=r='r(X,Y)':g='g(X,Y)':b='b(X,Y)':a='if(lte(pow(X-W/2,2)+pow(Y-H/2,2),pow(min(W,H)/2,2)),255,0)'"

        if is_game_source and layer["source"] != "full":
            # Fits from left to right (width = lw = 1080) under facecam, preserving aspect ratio with zero side cropping
            scale_filter = f"scale={lw}:{lh}:force_original_aspect_ratio=decrease,setsar=1{mask}"
        else:
            scale_filter = f"scale={lw}:{lh}:force_original_aspect_ratio=increase,crop={lw}:{lh},setsar=1{mask}"

        parts.append(f"{source}{crop}{scale_filter}[p{i}]")
    
    curr = "[bg]"
    for i, layer in enumerate(layers):
        next_label = f"[b{i}]" if i < len(layers) - 1 else "[base]"
        if layer["source"] == "cam" or layer["source"] == "full":
            ox = layer["x"]
            oy = layer["y"]
        else:
            # Fits from left to right inside the video under facecam, vertically centered in the remaining space
            ox = "(1080-w)/2"
            oy = f"{layer['y']}+({layer['h']}-h)/2"
        parts.append(f"{curr}[p{i}]overlay={ox}:{oy}:shortest=1{next_label}")
        curr = next_label

    return ";".join(parts)
