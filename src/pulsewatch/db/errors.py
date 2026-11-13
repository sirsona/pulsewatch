"""Storage-layer exceptions translated at the API boundary."""

from __future__ import annotations


class StorageUnavailableError(RuntimeError):
    """The metric store could not be reached or could not complete an operation."""
