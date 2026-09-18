"""Shared pytest fixtures for the spectrafit-core test suite.

Determinism is guaranteed per-test by explicit `np.random.default_rng(seed)` calls,
not a global seed. The previous autouse `enforce_test_seed` fixture only did
`os.environ.setdefault("SPECTRAFIT_TEST_SEED", ...)`, which nothing in the codebase
reads — a no-op — so it was removed (see fix/test-suite-hygiene, T2).
"""

from __future__ import annotations
