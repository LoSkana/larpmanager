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
"""Thread-local flag used to defer the Character post_save experience recompute.

Lets a caller that saves related data (e.g. writing question answers) right after
instance.save() suppress the signal's recompute and trigger it once itself, after
that related data is persisted, instead of twice with stale data in between.
"""

import threading
from collections.abc import Iterator
from contextlib import contextmanager

experience_state = threading.local()


def is_experience_recalc_deferred() -> bool:
    """Return True when the current thread has deferred the experience recompute."""
    return getattr(experience_state, "deferred", False)


@contextmanager
def experience_recalc_deferred() -> Iterator[None]:
    """Suppress the Character post_save experience recompute in this thread."""
    experience_state.deferred = True
    try:
        yield
    finally:
        experience_state.deferred = False
