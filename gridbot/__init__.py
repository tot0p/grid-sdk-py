"""
grid-sdk-py — Python SDK for Grid Tron-style bot battles.

Quick start::

    from gridbot import Client, Config, StrategyFunc, GameState, Direction

    def my_strategy(state: GameState) -> Direction:
        from gridbot.helpers import safe_moves_detailed
        moves = safe_moves_detailed(state)
        return moves[0].direction if moves else Direction(state.you.direction)

    client = Client(Config(
        server_url="wss://game.learn2code.tech",
        token="your-bot-token",
        strategy=StrategyFunc(my_strategy),
    ))
    client.run()
"""

from .client import Client, Config
from .direction import ALL_DIRECTIONS, Direction
from .helpers import (
    bot_by_id,
    distance_to,
    fill_ratio,
    find_closest_opponent,
    find_opponents,
    flood_fill,
    grid_value,
    head_on_risk,
    is_safe,
    is_trapped,
    manhattan_distance,
    neighbors,
    safe_moves,
    safe_moves_detailed,
    voronoi_bfs,
    wall_count,
)
from .strategy import MatchAware, Strategy, StrategyFunc
from .types import Bot, GameState, MatchResult, Move, Position

__all__ = [
    # Client
    "Client",
    "Config",
    # Types
    "Bot",
    "GameState",
    "MatchResult",
    "Move",
    "Position",
    # Direction
    "Direction",
    "ALL_DIRECTIONS",
    # Strategy
    "Strategy",
    "StrategyFunc",
    "MatchAware",
    # Helpers — cell inspection
    "is_safe",
    "grid_value",
    "neighbors",
    "wall_count",
    "fill_ratio",
    # Helpers — move generation
    "safe_moves",
    "safe_moves_detailed",
    # Helpers — space analysis
    "flood_fill",
    "is_trapped",
    "voronoi_bfs",
    # Helpers — distance
    "manhattan_distance",
    "distance_to",
    # Helpers — opponent analysis
    "head_on_risk",
    "find_opponents",
    "find_closest_opponent",
    "bot_by_id",
]
