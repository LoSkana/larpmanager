# LarpManager - https://larpmanager.com
# Copyright (C) 2025 Scanagatta Mauro
#
# This file is part of LarpManager and is dual-licensed:
#
# 1. Under the terms of the GNU Affero General Public License (AGPL) version 3,
#    as published by the Free Software Foundation. You may use, modify, and
#    distribute this file under those terms.
#
# 2. Under a commercial license, allowing use in closed-source or proprietary
#    environments without the obligations of the AGPL.
#
# If you have obtained this file under the AGPL, and you make it available over
# a network, you must also make the complete source code available under the same license.
#
# For more information or to purchase a commercial license, contact:
# commercial@larpmanager.com
#
# SPDX-License-Identifier: AGPL-3.0-or-later OR Proprietary
"""Thread-local flag used to suppress side-effectful signal handlers during bulk clones.

This module must stay free of Django imports so it can be imported from
models/signals.py without creating circular imports.
"""

import threading
from collections.abc import Iterator
from contextlib import contextmanager

clone_state = threading.local()


def is_clone_active() -> bool:
    """Return True when the current thread is running a bulk clone."""
    return getattr(clone_state, "active", False)


@contextmanager
def clone_signals_suppressed() -> Iterator[None]:
    """Suppress side-effectful signal handlers (emails, auto setup, accounting recompute) in this thread."""
    clone_state.active = True
    try:
        yield
    finally:
        clone_state.active = False
