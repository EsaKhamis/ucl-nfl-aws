"""Run parameters shared by every stage (Dev 1 owns; ask before changing).

Relative paths are resolved against the repo root, so `python run.py` works
from any working directory.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent

PRE_RELEASE_OFFSETS = (3, 4, 5)          # Req 12.4
OPEN_MODES = ("most_open", "threshold")  # Open_Mode


@dataclass
class Config:
    data_dir: Path = Path("data")
    derived_dir: Path = Path("out")
    outputs_dir: Path = Path("results")
    games: list[int] | None = None      # None = every tracking file
    rebuild: bool = False
    fixtures: bool = False              # stages read out/fixtures/ instead of out/
    pre_release_offset: int = 4         # 3, 4 or 5 (Req 12.4)
    open_mode: str = "most_open"        # or "threshold"
    open_threshold: float = 3.0         # yards; set from the data on the day
    closing_horizon_s: float = 0.5      # Openness_Score horizon
    lambda_lane: float = 0.5            # composite openness: weight of the throwing-lane penalty (Dev 2)
    lane_cushion: float = 2.0           # yards: a defender closer than this to the QB-receiver lane is penalized
    route_minimum: int = 100
    split_route_minimum: int = 40
    team_route_minimum: int = 50
    headline_x: str = "open_rate"       # or "expected_share" (Req 27.8)
    use_nflverse: bool = False
    pressure_split: bool = False
    down_distance: bool = False
    yac_allowance: float = 0.0
    orientation: bool = False
    recent_proxy: bool = False

    def __post_init__(self):
        for name in ("data_dir", "derived_dir", "outputs_dir"):
            path = Path(getattr(self, name))
            setattr(self, name, path if path.is_absolute() else REPO_ROOT / path)
        # Req 12.5: stop the run and report the allowed values.
        if self.pre_release_offset not in PRE_RELEASE_OFFSETS:
            raise ValueError(f"pre_release_offset={self.pre_release_offset!r} is not allowed; "
                             f"use one of {PRE_RELEASE_OFFSETS}")
        if self.open_mode not in OPEN_MODES:
            raise ValueError(f"open_mode={self.open_mode!r} is not allowed; use one of {OPEN_MODES}")
