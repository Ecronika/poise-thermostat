from __future__ import annotations

import pytest

from custom_components.poise.clock import ManualClock


@pytest.fixture
def clock() -> ManualClock:
    return ManualClock()
