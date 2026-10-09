"""trainer.routines.register_builtin_routines restores upstream's built-ins."""

import stanza.routines.builtins as builtins
from stanza.routines import clear_routine_registry, get_registered_routines
from trainer.routines import register_builtin_routines


def test_registers_every_builtin_after_registry_is_cleared() -> None:
    clear_routine_registry()
    register_builtin_routines()
    registered = get_registered_routines()
    for name in builtins.__all__:
        assert registered[name] is getattr(builtins, name)


def test_is_idempotent() -> None:
    register_builtin_routines()
    before = get_registered_routines()
    register_builtin_routines()
    assert get_registered_routines() == before


def test_keeps_other_registered_routines() -> None:
    from stanza.routines import routine

    @routine(name="trainer_test_custom")
    def custom() -> None: ...

    register_builtin_routines()
    assert "trainer_test_custom" in get_registered_routines()
