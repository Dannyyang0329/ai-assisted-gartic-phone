import json
import asyncio
import hashlib
import logging
from channels.generic.websocket import AsyncWebsocketConsumer
from collections import defaultdict, deque
import random
from asgiref.sync import sync_to_async
from .views import active_guest_ids  # 導入全局集合

# 添加基本日誌設置
logger = logging.getLogger(__name__)

# 簡易的記憶體內儲存來管理房間狀態
# 注意：這在多個伺服器實例下無法運作，生產環境需要更健壯的方案 (例如 Redis, 資料庫)
game_rooms = {}
waiting_rooms = {}

class WaitingRoomConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.room_name = self.scope['url_route']['kwargs'].get('room_name', 'default')
        room_name_hash = hashlib.md5(self.room_name.encode('utf-8')).hexdigest()
        self.room_group_name = f'waiting_{room_name_hash}'

        query_string = self.scope.get('query_string', b'').decode()
        if 'userid=' in query_string:
            import urllib.parse
            params = dict(urllib.parse.parse_qsl(query_string))
            self.user_id = params.get('userid')
            self.player_id = self.user_id
        
        # 初始化等待房間狀態 (如果不存在)
        if self.room_group_name not in waiting_rooms:
            waiting_rooms[self.room_group_name] = {
                'original_room_name': self.room_name,  # 保存原始房間名稱以供顯示
                'players': {},  # {player_id: {'name': 'PlayerName', 'isBot': False, 'isHost': False}}
                'host_id': self.player_id,  # 第一個加入的玩家為房主
            }

        # 加入房間群組
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )
        await self.accept()

        # 添加玩家到房間狀態
        room = waiting_rooms[self.room_group_name]
        
        # 判斷是否為房主
        is_host = room['host_id'] == self.player_id or not room['players']
        if is_host and not room['players']:
            room['host_id'] = self.player_id  # 確保有房主
        
        # 加入玩家
        room['players'][self.player_id] = {
            'id': self.player_id,
            'name': self.player_id,
            'isBot': False,
            'isHost': is_host
        }
        
        logger.info(f"WaitingRoomConsumer: 玩家 {self.player_id} 已加入房間 {self.room_name}")
        
        # 向所有玩家廣播更新後的狀態
        await self.broadcast_room_state("玩家加入")

    async def disconnect(self, close_code):
        logger.info(f"WaitingRoomConsumer: 玩家 {self.player_id} 斷開連接 - 房間: {self.room_name}")
        room = waiting_rooms.get(self.room_group_name)
        if room:
            # 從房間移除玩家
            if self.player_id in room['players']:
                # 檢查是否為房主
                was_host = room['players'][self.player_id]['isHost']
                # 移除玩家
                del room['players'][self.player_id]
                # 如果房主離開，將房主轉讓給其他人
                if was_host and room['players']:
                    # 選擇第一個非機器人玩家作為新房主
                    for pid, player in room['players'].items():
                        if not player['isBot']:
                            room['host_id'] = pid
                            room['players'][pid]['isHost'] = True
                            break
                
                # 如果房間空了，清理房間狀態
                if not room['players']:
                    del waiting_rooms[self.room_group_name]
                else:
                    # 檢查是否還有真實玩家
                    has_real_player = False
                    for player in room['players'].values():
                        if not player.get('isBot', False):
                            has_real_player = True
                            break
                    
                    # 如果沒有真實玩家，移除所有機器人和房間
                    if not has_real_player:
                        del waiting_rooms[self.room_group_name]
                    else:
                        # 向剩餘玩家廣播狀態
                        await self.broadcast_room_state("玩家離開")

        # 離開房間群組
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )
        
        # 檢查用戶ID
        user_id = getattr(self, 'user_id', None)
        if user_id:
            await self.remove_user_id(user_id)

    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
            message_type = data.get('type')
            payload = data.get('payload', {})
            
            room = waiting_rooms.get(self.room_group_name)
            if not room:
                return

            if message_type == 'chat_message':
                await self.handle_chat_message(payload.get('message', ''))
            elif message_type == 'add_bot':
                await self.handle_add_bot()
            elif message_type == 'remove_bot':
                await self.handle_remove_bot()
            elif message_type == 'start_game':
                await self.handle_start_game()
        except json.JSONDecodeError:
            print(f"Error decoding JSON: {text_data}")
        except Exception as e:
            print(f"Error processing message: {e}")
            import traceback
            traceback.print_exc()

    async def handle_chat_message(self, message):
        if message:
            room = waiting_rooms[self.room_group_name]
            player_name = room['players'].get(self.player_id, {}).get('name', '未知玩家')
            
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'broadcast_message',
                    'message_type': 'chat',
                    'payload': {
                        'sender': player_name,
                        'text': message
                    }
                }
            )

    async def handle_add_bot(self):
        room = waiting_rooms[self.room_group_name]
        
        # 檢查是否為房主
        if room['host_id'] != self.player_id:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'payload': {'message': '只有房主可以添加機器人'}
            }))
            return
            
        # 檢查房間是否已滿
        if len(room['players']) >= 8:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'payload': {'message': '房間已滿'}
            }))
            return
            
        # 計算當前機器人數量用於生成新機器人ID
        bot_count = sum(1 for player in room['players'].values() if player.get('isBot', False))
            
        # 添加機器人
        bot_id = f"bot_{bot_count}"
        bot_name = "畫畫機器人" + str(bot_count)
        room['players'][bot_id] = {
            'id': bot_id,
            'name': bot_name,
            'isBot': True,
            'isHost': False
        }
        
        # 向所有玩家廣播更新後的狀態
        await self.broadcast_room_state("已添加機器人")
        
        # 發送通知
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'broadcast_message',
                'message_type': 'notification',
                'payload': {
                    'message': f"已添加機器人玩家：{bot_name}",
                    'level': 'success'
                }
            }
        )

    async def handle_remove_bot(self):
        room = waiting_rooms[self.room_group_name]
        
        # 檢查是否為房主
        if room['host_id'] != self.player_id:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'payload': {'message': '只有房主可以移除機器人'}
            }))
            return
            
        # 檢查是否有機器人可移除
        bot_players = [player_id for player_id, player in room['players'].items() if player.get('isBot', False)]
        if not bot_players:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'payload': {'message': '沒有機器人可以移除'}
            }))
            return
            
        # 移除最後一個機器人
        bot_to_remove = bot_players[-1]
        bot_name = room['players'][bot_to_remove]['name']
        del room['players'][bot_to_remove]
        
        # 向所有玩家廣播更新後的狀態
        await self.broadcast_room_state("已移除機器人")
        
        # 發送通知
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'broadcast_message',
                'message_type': 'notification',
                'payload': {
                    'message': f"已移除機器人玩家：{bot_name}",
                    'level': 'info'
                }
            }
        )

    async def handle_start_game(self):
        room = waiting_rooms[self.room_group_name]
        
        # 檢查是否為房主
        if room['host_id'] != self.player_id:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'payload': {'message': '只有房主可以開始遊戲'}
            }))
            return
            
        # 檢查玩家數量是否足夠
        if len(room['players']) < 4:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'payload': {'message': '至少需要4名玩家才能開始遊戲'}
            }))
            return
            
        # 設置遊戲房間的初始狀態
        hash_key = hashlib.md5(self.room_name.encode('utf-8')).hexdigest()
        game_room_key = f'game_{hash_key}'
        
        game_rooms[game_room_key] = {
            'original_room_name': self.room_name,
            'players': {},
            'state': 'waiting',
            'prompts': {},
            'books': {},
            'current_round': 0,
            'assignments': {},
            'turn_order': [],
            'total_rounds': len(room['players'])  # 記錄總回合數
        }

        # 將等待室的機器人資訊轉移到遊戲房間
        for player_id, player_data in room['players'].items():
            if player_data.get('isBot', False):
                game_rooms[game_room_key]['players'][player_id] = {
                    'name': player_data['name'],
                    'isBot': True,
                }
        
        # 獲取當前等待室中的所有玩家ID (不包括機器人)
        waiting_room_players = [player_id for player_id, player_data in room['players'].items() if not player_data.get('isBot', False)]
        
        # 通知所有玩家遊戲開始
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'broadcast_message',
                'message_type': 'game_started',
                'payload': {
                    'room_name': self.room_name,
                    # 將所有預計進入遊戲的玩家ID發送給前端
                    'player_ids': waiting_room_players
                }
            }
        )

    async def broadcast_room_state(self, status_message=""):
        """向房間內所有玩家廣播當前的房間狀態"""
        room = waiting_rooms.get(self.room_group_name)
        if not room:
            return

        # 準備要廣播的狀態資訊
        players_list = []
        for player_id, player_data in room['players'].items():
            players_list.append({
                'id': player_id,
                'name': player_data.get('name', f'玩家_{player_id[:4]}'),
                'isBot': player_data.get('isBot', False),
                'isHost': player_data.get('isHost', False)
            })

        # 計算機器人數量
        bot_count = sum(1 for player in room['players'].values() if player.get('isBot', False))

        state_payload = {
            'players': players_list,
            'bot_count': bot_count,  # 保留bot_count以向後兼容，但現在是從players計算出來的
            'status_message': status_message,
        }

        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'broadcast_message',
                'message_type': 'room_update',
                'payload': state_payload
            }
        )

    async def broadcast_message(self, event):
        """處理來自 group_send 的廣播請求"""
        message_type = event['message_type']
        payload = event['payload']
        
        await self.send(text_data=json.dumps({
            'type': message_type,
            'payload': payload
        }))

    @sync_to_async
    def remove_user_id(self, user_id):
        """從活躍用戶集合中移除用戶ID"""
        if user_id in active_guest_ids:
            active_guest_ids.remove(user_id)
    
    @sync_to_async
    def add_user_id(self, user_id):
        """添加用戶ID到活躍集合"""
        active_guest_ids.add(user_id)

class GameConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.room_name = self.scope['url_route']['kwargs'].get('room_name', 'default')
        room_name_hash = hashlib.md5(self.room_name.encode('utf-8')).hexdigest()
        self.room_group_name = f'game_{room_name_hash}'

        query_string = self.scope.get('query_string', b'').decode()
        if 'userid=' in query_string:
            import urllib.parse
            params = dict(urllib.parse.parse_qsl(query_string))
            self.user_id = params.get('userid')
            self.player_id = self.user_id

        # 加入房間群組
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )
        await self.accept()
        
        # 獲取房間狀態
        room = game_rooms.get(self.room_group_name)
        
        # 添加玩家到房間 (如果不存在)
        if room and self.player_id not in room['players']:
            room['players'][self.player_id] = {
                'name': self.player_id,
                'isBot': False
            }
            logger.info(f"GameConsumer: 玩家 {self.player_id} 已加入遊戲房間 {self.room_group_name}")
        
        # 廣播更新的遊戲狀態
        if room:
            await self.broadcast_game_state("玩家已連接")
        
        # 確保用戶ID加入活躍集合 
        if self.user_id:
            await self.add_user_id(self.user_id)

    async def disconnect(self, close_code):
        logger.info(f"GameConsumer: WebSocket斷開連接 - player_id: {self.player_id}, user_id: {getattr(self, 'user_id', None)}")
        room = game_rooms.get(self.room_group_name)
        if room:
            # 標記玩家為斷線或直接移除
            if self.player_id in room['players']:
                # room['players'][self.player_id]['connected'] = False
                del room['players'][self.player_id] # 簡單起見，直接移除
                print(f"Player {self.player_id} disconnected from {self.room_group_name}. Remaining players: {room['players']}")

            # 如果房間空了，可以考慮清理房間狀態
            if not room['players']:
                del game_rooms[self.room_group_name]
                print(f"Room {self.room_group_name} closed.")
            else:
                 # 向剩餘玩家廣播狀態
                 # TODO: 需要處理遊戲進行中玩家離開的情況
                 await self.broadcast_game_state("玩家離開")

        # 離開房間群組
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )
        
        # 使用更健壯的方式檢查用戶ID
        user_id = getattr(self, 'user_id', None)
        if user_id:
            await self.remove_user_id(user_id)

    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
            message_type = data.get('type')
            payload = data.get('payload', {})

            room = game_rooms.get(self.room_group_name)
            if not room:
                logger.warning(f"GameConsumer: 房間 {self.room_group_name} 不存在，但收到訊息類型 {message_type}")
                return

            print(f"GameConsumer: Received message type: {message_type} from {self.player_id} in {self.room_name}")

            if message_type == 'chat_message':
                await self.handle_chat_message(payload.get('message', ''))
            elif message_type == 'start_game':
                await self.handle_start_game()
            elif message_type == 'submit_prompt':
                await self.handle_submit_prompt(payload.get('prompt'))
            elif message_type == 'submit_drawing':
                await self.handle_submit_drawing(payload.get('drawing'))
            elif message_type == 'submit_guess':
                await self.handle_submit_guess(payload.get('guess'))
            elif message_type == 'clear_canvas': # 處理清除畫布請求
                await self.handle_clear_canvas()
            elif message_type == 'user_info': # 處理用戶信息
                # 即使移除了登入系統，我們仍然可以允許客戶端發送一個顯示名稱
                player_display_name = payload.get('displayName', room['players'].get(self.player_id, {}).get('name'))
                if self.player_id in room['players']:
                    room['players'][self.player_id]['name'] = player_display_name
                    await self.broadcast_game_state(f"玩家 {player_display_name} 已更新名稱")
                # 保存用戶ID
                self.user_id = payload.get('username')
                logger.info(f"GameConsumer: 設置user_id為: {self.user_id}")
                # 確保用戶ID加入活躍集合
                if self.user_id and self.user_id not in active_guest_ids:
                    await self.add_user_id(self.user_id)
            # 可以添加其他訊息類型處理

        except json.JSONDecodeError:
            print(f"Error decoding JSON: {text_data}")
        except Exception as e:
            print(f"Error processing message: {e}")
            import traceback
            traceback.print_exc()

    async def handle_start_game(self):
        """初始化遊戲並開始第一輪"""
        room = game_rooms[self.room_group_name]
        
        # 設置遊戲基本參數
        players_count = len(room['players'])
            
        # 確定玩家順序
        room['turn_order'] = list(room['players'].keys())
        random.shuffle(room['turn_order'])  # 隨機打亂順序
        
        # 初始化每個玩家的故事本
        for player_id in room['turn_order']:
            room['books'][player_id] = []
        
        # 設置遊戲輪數 (不添加機器人，使用實際玩家數量)
        room['current_round'] = 0
        room['total_rounds'] = players_count
        
        # 進入提示輸入階段
        await self.start_prompting_round()
        
        return True

    async def start_prompting_round(self):
        """開始提示輸入階段"""
        room = game_rooms[self.room_group_name]
        room['state'] = 'prompting'
        room['assignments'] = {}  # 清空上一輪的任務
        
        print(f"開始提示輸入階段")
        
        # 為每個玩家分配提示輸入任務
        for player_id in room['turn_order']:
            room['assignments'][player_id] = {'type': 'prompt'}
            
            # 單獨發送提示請求給指定玩家
            await self.channel_layer.send(
                player_id,
                {
                    'type': 'send_message',
                    'message_type': 'request_prompt',
                    'payload': {}
                }
            )
        
        # 廣播更新遊戲狀態
        await self.broadcast_game_state("請每位玩家輸入一個有趣的題目或短語作為開始！")

    async def handle_submit_prompt(self, prompt_text):
        """處理玩家提交的題目"""
        room = game_rooms[self.room_group_name]
        
        if room['state'] != 'prompting' or self.player_id not in room['assignments']:
            await self.send_message('error', {'message': '現在不是提交題目的時間或您已經提交過題目'})
            return
        
        # 從待處理任務中移除此玩家
        room['assignments'].pop(self.player_id)
        
        # 將題目添加到該玩家的書本中
        room['books'][self.player_id].append({
            'type': 'prompt',
            'data': prompt_text,
            'player': self.player_id,
            'round': 0
        })
        
        # 發送確認消息
        await self.send_message('notification', {
            'message': '您的題目已提交！',
            'level': 'success'
        })
        
        # 檢查是否所有玩家都已提交題目
        if not room['assignments']:
            print(f"所有題目已提交，開始第一輪繪畫階段...")
            await self.start_drawing_round()
        else:
            # 更新等待狀態
            await self.broadcast_game_state(f"等待其他 {len(room['assignments'])} 位玩家提交題目...")

    async def start_drawing_round(self):
        """開始一輪繪畫階段"""
        room = game_rooms[self.room_group_name]
        room['state'] = 'drawing'
        room['current_round'] += 1
        room['assignments'] = {}  # 清空上一輪的任務

        num_players = len(room['turn_order'])
        
        print(f"開始繪畫階段 - 回合 {room['current_round']}")

        # 為每位玩家分配繪畫任務
        for i, current_player_id in enumerate(room['turn_order']):
            # 計算要畫哪個玩家的故事本 (輪轉)
            # 玩家 i 畫玩家 (i+當前回合)%玩家數 的故事本中最後一個元素
            target_book_index = (i + room['current_round']) % num_players
            original_player_id = room['turn_order'][target_book_index]
            book = room['books'][original_player_id]

            if not book:
                print(f"錯誤: 玩家 {original_player_id} 的故事本為空!")
                continue

            # 獲取需要繪畫的內容 (上一步的題目或猜測)
            item_to_draw = book[-1]
            if item_to_draw['type'] not in ['prompt', 'guess']:
                print(f"錯誤: 需要題目或猜測作為繪畫依據，但收到了 {item_to_draw['type']} (來自故事本 {original_player_id})")
                continue

            # 創建繪畫任務
            task_data = {
                'type': 'draw',
                'prompt_or_guess': item_to_draw['data'],
                'original_player_id': original_player_id  # 追蹤這個繪畫屬於哪個故事本
            }
            room['assignments'][current_player_id] = task_data  # 儲存分配給玩家的任務

            # 單獨發送繪畫請求給指定玩家
            await self.channel_layer.send(
                current_player_id,
                {
                    'type': 'send_message',
                    'message_type': 'request_drawing',
                    'payload': {
                        'prompt_or_guess': item_to_draw['data'],
                        'original_player': original_player_id,
                        'round': room['current_round']
                    }
                }
            )
        
        # 廣播更新遊戲狀態
        await self.broadcast_game_state("繪畫階段開始！請根據分配給您的題目進行創意繪畫。")

    async def handle_submit_drawing(self, drawing_data):
        """處理玩家提交的繪畫"""
        room = game_rooms[self.room_group_name]

        if room['state'] != 'drawing' or self.player_id not in room['assignments']:
            await self.send_message('error', {'message': '現在不是繪畫階段或您已經提交過繪畫'})
            return
        
        # 獲取並移除已完成的任務
        task = room['assignments'].pop(self.player_id)
        original_player_id = task['original_player_id']

        # 將繪畫加入對應的故事本
        room['books'][original_player_id].append({
            'type': 'drawing', 
            'data': drawing_data, 
            'player': self.player_id,
            'round': room['current_round']
        })
        print(f"玩家 {self.player_id} 為故事本 {original_player_id} 提交了繪畫")

        # 發送確認消息
        await self.send_message('notification', {
            'message': '您的繪畫已提交！',
            'level': 'success'
        })

        # 檢查是否所有繪畫都已提交
        if not room['assignments']:
            print(f"回合 {room['current_round']} 的所有繪畫已提交，進入猜測階段")
            await self.start_guessing_round()
        else:
            # 更新等待狀態
            await self.broadcast_game_state(f"等待其他 {len(room['assignments'])} 位玩家完成繪畫...")

    async def start_guessing_round(self):
        """開始一輪猜測階段"""
        room = game_rooms[self.room_group_name]
        room['state'] = 'guessing'
        room['assignments'] = {}  # 清空上一輪的任務

        num_players = len(room['turn_order'])
        
        print(f"開始猜測階段 - 回合 {room['current_round']}")

        # 為每位玩家分配猜測任務
        for i, current_player_id in enumerate(room['turn_order']):
            # 計算要猜測哪個玩家的故事本
            # 玩家 i 猜測玩家 (i+當前回合)%玩家數 的故事本中的最新繪畫
            target_book_index = (i + room['current_round']) % num_players
            original_player_id = room['turn_order'][target_book_index]
            book = room['books'][original_player_id]

            if not book:
                print(f"錯誤: 玩家 {original_player_id} 的故事本為空!")
                continue

            # 獲取需要猜測的繪畫 (最新的元素)
            item_to_guess = book[-1]
            if item_to_guess['type'] != 'drawing':
                print(f"錯誤: 需要繪畫作為猜測對象，但收到了 {item_to_guess['type']} (來自故事本 {original_player_id})")
                continue

            # 創建猜測任務
            task_data = {
                'type': 'guess',
                'drawing_data': item_to_guess['data'],
                'original_player_id': original_player_id  # 追蹤這個猜測屬於哪個故事本
            }
            room['assignments'][current_player_id] = task_data

            # 單獨發送猜測請求給指定玩家
            await self.channel_layer.send(
                current_player_id,
                {
                    'type': 'send_message',
                    'message_type': 'request_guess',
                    'payload': {
                        'drawing_data': item_to_guess['data'],
                        'original_player': original_player_id,
                        'round': room['current_round']
                    }
                }
            )
        
        # 廣播更新遊戲狀態
        await self.broadcast_game_state("猜測階段開始！請猜猜看您看到的繪畫代表什麼？")

    async def handle_submit_guess(self, guess_text):
        """處理玩家提交的猜測"""
        room = game_rooms[self.room_group_name]

        if room['state'] != 'guessing' or self.player_id not in room['assignments']:
            await self.send_message('error', {'message': '現在不是猜測階段或您已經提交過猜測'})
            return
        
        # 獲取並移除已完成的任務
        task = room['assignments'].pop(self.player_id)
        original_player_id = task['original_player_id']

        # 將猜測加入對應的故事本
        room['books'][original_player_id].append({
            'type': 'guess', 
            'data': guess_text, 
            'player': self.player_id,
            'round': room['current_round']
        })
        print(f"玩家 {self.player_id} 為故事本 {original_player_id} 提交了猜測")

        # 發送確認消息
        await self.send_message('notification', {
            'message': '您的猜測已提交！',
            'level': 'success'
        })

        # 檢查是否所有猜測都已提交
        if not room['assignments']:
            # 檢查是否達到遊戲結束條件
            num_players = len(room['turn_order'])
            if room['current_round'] >= num_players - 1:
                # 遊戲結束
                await self.finish_game()
            else:
                # 進入下一輪繪畫階段
                print(f"回合 {room['current_round']} 的所有猜測已提交，進入下一輪繪畫")
                await self.start_drawing_round()
        else:
            # 更新等待狀態
            await self.broadcast_game_state(f"等待其他 {len(room['assignments'])} 位玩家完成猜測...")

    async def finish_game(self):
        """結束遊戲並展示結果"""
        room = game_rooms[self.room_group_name]
        room['state'] = 'finished'
        
        # 確保每個故事本的完整性
        for player_id, book in room['books'].items():
            player_name = room['players'][player_id]['name']
            book_length = len(book)
            expected_length = len(room['turn_order'])
            
            print(f"玩家 {player_name} 的故事本有 {book_length} 個項目，期望有 {expected_length} 個")
            
            # 檢查故事本是否完整 (每個故事本應該有N個項目，包含1個題目、(N-1)/2個繪畫和(N-1)/2個猜測)
            if book_length != expected_length:
                print(f"警告: 玩家 {player_name} 的故事本不完整")

        # 發送遊戲結束消息，包含所有故事本數據
        result_payload = {
            'players': room['players'],
            'books': room['books'],
            'turn_order': room['turn_order']
        }

        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'send_message',
                'message_type': 'game_over',
                'payload': result_payload
            }
        )

        await self.broadcast_game_state("遊戲結束！請查看每本故事的演變過程。")
        print("遊戲結束，已發送結果")

    async def broadcast_game_state(self, status_message=""):
        """向房間內所有玩家廣播當前的遊戲狀態"""
        room = game_rooms.get(self.room_group_name)
        if not room:
            return

        # 準備要廣播的狀態資訊
        state_payload = {
            'state': room['state'],
            'players': room['players'],
            'current_round': room['current_round'],
            'status_message': status_message,
            # 只提供誰還沒完成的信息，不包含任務內容
            'waiting_on': list(room.get('assignments', {}).keys()),
            'turn_order': room.get('turn_order', []),
            # 新增總輪數信息
            'total_rounds': len(room.get('turn_order', [])) - 1 if room.get('turn_order') else 0
        }

        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'send_message',
                'message_type': 'game_state_update',
                'payload': state_payload
            }
        )

    async def handle_clear_canvas(self):
         # 只廣播給同一個房間的其他玩家，不包括自己
         await self.channel_layer.group_send(
             self.room_group_name,
             {
                 'type': 'broadcast_message',
                 'message_type': 'clear_canvas_instruction',
                 'payload': {},
                 'sender_channel': self.channel_name # 告訴廣播函數不要發給自己
             }
         )

    async def start_drawing_round(self):
        room = game_rooms[self.room_group_name]
        room['state'] = 'drawing'
        room['current_round'] += 1
        room['assignments'] = {} # 清空上一輪的任務

        num_players = len(room['turn_order'])
        current_assignments = {}

        print(f"Starting drawing round {room['current_round']}")

        for i, current_player_id in enumerate(room['turn_order']):
            # 計算要畫哪個玩家的故事本 (輪轉)
            # 第 1 輪 (round=1): 玩家 i 畫玩家 (i+1)%N 的題目
            # 第 2 輪 (round=2): 玩家 i 畫玩家 (i+2)%N 的猜測 (來自玩家 (i+1)%N 的繪畫)
            # ...
            # 第 k 輪 (round=k): 玩家 i 畫玩家 (i+k)%N 的上一個元素
            target_book_index = (i + room['current_round']) % num_players
            original_player_id = room['turn_order'][target_book_index]
            book = room['books'][original_player_id]

            if not book:
                print(f"Error: Book for {original_player_id} is empty!")
                continue # 理論上不應發生

            # 獲取需要繪畫的內容 (上一步的題目或猜測)
            item_to_draw = book[-1]
            if item_to_draw['type'] not in ['prompt', 'guess']:
                 print(f"Error: Expected prompt or guess for drawing, got {item_to_draw['type']} for book {original_player_id}")
                 # 可能需要更複雜的邏輯來處理錯誤或跳過
                 continue

            task_data = {
                'type': 'draw',
                'prompt_or_guess': item_to_draw['data'],
                'original_player_id': original_player_id # 追蹤這個繪畫屬於哪個故事本
            }
            room['assignments'][current_player_id] = task_data # 儲存分配給玩家的任務

            # 單獨發送繪畫請求給指定玩家
            await self.channel_layer.send(
                current_player_id,
                {
                    'type': 'send_message', # 需要一個 consumer 方法來處理這個類型
                    'message_type': 'request_drawing',
                    'payload': task_data
                }
            )
            print(f"Assigned drawing task to {current_player_id}: Draw '{item_to_draw['data']}' from book {original_player_id}")


        await self.broadcast_game_state(f"第 {room['current_round']} 輪 - 請開始繪畫！")

    async def start_guessing_round(self):
        room = game_rooms[self.room_group_name]
        room['state'] = 'guessing'
        # current_round 不需要增加，因為猜測是跟隨繪畫輪次的
        room['assignments'] = {} # 清空上一輪的任務

        num_players = len(room['turn_order'])
        current_assignments = {}

        print(f"Starting guessing round for drawing round {room['current_round']}")

        for i, current_player_id in enumerate(room['turn_order']):
            # 計算要猜哪個玩家的故事本 (輪轉)
            # 玩家 i 猜測由玩家 (i-1)%N 根據玩家 (i+round-1)%N 的內容畫出的圖
            # 也就是說，玩家 i 猜測玩家 (i + room['current_round']) % num_players 的故事本中的最新繪畫
            target_book_index = (i + room['current_round']) % num_players
            original_player_id = room['turn_order'][target_book_index]
            book = room['books'][original_player_id]

            if not book:
                print(f"Error: Book for {original_player_id} is empty!")
                continue

            # 獲取需要猜測的繪畫 (最新的元素)
            item_to_guess = book[-1]
            if item_to_guess['type'] != 'drawing':
                print(f"Error: Expected drawing for guessing, got {item_to_guess['type']} for book {original_player_id}")
                continue

            task_data = {
                'type': 'guess',
                'drawing_data': item_to_guess['data'],
                'original_player_id': original_player_id
            }
            room['assignments'][current_player_id] = task_data

            # 單獨發送猜測請求給指定玩家
            await self.channel_layer.send(
                current_player_id,
                {
                    'type': 'send_message',
                    'message_type': 'request_guess',
                    'payload': task_data
                }
            )
            print(f"Assigned guessing task to {current_player_id}: Guess drawing from book {original_player_id}")


        await self.broadcast_game_state(f"第 {room['current_round']} 輪 - 請根據繪畫猜測！")

    async def finish_game(self):
        room = game_rooms[self.room_group_name]
        room['state'] = 'finished'
        print(f"Game finished in room {self.room_group_name}")

        # 向所有玩家廣播最終結果
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'broadcast_message',
                'message_type': 'game_over',
                'payload': {
                    'books': room['books'],
                    'players': room['players'], # 包含玩家名稱等資訊
                    'turn_order': room['turn_order']
                 }
            }
        )
        await self.broadcast_game_state("遊戲結束！查看結果。")
        # 可以考慮一段時間後重置房間狀態回 waiting

    async def broadcast_game_state(self, status_message=""):
        """向房間內所有玩家廣播當前的遊戲狀態"""
        room = game_rooms.get(self.room_group_name)
        if not room:
            return

        # 準備要廣播的狀態資訊 (移除敏感或過大的資料)
        state_payload = {
            'state': room['state'],
            'players': room['players'],
            'current_round': room['current_round'],
            'status_message': status_message,
            # 可以選擇性加入 assignments 的 key (誰還沒完成) 但不含內容
            'waiting_on': list(room.get('assignments', {}).keys()),
            'turn_order': room.get('turn_order', [])
        }

        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'broadcast_message',
                'message_type': 'game_state_update',
                'payload': state_payload
            }
        )

    async def broadcast_message(self, event):
        """處理來自 group_send 的廣播請求"""
        message_type = event['message_type']
        payload = event['payload']
        sender_channel = event.get('sender_channel') # 獲取發送者 channel

        # 如果是清除畫布指令，且當前接收者不是發送者，才發送
        if message_type == 'clear_canvas_instruction':
            if self.channel_name != sender_channel:
                 await self.send(text_data=json.dumps({
                     'type': message_type,
                     'payload': payload
                 }))
        else:
            # 其他廣播訊息正常發送給所有 group 成員
            # (包括 game_state_update, request_prompt, game_over 等)
            # Removed 'chat' from the comment as it's no longer handled here for game_room
             await self.send(text_data=json.dumps({
                 'type': message_type,
                 'payload': payload
             }))

    async def send_message(self, event):
        """處理來自 channel_layer.send 的單獨發送請求"""
        message_type = event['message_type']
        payload = event['payload']
        await self.send(text_data=json.dumps({
            'type': message_type,
            'payload': payload
        }))

    @sync_to_async
    def remove_user_id(self, user_id):
        """從活躍用戶集合中移除用戶ID"""
        if user_id in active_guest_ids:
            active_guest_ids.remove(user_id)
            logger.info(f"GameConsumer: 已移除用戶ID {user_id}, 當前活躍IDs: {active_guest_ids}")
        else:
            logger.warning(f"GameConsumer: 嘗試移除不存在的用戶ID {user_id}, 當前活躍IDs: {active_guest_ids}")
            
    @sync_to_async
    def add_user_id(self, user_id):
        """添加用戶ID到活躍集合"""
        active_guest_ids.add(user_id)
        logger.info(f"GameConsumer: 已添加用戶ID {user_id}, 當前活躍IDs: {active_guest_ids}")
