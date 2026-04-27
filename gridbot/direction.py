from enum import Enum
from typing import Tuple


class Direction(str, Enum):
    UP = "up"
    DOWN = "down"
    LEFT = "left"
    RIGHT = "right"

    def opposite(self) -> "Direction":
        _opp = {"up": "down", "down": "up", "left": "right", "right": "left"}
        return Direction(_opp[self.value])

    def delta_x(self) -> int:
        return {"left": -1, "right": 1}.get(self.value, 0)

    def delta_y(self) -> int:
        """Up is -1 (y decreases), Down is +1 (y increases)."""
        return {"up": -1, "down": 1}.get(self.value, 0)

    def apply(self, x: int, y: int) -> Tuple[int, int]:
        return x + self.delta_x(), y + self.delta_y()

    def is_opposite(self, other: "Direction") -> bool:
        return self == other.opposite()

    def turn_right(self) -> "Direction":
        _right = {"up": "right", "right": "down", "down": "left", "left": "up"}
        return Direction(_right[self.value])

    def turn_left(self) -> "Direction":
        _left = {"up": "left", "left": "down", "down": "right", "right": "up"}
        return Direction(_left[self.value])


ALL_DIRECTIONS: list = [Direction.UP, Direction.DOWN, Direction.LEFT, Direction.RIGHT]
