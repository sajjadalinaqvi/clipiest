"""Clipiest Master CLI Entrypoint."""
import os
import sys
import uvicorn
from clipiest.config import HOST, PORT, HAS_NVENC, HAS_QSV, AI_PROVIDER, WHISPER_MODEL, DATA_DIR

def main():
    gpu_status = "NVENC (NVIDIA Hardware)" if HAS_NVENC else ("QSV (Intel Hardware)" if HAS_QSV else "CPU Software (libx264)")
    print("=" * 60)
    print("                CLIPIEST MASTER ENGINE")
    print("   AI Video Discovery + Neon Visual Framing & Dynamic ASS")
    print("=" * 60)
    print(f" Web UI:        http://{HOST}:{PORT}")
    print(f" Data Dir:      {DATA_DIR}")
    print(f" Video Encoder: {gpu_status}")
    print(f" ASR Model:     {WHISPER_MODEL}")
    print(f" AI Provider:   {AI_PROVIDER}")
    print("=" * 60)
    print("Starting server... Press Ctrl+C to stop.\n")
    try:
        uvicorn.run("clipiest.server:app", host=HOST, port=PORT, reload=False, access_log=True)
    except (KeyboardInterrupt, SystemExit):
        print("\n[Clipiest] Server stopped cleanly.")

if __name__ == "__main__":
    main()
