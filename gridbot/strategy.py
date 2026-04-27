from abc import ABC, abstractmethod
from typing import Callable

from .direction import Direction
from .types import GameState


class Strategy(ABC):
    """Base interface that all bot strategies must implement."""

    @abstractmethod
    def move(self, state: GameState) -> Direction:
        """Called each turn. Return the direction to move."""
        ...


class StrategyFunc(Strategy):
    """Adapter to use a plain function as a Strategy."""

    def __init__(self, func: Callable[[GameState], Direction]):
        self._func = func

    def move(self, state: GameState) -> Direction:
        return self._func(state)


class MatchAware:
    """
    Optional mixin for strategies that want match lifecycle callbacks.
    Combine with Strategy:

        class MyBot(Strategy, MatchAware):
            def move(self, state): ...
            def on_match_start(self, state): ...
            def on_death(self, state): ...
            def on_win(self, state): ...
    """

    def on_match_start(self, state: GameState) -> None:
        """Called when a new match begins (turn <= 1)."""

    def on_death(self, state: GameState) -> None:
        """Called when the bot dies (you.alive becomes False)."""

    def on_win(self, state: GameState) -> None:
        """Called when the bot wins (all opponents dead, bot still alive)."""
