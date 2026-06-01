import queue
import threading
import time


class LogBus:
    def __init__(self):
        self._lock = threading.Lock()
        self._subs: dict[int, "queue.Queue[str]"] = {}
        self._next_id = 1

    def publish(self, msg: str) -> None:
        with self._lock:
            qs = list(self._subs.values())
        for q in qs:
            try:
                q.put_nowait(msg)
            except Exception:
                # Best-effort logging; drop if subscriber is slow/broken.
                pass

    def subscribe(self) -> tuple[int, "queue.Queue[str]"]:
        with self._lock:
            sid = self._next_id
            self._next_id += 1
            q: "queue.Queue[str]" = queue.Queue()
            self._subs[sid] = q
        return sid, q

    def unsubscribe(self, sid: int) -> None:
        with self._lock:
            self._subs.pop(sid, None)


def sse_format(data: str, event: str | None = None) -> str:
    # SSE format: event/name optional, data required. Blank line ends the message.
    out = []
    if event:
        out.append(f"event: {event}")
    for line in data.splitlines() or [""]:
        out.append(f"data: {line}")
    out.append("")
    return "\n".join(out)


def heartbeat_every(seconds: float):
    last = time.monotonic()
    while True:
        now = time.monotonic()
        if now - last >= seconds:
            yield True
            last = now
        else:
            yield False
