from snipebot.notifications.base import Notifier
from snipebot.notifications.models import NotificationMessage, NotificationResult


class NoopNotifier(Notifier):
    def send(self, message: NotificationMessage) -> NotificationResult:
        return NotificationResult(ok=False, error="notifications_disabled")
