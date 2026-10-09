"""Access to upstream Stanza's built-in routines.

Upstream registers routines in a process-global registry at import time, and some
callers (upstream's own tests among them) clear that registry. Anything in the
trainer that runs built-ins calls :func:`register_builtin_routines` first, so it
never depends on import order.
"""

import stanza.routines.builtins as builtins
from stanza.routines import routine


def register_builtin_routines() -> None:
    """(Re)register every upstream built-in routine under its own name."""
    for name in builtins.__all__:
        routine(getattr(builtins, name))
