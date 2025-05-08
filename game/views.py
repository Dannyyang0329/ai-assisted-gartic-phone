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
    # 檢查是否有重定向參數
    redirect_room = request.GET.get('redirect_room', '')
    room_type = request.GET.get('room_type', '')
    
    context = {
        'redirect_room': redirect_room,
        'room_type': room_type
    }
    
    return render(request, 'game/index.html', context)

def room(request, room_name):
    # 從URL參數獲取用戶ID
    userid = request.GET.get('userid', '')
    
    # 如果沒有用戶ID或ID不符合要求，重定向到主頁面
    if not userid:
        logger.info(f"room視圖: 未提供用戶ID，重定向到主頁")
        return redirect(f'/?redirect_room={room_name}&room_type=room')
    
    if len(userid) < 3 or len(userid) > 20:
        logger.info(f"room視圖: 用戶ID {userid} 長度不符合要求，重定向到主頁")
        return redirect(f'/?redirect_room={room_name}&room_type=room&error=invalid_length')
    
    # 檢查用戶ID是否已存在
    exists_in_db = User.objects.filter(username=userid).exists()
    exists_in_active = userid in active_guest_ids
    
    if exists_in_db or exists_in_active:
        # 返回首頁並顯示錯誤訊息
        logger.info(f"room視圖: 用戶ID {userid} 已被使用，重定向到主頁")
        return redirect(f'/?error=userid_taken&userid={userid}&redirect_room={room_name}&room_type=room')
    
    # 將用戶ID添加到活躍用戶集合中
    active_guest_ids.add(userid)
    logger.info(f"room視圖: 添加用戶ID {userid}到active_guest_ids, 當前IDs: {active_guest_ids}")
    
    return render(request, 'game/room.html', {
        'room_name': room_name
    })

def waiting_room(request, room_name):
    # 從URL參數獲取用戶ID
    user_id = request.GET.get('userid', '')
    
    # 如果沒有用戶ID或ID不符合要求，重定向到主頁面
    if not user_id:
        logger.info(f"waiting_room視圖: 未提供用戶ID，重定向到主頁")
        return redirect(f'/?redirect_room={room_name}&room_type=waiting_room')
    
    if len(user_id) < 3 or len(user_id) > 20:
        logger.info(f"waiting_room視圖: 用戶ID {user_id} 長度不符合要求，重定向到主頁")
        return redirect(f'/?redirect_room={room_name}&room_type=waiting_room&error=invalid_length')
    
    # 檢查用戶ID是否已存在
    exists_in_db = User.objects.filter(username=user_id).exists()
    exists_in_active = user_id in active_guest_ids
    
    if exists_in_db or exists_in_active:
        # 返回首頁並顯示錯誤訊息
        logger.info(f"waiting_room視圖: 用戶ID {user_id} 已被使用，重定向到主頁")
        return redirect(f'/?error=userid_taken&userid={user_id}&redirect_room={room_name}&room_type=waiting_room')
    
    # 若ID可用，則將其添加到活躍ID集合中
    active_guest_ids.add(user_id)
    logger.info(f"waiting_room: 已添加用戶ID {user_id}, 當前活躍IDs: {active_guest_ids}")
    
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
