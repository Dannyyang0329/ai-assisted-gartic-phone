"""
ASGI config for gartic_project project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/5.2/howto/deployment/asgi/
"""

import os
from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
import game.routing # 確保導入了 game.routing

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'gartic_project.settings')

# django_asgi_app = get_asgi_application() # 如果在下面使用，先獲取

application = ProtocolTypeRouter({
    "http": get_asgi_application(), # 直接調用
    "websocket": AuthMiddlewareStack(
        URLRouter(
            game.routing.websocket_urlpatterns # 使用 game.routing 中的路由
        )
    ),
})
print("--- ASGI application configured ---") # <--- 加入這行
