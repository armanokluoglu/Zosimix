"""The interface every mix engine implements."""

from __future__ import annotations

from abc import ABC, abstractmethod

import numpy as np

from zosimix.mixstate import MixState


class MixEngine(ABC):
    """Holds a song's stems and a current MixState, and renders them.

    The agent's tools never talk to FL or pedalboard directly; they talk to a MixEngine.
    That is what lets the same tools, evals and graders run on either engine.
    """

    sample_rate: int

    @property
    @abstractmethod
    def stem_names(self) -> list[str]: ...

    @abstractmethod
    def get_state(self) -> MixState:
        """A copy of the current mix state."""

    @abstractmethod
    def set_state(self, state: MixState) -> None:
        """Replace the whole mix state. Raises ValueError if it is outside the action space."""

    @abstractmethod
    def render_stems(self) -> dict[str, np.ndarray]:
        """Each stem after its track processing, as (frames, 2) arrays, before summing."""

    def render(self) -> np.ndarray:
        """The full stereo mix, as a (frames, 2) float array. No master processing."""
        stems = self.render_stems()
        length = max(a.shape[0] for a in stems.values())
        out = np.zeros((length, 2))
        for a in stems.values():
            out[: a.shape[0]] += a
        return out
