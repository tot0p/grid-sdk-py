from typing import List, Optional, Tuple

from .direction import ALL_DIRECTIONS, Direction
from .types import Bot, GameState, Move, Position

# ---------------------------------------------------------------------------
# Internal: flat grid cache
# ---------------------------------------------------------------------------

def _flat(state: GameState) -> bytearray:
    """
    Return a *cached* flat bytearray view of state.grid.
    Layout: flat[y * width + x] — 0 = free, 1 = occupied.
    Cached on the GameState instance so multiple helpers share one conversion.
    """
    cache = state.__dict__.get("_flat_cache")
    if cache is not None:
        return cache
    w = state.width
    flat = bytearray(state.height * w)
    for y, row in enumerate(state.grid):
        base = y * w
        for x, val in enumerate(row):
            if val:
                flat[base + x] = 1
    state.__dict__["_flat_cache"] = flat
    return flat


# ---------------------------------------------------------------------------
# Cell inspection
# ---------------------------------------------------------------------------

def is_safe(x: int, y: int, state: GameState) -> bool:
    """Return True if (x, y) is within bounds and the cell is empty."""
    return (
        0 <= x < state.width
        and 0 <= y < state.height
        and state.grid[y][x] == 0
    )


def grid_value(x: int, y: int, state: GameState) -> int:
    """Return the raw grid value at (x, y), or -1 if out of bounds.
    0 = empty; any other value = occupied by a bot's trail."""
    if x < 0 or x >= state.width or y < 0 or y >= state.height:
        return -1
    return state.grid[y][x]


def neighbors(x: int, y: int, state: GameState) -> List[Position]:
    """Return all safe 4-connected positions adjacent to (x, y)."""
    return [
        Position(nx, ny)
        for d in ALL_DIRECTIONS
        for nx, ny in [d.apply(x, y)]
        if is_safe(nx, ny, state)
    ]


def wall_count(x: int, y: int, state: GameState) -> int:
    """Count non-safe adjacent cells (out-of-bounds + occupied) around (x, y).
    Range: 0–4."""
    return sum(
        1 for d in ALL_DIRECTIONS
        if not is_safe(*d.apply(x, y), state)
    )


def fill_ratio(state: GameState) -> float:
    """Return the fraction of the grid that is occupied (0.0–1.0).
    Useful for detecting game phase: <0.15 = early, 0.15–0.5 = mid, >0.5 = late."""
    total = state.width * state.height
    if total == 0:
        return 0.0
    flat = _flat(state)
    return sum(flat) / total


# ---------------------------------------------------------------------------
# Move generation
# ---------------------------------------------------------------------------

def safe_moves(state: GameState) -> List[Direction]:
    """Return all directions from the bot's current position that lead to a
    safe cell, excluding the reverse direction (180-degree turn)."""
    if state.you is None:
        return []
    current = Direction(state.you.direction)
    return [
        d for d in ALL_DIRECTIONS
        if not d.is_opposite(current)
        and is_safe(*d.apply(state.you.x, state.you.y), state)
    ]


def safe_moves_detailed(state: GameState) -> List[Move]:
    """Return all safe moves with target positions and head-on risk info.
    Excludes the reverse direction."""
    if state.you is None:
        return []
    current = Direction(state.you.direction)
    out = []
    for d in ALL_DIRECTIONS:
        if d.is_opposite(current):
            continue
        nx, ny = d.apply(state.you.x, state.you.y)
        if is_safe(nx, ny, state):
            out.append(Move(
                direction=d,
                x=nx,
                y=ny,
                head_on_risk=head_on_risk(nx, ny, state),
            ))
    return out


# ---------------------------------------------------------------------------
# Space analysis
# ---------------------------------------------------------------------------

def flood_fill(x: int, y: int, state: GameState) -> int:
    """Count reachable empty cells from (x, y) via BFS.

    Optimised with bytearray + integer indices (~5-8× faster than naïve BFS):
    no per-cell tuple allocation, no deque overhead.
    """
    w, h = state.width, state.height
    flat = _flat(state)
    start = y * w + x

    if flat[start]:
        return 0

    size = w * h
    visited = bytearray(size)
    visited[start] = 1
    stack = [start]
    count = 1
    qi = 0

    while qi < len(stack):
        pos = stack[qi]
        qi += 1
        px = pos % w
        py = pos // w

        if px > 0:
            n = pos - 1
            if not visited[n] and not flat[n]:
                visited[n] = 1; count += 1; stack.append(n)
        if px < w - 1:
            n = pos + 1
            if not visited[n] and not flat[n]:
                visited[n] = 1; count += 1; stack.append(n)
        if py > 0:
            n = pos - w
            if not visited[n] and not flat[n]:
                visited[n] = 1; count += 1; stack.append(n)
        if py < h - 1:
            n = pos + w
            if not visited[n] and not flat[n]:
                visited[n] = 1; count += 1; stack.append(n)

    return count


def is_trapped(state: GameState, threshold: int = 15) -> bool:
    """Return True if the bot's reachable space is below threshold.
    Useful as a quick escape-priority trigger. Default threshold: 15 cells."""
    if state.you is None:
        return True
    return flood_fill(state.you.x, state.you.y, state) < threshold


def voronoi_bfs(
    my_x: int, my_y: int,
    opp_x: int, opp_y: int,
    state: GameState,
) -> Tuple[int, int]:
    """Simultaneous BFS from two positions.
    Returns (my_count, opp_count) — cells each side reaches first.
    Optimised with bytearray + integer indices."""
    w, h = state.width, state.height
    flat = _flat(state)
    size = w * h

    my_start = my_y * w + my_x
    if flat[my_start]:
        return 0, 0

    owner = bytearray(size)   # 0=unvisited, 1=mine, 2=opponent
    owner[my_start] = 1
    my_count = 1
    my_front: list = [my_start]

    opp_count = 0
    opp_front: list = []
    opp_start = opp_y * w + opp_x
    if not flat[opp_start] and owner[opp_start] == 0:
        owner[opp_start] = 2
        opp_count = 1
        opp_front = [opp_start]

    while my_front or opp_front:
        next_my: list = []
        for pos in my_front:
            px = pos % w; py = pos // w
            if px > 0:
                n = pos - 1
                if owner[n] == 0 and not flat[n]:
                    owner[n] = 1; my_count += 1; next_my.append(n)
            if px < w - 1:
                n = pos + 1
                if owner[n] == 0 and not flat[n]:
                    owner[n] = 1; my_count += 1; next_my.append(n)
            if py > 0:
                n = pos - w
                if owner[n] == 0 and not flat[n]:
                    owner[n] = 1; my_count += 1; next_my.append(n)
            if py < h - 1:
                n = pos + w
                if owner[n] == 0 and not flat[n]:
                    owner[n] = 1; my_count += 1; next_my.append(n)
        my_front = next_my

        next_opp: list = []
        for pos in opp_front:
            px = pos % w; py = pos // w
            if px > 0:
                n = pos - 1
                if owner[n] == 0 and not flat[n]:
                    owner[n] = 2; opp_count += 1; next_opp.append(n)
            if px < w - 1:
                n = pos + 1
                if owner[n] == 0 and not flat[n]:
                    owner[n] = 2; opp_count += 1; next_opp.append(n)
            if py > 0:
                n = pos - w
                if owner[n] == 0 and not flat[n]:
                    owner[n] = 2; opp_count += 1; next_opp.append(n)
            if py < h - 1:
                n = pos + w
                if owner[n] == 0 and not flat[n]:
                    owner[n] = 2; opp_count += 1; next_opp.append(n)
        opp_front = next_opp

    return my_count, opp_count


# ---------------------------------------------------------------------------
# Distance
# ---------------------------------------------------------------------------

def manhattan_distance(x1: int, y1: int, x2: int, y2: int) -> int:
    """Return |x1-x2| + |y1-y2|."""
    return abs(x1 - x2) + abs(y1 - y2)


def distance_to(state: GameState, target: Bot) -> int:
    """Return the Manhattan distance from the bot to a target bot.
    Returns -1 if state.you is None."""
    if state.you is None:
        return -1
    return manhattan_distance(state.you.x, state.you.y, target.x, target.y)


# ---------------------------------------------------------------------------
# Opponent analysis
# ---------------------------------------------------------------------------

def head_on_risk(x: int, y: int, state: GameState) -> bool:
    """Return True if an alive opponent could also move to (x, y) next turn."""
    if state.you is None:
        return False
    my_id = state.you.bot_id
    for bot in state.bots:
        if bot.bot_id == my_id or not bot.alive:
            continue
        for d in ALL_DIRECTIONS:
            ox, oy = d.apply(bot.x, bot.y)
            if ox == x and oy == y:
                return True
    return False


def find_opponents(state: GameState) -> List[Bot]:
    """Return all alive bots that are not you."""
    if state.you is None:
        return []
    my_id = state.you.bot_id
    return [b for b in state.bots if b.bot_id != my_id and b.alive]


def find_closest_opponent(state: GameState) -> Optional[Bot]:
    """Return the closest alive opponent by Manhattan distance, or None."""
    if state.you is None:
        return None
    opponents = find_opponents(state)
    if not opponents:
        return None
    return min(opponents, key=lambda b: manhattan_distance(
        state.you.x, state.you.y, b.x, b.y
    ))


def bot_by_id(bot_id: int, state: GameState) -> Optional[Bot]:
    """Return the bot with the given ID, or None if not found."""
    for b in state.bots:
        if b.bot_id == bot_id:
            return b
    return None
