from __future__ import annotations

from collections import deque
from typing import Deque, Iterable, List, Optional, Sequence, Set, Tuple

from .protocol import Cell, neighbors
from .config import N


def camp_cells_top_left() -> Set[Tuple[int, int]]:
    cells: Set[Tuple[int, int]] = set()
    for r in range(5):
        for c in range(5 - r):
            cells.add((r, c))
    return cells


def camp_cells_bottom_right() -> Set[Tuple[int, int]]:
    tl = camp_cells_top_left()
    return {(N - 1 - r, N - 1 - c) for r, c in tl}


CAMP_A = camp_cells_top_left()
CAMP_B = camp_cells_bottom_right()


class Board:
    def __init__(self) -> None:
        self.grid: List[List[int]] = [[Cell.EMPTY for _ in range(N)] for _ in range(N)]
        for r, c in CAMP_A:
            self.grid[r][c] = Cell.P1
        for r, c in CAMP_B:
            self.grid[r][c] = Cell.P2

    @staticmethod
    def deserialize(g: List[List[int]]) -> "Board":
        b = Board()
        b.grid = g
        return b

    def serialize(self) -> List[List[int]]:
        return self.grid

    def inside(self, r: int, c: int) -> bool:
        return 0 <= r < N and 0 <= c < N

    def cell(self, r: int, c: int) -> int:
        return self.grid[r][c]

    def set_cell(self, r: int, c: int, v: int) -> None:
        self.grid[r][c] = v

    def is_victory(self, player: int) -> bool:
        target = CAMP_B if player == Cell.P1 else CAMP_A
        return all(self.grid[r][c] == player for (r, c) in target)


def compute_moves(board: Board, start: Tuple[int, int]) -> Tuple[Set[Tuple[int, int]], Set[Tuple[int, int]]]:
    """Retorna (simples, saltos) a partir de `start`. BFS para saltos múltiplos."""
    r0, c0 = start
    simple: Set[Tuple[int, int]] = set()
    for r1, c1 in neighbors(r0, c0):
        if board.inside(r1, c1) and board.cell(r1, c1) == Cell.EMPTY:
            simple.add((r1, c1))

    jump_dest: Set[Tuple[int, int]] = set()
    q: Deque[Tuple[int, int]] = deque([start])
    visited: Set[Tuple[int, int]] = {start}

    DIRS = [(-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (-1, 1), (1, -1), (1, 1)]

    while q:
        r, c = q.popleft()
        for dr, dc in DIRS:
            r_mid, c_mid = r + dr, c + dc
            r2, c2 = r + 2 * dr, c + 2 * dc
            if not board.inside(r2, c2):
                continue
            if board.inside(r_mid, c_mid) and board.cell(r_mid, c_mid) in (Cell.P1, Cell.P2) and board.cell(r2, c2) == Cell.EMPTY:
                if (r2, c2) not in visited:
                    visited.add((r2, c2))
                    jump_dest.add((r2, c2))
                    q.append((r2, c2))

    return simple, jump_dest