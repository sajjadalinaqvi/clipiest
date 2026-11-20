"""Anonymous chat listener for Twitch and YouTube Live streams."""
import re
import socket
import ssl
import time
import threading
from collections import Counter, defaultdict

_NICK = re.compile(r"(?m)^:([A-Za-z0-9_]{2,25})!")

class ChatWatcher:
    def __init__(self, platform: str, target: str):
        self.platform = platform.lower()
        self.target = target
        self.stop_ev = threading.Event()
        self.counts = Counter()          # second -> message count
        self.users = defaultdict(set)    # second -> set of user nicknames
        self.total_msgs = 0
        self.status = "connecting"
        
    def start(self):
        if self.platform == "twitch":
            threading.Thread(target=self._twitch_loop, daemon=True).start()
        else:
            threading.Thread(target=self._youtube_loop, daemon=True).start()
            
    def stop(self):
        self.stop_ev.set()

    def _twitch_loop(self):
        while not self.stop_ev.is_set():
            try:
                raw = socket.create_connection(("irc.chat.twitch.tv", 6697), timeout=20)
                s = ssl.create_default_context().wrap_socket(raw, server_hostname="irc.chat.twitch.tv")
                s.sendall(f"NICK justinfan{int(time.time()) % 90000 + 10000}\r\nJOIN #{self.target}\r\n".encode())
                s.settimeout(30)
                self.status = "connected"
                buf = b""
                while not self.stop_ev.is_set():
                    try:
                        data = s.recv(4096)
                    except socket.timeout:
                        continue
                    if not data:
                        break
                    buf += data
                    *lines, buf = buf.split(b"\r\n")
                    for line in lines:
                        if line.startswith(b"PING"):
                            s.sendall(b"PONG :tmi.twitch.tv\r\n")
                        elif b" PRIVMSG #" in line:
                            sec = int(time.time())
                            self.counts[sec] += 1
                            self.total_msgs += 1
                            who = _NICK.findall(line.decode("utf-8", "replace"))
                            if who:
                                self.users[sec].add(who[0].lower())
                s.close()
            except Exception:
                self.status = "reconnecting"
                time.sleep(3)

    def _youtube_loop(self):
        try:
            import pytchat
            chat = pytchat.create(video_id=self.target, interruptable=False)
            self.status = "connected"
            while chat.is_alive() and not self.stop_ev.is_set():
                for c in chat.get().sync_items():
                    sec = int(time.time())
                    self.counts[sec] += 1
                    self.total_msgs += 1
                    if getattr(c, 'author', None):
                        self.users[sec].add(c.author.name)
                time.sleep(0.5)
        except Exception:
            self.status = "unavailable"
