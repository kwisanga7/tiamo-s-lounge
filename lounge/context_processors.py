from .models import Notification


def notification_summary(request):
    if not request.user.is_authenticated:
        return {"unread_notification_count": 0, "recent_notifications": []}
    notifications = Notification.objects.filter(recipient=request.user)
    return {
        "unread_notification_count": notifications.filter(is_read=False).count(),
        "recent_notifications": notifications[:5],
    }
