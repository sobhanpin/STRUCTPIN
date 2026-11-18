from __future__ import annotations

from dataclasses import dataclass

__all__ = ["StaleState"]


@dataclass(frozen=True)
class StaleState:
    input_change_invalidated: bool = False
    results_stale: bool = False
    stale_error_reported: bool = False

    def input_change_needs_clear(self, has_model: bool) -> bool:
        return has_model or self.results_stale

    def should_notify_clear_failure(self) -> bool:
        return not self.stale_error_reported

    def on_clear_attempt(
        self,
        clear_ok: bool,
        operation_succeeded: bool,
    ) -> "StaleState":
        if not clear_ok:
            return StaleState(
                input_change_invalidated=True,
                results_stale=True,
                stale_error_reported=True,
            )
        if operation_succeeded:
            return StaleState()
        return self

    def on_results_invalidated(self, clear_ok: bool) -> "StaleState":
        if clear_ok:
            return StaleState(
                input_change_invalidated=True,
                results_stale=False,
                stale_error_reported=False,
            )
        return StaleState(
            input_change_invalidated=True,
            results_stale=True,
            stale_error_reported=True,
        )

    def on_analysis_succeeded(self) -> "StaleState":
        return StaleState()
