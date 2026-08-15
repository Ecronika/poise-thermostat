from __future__ import annotations

import os

import pytest
from hypothesis import HealthCheck, Phase, settings

from custom_components.poise.clock import ManualClock

# F.5: property-based testing must never make the gate flaky or slow.
#
# "ci" is DERANDOMISED: the same examples run on every commit, so a red build
# is reproducible from the commit alone and a green one means the same thing
# twice. Shrinking stays on (a failure must be reported minimally), the
# example database is off (CI has no writable, persistent .hypothesis).
# "dev" is the local profile: more examples and the database on, so replaying
# a previously found counter-example is instant.
settings.register_profile(
    "ci",
    max_examples=200,
    derandomize=True,
    database=None,
    deadline=None,  # coverage/CI machines are too jittery for per-example timing
    print_blob=True,  # a failure prints the @reproduce_failure blob
    suppress_health_check=[HealthCheck.too_slow],
    phases=[Phase.explicit, Phase.reuse, Phase.generate, Phase.target, Phase.shrink],
)
settings.register_profile("dev", max_examples=500, deadline=None, print_blob=True)
settings.load_profile(os.environ.get("HYPOTHESIS_PROFILE", "ci"))


@pytest.fixture
def clock() -> ManualClock:
    return ManualClock()
