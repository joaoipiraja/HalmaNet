from __future__ import annotations

from enum import Enum, IntEnum
from typing import Iterable, Tuple

# Direções (8-vizinhos)
DIRS: Tuple[Tuple[int, int], ...] = (
    (-1, 0), (1, 0), (0, -1), (0, 1),
    (-1, -1), (-1, 1), (1, -1), (1, 1),
)


class Cell(IntEnum):
    EMPTY = 0
    P1 = 1
    P2 = 2


class MsgType(str, Enum):
    JOIN = "join"
    STATE = "state"
    CHAT = "chat"
    MOVE = "move"
    ENDJUMP = "endjump"
    RESET = "reset"
    RESIGN = "resign"
    PING = "ping"
    PONG = "pong"
    ERROR = "error"
    DISCONNECT = "disconnect"  # uso interno do cliente


def neighbors(r: int, c: int) -> Iterable[Tuple[int, int]]:
    for dr, dc in DIRS:
        yield r + dr, c + dc