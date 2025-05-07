from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.contrib.auth.models import User
from django.views.decorators.http import require_GET
import logging

# 全局集合來存儲活躍的訪客用戶ID
active_guest_ids = set()

# 設置日誌
logger = logging.getLogger(__name__)

def index(request):
    return render(request, 'game/index.html')

def room(request, room_name):
    # 從URL參數獲取用戶ID
    userid = request.GET.get('userid', '')
    if userid:
        active_guest_ids.add(userid)
        logger.info(f"room視圖: 添加用戶ID {userid}到active_guest_ids, 當前IDs: {active_guest_ids}")
    return render(request, 'game/room.html', {
        'room_name': room_name
    })

def waiting_room(request, room_name):
    # 從URL參數獲取用戶ID
    userid = request.GET.get('userid', '')
    if userid:
        active_guest_ids.add(userid)
        logger.info(f"waiting_room視圖: 添加用戶ID {userid}到active_guest_ids, 當前IDs: {active_guest_ids}")
    return render(request, 'game/waiting_room.html', {
        'room_name': room_name
    })

@require_GET
def check_userid_availability(request):
    """檢查用戶 ID 是否可用"""
    userid = request.GET.get('userid', '')
    
    if not userid:
        return JsonResponse({'available': False, 'message': '請輸入用戶 ID'})
    
    # 檢查長度
    if len(userid) < 3:
        return JsonResponse({'available': False, 'message': '用戶 ID 至少需要 3 個字符'})
    
    if len(userid) > 20:
        return JsonResponse({'available': False, 'message': '用戶 ID 不能超過 20 個字符'})
    
    # 檢查是否已存在於用戶表中
    exists_in_db = User.objects.filter(username=userid).exists()
    
    # 檢查是否已存在於活躍訪客ID中
    exists_in_active = userid in active_guest_ids
    
    logger.info(f"check_userid_availability: 檢查ID {userid}, exists_in_db={exists_in_db}, exists_in_active={exists_in_active}, active_ids={active_guest_ids}")
    
    if exists_in_db or exists_in_active:
        return JsonResponse({'available': False, 'message': '此 ID 已被使用'})
    else:
        return JsonResponse({'available': True, 'message': '此 ID 可用'})
