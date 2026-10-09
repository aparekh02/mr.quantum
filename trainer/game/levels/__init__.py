"""All levels, in play order."""

from trainer.game.level import Level
from trainer.game.levels.compensation import COMPENSATE_SENSOR
from trainer.game.levels.coulomb_peak import COULOMB_PEAK
from trainer.game.levels.double_dot import DOUBLE_DOT

LEVELS: tuple[Level, ...] = (COULOMB_PEAK, COMPENSATE_SENSOR, DOUBLE_DOT)


def get_level(level_id: str) -> Level:
    for level in LEVELS:
        if level.id == level_id:
            return level
    raise KeyError(f"no level {level_id!r}")
