from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from .models import Notification

def notify_user(
    *,
    user,
    title,
    description="",
    link="",
    type="info",
    category="system",
    payload=None,
):
    notification = Notification.objects.create(
        user=user,
        title=title,
        description=description,
        link=link,
        type=type,
        category=category,
        payload=payload or {},
    )

    channel_layer = get_channel_layer()

    async_to_sync(channel_layer.group_send)(
        f"user_{user.id}",
        {
            "type": "send_notification",
            "data": {
                "id": notification.id,
                "title": title,
                "description": description,
                "link": link,
                "type": type,
                "category": category,
                "created_at": notification.created_at.isoformat(),
            },
        },
    )

    return notification
