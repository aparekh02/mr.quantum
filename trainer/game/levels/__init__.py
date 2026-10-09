"""All levels, in play order."""

from trainer.game.level import Level
from trainer.game.levels.coulomb_peak import COULOMB_PEAK

LEVELS: tuple[Level, ...] = (COULOMB_PEAK,)


def get_level(level_id: str) -> Level:
    for level in LEVELS:
        if level.id == level_id:
            return level
    raise KeyError(f"no level {level_id!r}")
