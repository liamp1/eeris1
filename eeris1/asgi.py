import os
from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
import receipts.routing  # adjust if your app name is different

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'eeris1.settings')

application = ProtocolTypeRouter({
    "http": get_asgi_application(),
    "websocket": AuthMiddlewareStack(
        URLRouter(
            receipts.routing.websocket_urlpatterns
        )
    ),
})