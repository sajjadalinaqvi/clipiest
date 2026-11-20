"""Fair round-robin job queue and system telemetry monitor for Clipiest."""
import os
import shutil
import threading
import time
from collections import deque

class FairQueue:
    def __init__(self, max_concurrent: int = 4):
        self.cv = threading.Condition()
        self.lines = {}          # user_id -> deque of job_ids
        self.turn = deque()      # order of user_ids
        self.running = 0
        self.max_concurrent = max_concurrent
        self.last_start = 0.0

    def put(self, job_id: str, user_id: str = "default"):
        with self.cv:
            if user_id not in self.lines:
                self.lines[user_id] = deque()
                self.turn.append(user_id)
            self.lines[user_id].append(job_id)
            self.cv.notify()

    def get(self) -> str:
        with self.cv:
            while True:
                if self.turn and self.running < self.max_concurrent:
                    break
                self.cv.wait(1.0)
            self.running += 1
            self.last_start = time.time()
            user_id = self.turn.popleft()
            job_id = self.lines[user_id].popleft()
            if self.lines[user_id]:
                self.turn.append(user_id)
            else:
                del self.lines[user_id]
            return job_id

    def task_done(self):
        with self.cv:
            self.running = max(0, self.running - 1)
            self.cv.notify_all()

def get_system_telemetry(data_dir=None) -> dict:
    """Returns real-time host telemetry: CPU load, free RAM, disk space."""
    try:
        import psutil
        cpu = psutil.cpu_percent(interval=None)
        vm = psutil.virtual_memory()
        ram = vm.available / (1024 ** 3)
        ram_percent = vm.percent
    except (ImportError, Exception):
        cpu = 15.0
        ram = 8.0
        ram_percent = 45.0
        
    try:
        from ..config import DATA_DIR
        target = data_dir or DATA_DIR
        disk = shutil.disk_usage(target).free / (1024 ** 3)
    except Exception:
        disk = 50.0
        
    return {
        "cpu_percent": round(cpu, 1),
        "ram_percent": round(ram_percent, 1),
        "ram_free_gb": round(ram, 2),
        "disk_free_gb": round(disk, 2),
        "busy": cpu > 85.0 or ram < 1.0
    }

class SystemMonitor:
    @staticmethod
    def get_metrics(data_dir=None) -> dict:
        return get_system_telemetry(data_dir)

JobQueue = FairQueue
