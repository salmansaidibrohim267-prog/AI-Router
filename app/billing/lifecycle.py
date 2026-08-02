from __future__ import annotations

from .exceptions import InvalidTransitionError
from .models import Subscription, SubscriptionStatus


class SubscriptionState:
    """State: one node of the subscription lifecycle state machine."""

    status: SubscriptionStatus

    def allowed_targets(self) -> set[SubscriptionStatus]:
        return set()

    def on_enter(self, subscription: "Subscription") -> None:
        return None

    def can_transition(self, target: SubscriptionStatus) -> bool:
        return target in self.allowed_targets()


class TrialState(SubscriptionState):
    status = SubscriptionStatus.TRIAL

    def allowed_targets(self) -> set[SubscriptionStatus]:
        return {
            SubscriptionStatus.ACTIVE,
            SubscriptionStatus.PAST_DUE,
            SubscriptionStatus.PAUSED,
            SubscriptionStatus.CANCELLED,
        }


class ActiveState(SubscriptionState):
    status = SubscriptionStatus.ACTIVE

    def allowed_targets(self) -> set[SubscriptionStatus]:
        return {
            SubscriptionStatus.PAST_DUE,
            SubscriptionStatus.PAUSED,
            SubscriptionStatus.CANCELLED,
            SubscriptionStatus.TRIAL,
        }


class PastDueState(SubscriptionState):
    status = SubscriptionStatus.PAST_DUE

    def allowed_targets(self) -> set[SubscriptionStatus]:
        return {
            SubscriptionStatus.ACTIVE,
            SubscriptionStatus.CANCELLED,
            SubscriptionStatus.PAUSED,
        }


class PausedState(SubscriptionState):
    status = SubscriptionStatus.PAUSED

    def allowed_targets(self) -> set[SubscriptionStatus]:
        return {
            SubscriptionStatus.ACTIVE,
            SubscriptionStatus.CANCELLED,
        }


class CancelledState(SubscriptionState):
    status = SubscriptionStatus.CANCELLED

    def allowed_targets(self) -> set[SubscriptionStatus]:
        return {SubscriptionStatus.ACTIVE}


class SubscriptionStateFactory:
    """Factory: maps a status to its state object."""

    _registry: dict[SubscriptionStatus, type[SubscriptionState]] = {
        SubscriptionStatus.TRIAL: TrialState,
        SubscriptionStatus.ACTIVE: ActiveState,
        SubscriptionStatus.PAST_DUE: PastDueState,
        SubscriptionStatus.PAUSED: PausedState,
        SubscriptionStatus.CANCELLED: CancelledState,
    }

    @classmethod
    def create(cls, status: SubscriptionStatus | str) -> SubscriptionState:
        if isinstance(status, str):
            status = SubscriptionStatus(status)
        state_cls = cls._registry[status]
        return state_cls()


class SubscriptionLifecycle:
    """State machine driving subscription status transitions."""

    def __init__(self) -> None:
        self._factory = SubscriptionStateFactory

    def state_for(self, status: SubscriptionStatus | str) -> SubscriptionState:
        return self._factory.create(status)

    def allowed_transitions(self, status: SubscriptionStatus | str) -> list[str]:
        state = self.state_for(status)
        return [target.value for target in sorted(state.allowed_targets(), key=lambda s: s.value)]

    def transition(
        self,
        subscription: "Subscription",
        target: SubscriptionStatus | str,
    ) -> Subscription:
        if isinstance(target, str):
            target = SubscriptionStatus(target)
        state = self.state_for(subscription.status)
        if not state.can_transition(target):
            raise InvalidTransitionError(subscription.status.value, target.value)
        subscription.status = target
        state = self.state_for(subscription.status)
        state.on_enter(subscription)
        return subscription
