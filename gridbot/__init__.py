"""
grid-sdk-py — Python SDK for Grid Tron-style bot battles.

Quick start::

    from gridbot import Client, Config, StrategyFunc, GameState, Direction

    def my_strategy(state: GameState) -> Direction:
        from gridbot.helpers import safe_moves_detailed
        moves = safe_moves_detailed(state)
        return moves[0].direction if moves else Direction(state.you.direction)

    client = Client(Config(
        server_url="ws://localhost:8083",
        token="your-bot-token",
        strategy=StrategyFunc(my_strategy),
    ))
    client.run()
"""

from .client import Client, Config
from .direction import ALL_DIRECTIONS, Direction
from .helpers import (
    find_closest_opponent,
    find_opponents,
    flood_fill,
    head_on_risk,
    is_safe,
    manhattan_distance,
    safe_moves,
    safe_moves_detailed,
    voronoi_bfs,
    wall_count,
)
from .strategy import MatchAware, Strategy, StrategyFunc
from .types import Bot, GameState, Move

__all__ = [
    # Client
    "Client",
    "Config",
    # Types
    "Bot",
    "GameState",
    "Move",
    # Direction
    "Direction",
    "ALL_DIRECTIONS",
    # Strategy
    "Strategy",
    "StrategyFunc",
    "MatchAware",
    # Helpers
    "is_safe",
    "safe_moves",
    "safe_moves_detailed",
    "flood_fill",
    "voronoi_bfs",
    "manhattan_distance",
    "wall_count",
    "head_on_risk",
    "find_opponents",
    "find_closest_opponent",
]
