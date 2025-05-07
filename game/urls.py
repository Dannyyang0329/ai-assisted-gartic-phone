from django.urls import path
from . import views

urlpatterns = [
    path('', views.index, name='index'),
    path('check-userid/', views.check_userid_availability, name='check_userid_availability'),
    # 已移除waiting_room和room路徑，因為已經在主urls.py中定義
]
