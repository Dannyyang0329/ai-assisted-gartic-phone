from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    # 更新 Consumer 名稱
    re_path(r'^ws/game/(?P<room_name>\w+)/$', consumers.GameConsumer.as_asgi()),
    re_path(r'^ws/waiting_room/(?P<room_name>\w+)/$', consumers.WaitingRoomConsumer.as_asgi()),
]
