import json
import asyncio
import hashlib
import logging
from channels.generic.websocket import AsyncWebsocketConsumer
from collections import defaultdict, deque
import random
from asgiref.sync import sync_to_async
from .views import active_guest_ids  # 導入全局集合
import math # Add math import for ceil

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
        
        if room['host_id'] != self.player_id:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'payload': {'message': '只有房主可以開始遊戲'}
            }))
            return
            
        num_actual_players = len([p for p in room['players'].values() if not p.get('isBot', False)])
        if num_actual_players < 2: # 至少需要2名人類玩家才能開始遊戲 (例如，2人遊戲，N=2, N-1=1輪操作)
                                 # 根據使用者描述，N至少為2。如果N=2, 總共2個條目，1次繪畫。
                                 # 如果N=3, 總共3個條目，1畫1猜。
                                 # 遊戲至少需要2人。
            await self.send(text_data=json.dumps({
                'type': 'error',
                'payload': {'message': '至少需要2名玩家才能開始遊戲'}
            }))
            return
            
        hash_key = hashlib.md5(self.room_name.encode('utf-8')).hexdigest()
        game_room_key = f'game_{hash_key}'
        
        # 獲取當前等待室中的所有玩家ID (包括機器人)
        # turn_order 將在 GameConsumer 中確定，這裡只傳遞所有參與者
        all_player_ids_in_order = list(room['players'].keys()) # 保持加入順序或由 GameConsumer 處理順序

        # 創建遊戲房間實例
        game_rooms[game_room_key] = {
            'room_name': self.room_name,
            'players': dict(room['players']), # 複製玩家資訊
            'host_id': room['host_id'],
            'turn_order': all_player_ids_in_order, # GameConsumer 將使用這個順序
            'state': 'initializing',
            'current_op_number': 0,
            'total_ops': len(all_player_ids_in_order) - 1 if len(all_player_ids_in_order) > 0 else 0,
            'current_display_round': 0,
            'total_display_rounds': math.ceil((len(all_player_ids_in_order) - 1) / 2.0) if len(all_player_ids_in_order) > 1 else 0,
            'books': {player_id: [] for player_id in all_player_ids_in_order},
            'assignments': {},
            'game_log': []
        }
        print(f"Game room {game_room_key} created with players: {all_player_ids_in_order}")
        print(f"Total ops: {game_rooms[game_room_key]['total_ops']}, Total display rounds: {game_rooms[game_room_key]['total_display_rounds']}")


        # 通知所有玩家遊戲開始，並傳遞遊戲房間的 key (room_name)
        await self.channel_layer.group_send(
            self.room_group_name, # 仍然發送到 waiting_room group
            {
                'type': 'broadcast_message', # WaitingRoomConsumer 需要有 broadcast_message 方法
                'message_type': 'game_started',
                'payload': {
                    'room_name': self.room_name, # 前端將使用此 room_name 導航到 /room/<room_name>
                    'player_ids': all_player_ids_in_order # 可選，前端可能不需要
                }
            }
        )
        
        # 清理等待室 (可選，或者讓其自然過期)
        # del waiting_rooms[self.room_group_name]

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

        # 檢查遊戲房間是否存在 (由 WaitingRoomConsumer 創建)
        if self.room_group_name not in game_rooms:
            print(f"Game room {self.room_group_name} not found. Disconnecting.")
            await self.close()
            return

        room = game_rooms[self.room_group_name]
        
        # 確保玩家是該房間的一員
        if self.player_id not in room['players']:
            print(f"Player {self.player_id} not in room {self.room_group_name}. Disconnecting.")
            await self.close()
            return

        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )
        await self.accept()
        
        # 更新玩家的 channel_name，用於私訊
        room['players'][self.player_id]['channel_name'] = self.channel_name
        
        print(f"Player {self.player_id} connected to game room {self.room_name} (channel: {self.channel_name})")

        # 如果所有玩家都已連接，房主可以開始遊戲 (或者自動開始)
        # 此處的邏輯是，前端連接後會發送 'start_game' 訊息
        # 我們也可以在這裡檢查是否所有 turn_order 中的玩家都已連接 (都有 channel_name)
        # 然後自動觸發遊戲開始，而不是等待前端的 'start_game'
        
        # 發送初始遊戲狀態給剛連接的玩家
        await self.send_game_state_to_player(self.player_id, "成功加入遊戲房間！")

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
        """
        (此方法被前端的 'start_game' 訊息觸發後的內部調用取代)
        現在由 receive -> start_prompting_round 直接觸發
        """
        room = game_rooms[self.room_group_name]
        if room['state'] == 'initializing': # 確保只初始化一次
            # 可選：打亂玩家順序
            # random.shuffle(room['turn_order'])
            # print(f"Turn order for room {self.room_name}: {room['turn_order']}")
            await self.start_prompting_round()

    async def start_prompting_round(self):
        """開始提示輸入階段"""
        room = game_rooms[self.room_group_name]
        if room['state'] != 'initializing':
            return # 防止重複開始

        room['state'] = 'prompting'
        room['current_op_number'] = 0 # 題目階段是操作0
        room['current_display_round'] = 0 # 題目階段顯示為回合0或不顯示回合
        room['assignments'] = {player_id: {'type': 'prompt'} for player_id in room['turn_order']}
        
        print(f"Room {self.room_name}: Starting prompting round.")
        await self.broadcast_game_state("請所有玩家提交一個有趣的題目！")
        
        # 可以為每個玩家單獨發送 assign_prompt 指令，如果需要的話
        for player_id in room['turn_order']:
            if room['players'][player_id].get('channel_name'):
                await self.channel_layer.send(
                    room['players'][player_id]['channel_name'],
                    {
                        'type': 'send_message', # GameConsumer 方法
                        'message_type': 'assign_prompt', # 前端識別的類型
                        'payload': {} 
                    }
                )

    async def handle_submit_prompt(self, prompt_text):
        room = game_rooms[self.room_group_name]

        if room['state'] != 'prompting':
            await self.send_error("現在不是提交題目的階段。")
            return
        if self.player_id not in room['assignments'] or room['assignments'][self.player_id]['type'] != 'prompt':
            await self.send_error("您沒有被分配提交題目或已提交。")
            return
        if not prompt_text or len(prompt_text.strip()) == 0:
            await self.send_error("題目不能為空。")
            return

        room['assignments'].pop(self.player_id)
        room['books'][self.player_id].append({
            'type': 'prompt',
            'data': prompt_text,
            'player': self.player_id, # 題目由自己提出
            'round': 0 # 初始題目定義為 round 0
        })
        print(f"Player {self.player_id} submitted prompt: {prompt_text}")

        await self.send_notification('您的題目已提交！', 'success')

        if not room['assignments']: # 所有人都提交完畢
            print(f"Room {self.room_name}: All prompts submitted. Starting first operation.")
            await self.start_next_operation()
        else:
            await self.broadcast_game_state(f"等待其他 {len(room['assignments'])} 位玩家提交題目...")

    async def start_next_operation(self):
        room = game_rooms[self.room_group_name]
        room['current_op_number'] += 1
        op_num = room['current_op_number']
        
        num_players = len(room['turn_order'])

        if op_num > room['total_ops']:
            print(f"Room {self.room_name}: All operations completed. Finishing game.")
            await self.finish_game()
            return

        is_drawing_op = (op_num % 2 == 1)
        room['current_display_round'] = math.ceil(op_num / 2.0)
        
        current_assignments = {}
        action_type = 'draw' if is_drawing_op else 'guess'
        next_state = 'drawing' if is_drawing_op else 'guessing'
        room['state'] = next_state

        print(f"Room {self.room_name}: Starting Op# {op_num} (Display Round {room['current_display_round']}) - Type: {next_state}")

        for i, current_player_id in enumerate(room['turn_order']):
            # 玩家 current_player_id (索引 i) 操作的書本是來自 (i - op_num) 的玩家
            book_owner_index = (i - op_num % num_players + num_players) % num_players
            original_book_owner_id = room['turn_order'][book_owner_index]
            
            book_content = room['books'][original_book_owner_id]
            if not book_content:
                print(f"Error: Book for {original_book_owner_id} is empty for Op# {op_num} by {current_player_id}!")
                # This should not happen if prompting was successful
                continue 
            
            item_to_process = book_content[-1] # Get the last item (prompt, drawing, or guess)

            task_payload = {
                'original_player_id': original_book_owner_id,
                'ui_round': room['current_display_round']
            }
            client_message_payload = {
                'original_player': original_book_owner_id, # For client display
                'round': room['current_display_round']
            }

            if is_drawing_op:
                if item_to_process['type'] not in ['prompt', 'guess']:
                    print(f"Error: Expected prompt or guess for drawing, got {item_to_process['type']}")
                    continue
                task_payload['type'] = 'draw'
                task_payload['prompt_or_guess'] = item_to_process['data']
                client_message_payload['prompt_or_guess'] = item_to_process['data']
                client_message_type = 'request_drawing'
            else: # Guessing Op
                if item_to_process['type'] != 'drawing':
                    print(f"Error: Expected drawing for guessing, got {item_to_process['type']}")
                    continue
                task_payload['type'] = 'guess'
                task_payload['drawing_data'] = item_to_process['data']
                client_message_payload['drawing_data'] = item_to_process['data']
                client_message_type = 'request_guess'

            current_assignments[current_player_id] = task_payload
            
            if room['players'][current_player_id].get('channel_name'):
                await self.channel_layer.send(
                    room['players'][current_player_id]['channel_name'],
                    {
                        'type': 'send_message',
                        'message_type': client_message_type,
                        'payload': client_message_payload
                    }
                )
            print(f"Assigned task to {current_player_id}: {task_payload['type']} for book {original_book_owner_id} (Op# {op_num})")

        room['assignments'] = current_assignments
        await self.broadcast_game_state(f"第 {room['current_display_round']} 回合 - {'請開始繪畫' if is_drawing_op else '請開始猜測'}！")

    async def handle_submit_drawing(self, drawing_data_url):
        room = game_rooms[self.room_group_name]

        if room['state'] != 'drawing':
            await self.send_error("現在不是繪畫階段。")
            return
        if self.player_id not in room['assignments'] or room['assignments'][self.player_id]['type'] != 'draw':
            await self.send_error("您沒有被分配繪畫任務或已提交。")
            return
        if not drawing_data_url:
            await self.send_error("繪畫數據不能為空。")
            return

        task = room['assignments'].pop(self.player_id)
        original_player_id = task['original_player_id']
        ui_round = task['ui_round']

        room['books'][original_player_id].append({
            'type': 'drawing',
            'data': drawing_data_url,
            'player': self.player_id, # Who drew it
            'round': ui_round
        })
        print(f"Player {self.player_id} submitted drawing for book {original_player_id} (UI Round {ui_round})")
        await self.send_notification('您的繪畫已提交！', 'success')

        if not room['assignments']: # All drawings for this op_num submitted
            print(f"Room {self.room_name}: All drawings for Op# {room['current_op_number']} submitted.")
            await self.start_next_operation()
        else:
            await self.broadcast_game_state(f"等待其他 {len(room['assignments'])} 位玩家完成繪畫...")

    async def handle_submit_guess(self, guess_text):
        room = game_rooms[self.room_group_name]

        if room['state'] != 'guessing':
            await self.send_error("現在不是猜測階段。")
            return
        if self.player_id not in room['assignments'] or room['assignments'][self.player_id]['type'] != 'guess':
            await self.send_error("您沒有被分配猜測任務或已提交。")
            return
        if not guess_text or len(guess_text.strip()) == 0:
            await self.send_error("猜測內容不能為空。")
            return
            
        task = room['assignments'].pop(self.player_id)
        original_player_id = task['original_player_id']
        ui_round = task['ui_round']

        room['books'][original_player_id].append({
            'type': 'guess',
            'data': guess_text,
            'player': self.player_id, # Who guessed it
            'round': ui_round
        })
        print(f"Player {self.player_id} submitted guess for book {original_player_id} (UI Round {ui_round})")
        await self.send_notification('您的猜測已提交！', 'success')

        if not room['assignments']: # All guesses for this op_num submitted
            print(f"Room {self.room_name}: All guesses for Op# {room['current_op_number']} submitted.")
            await self.start_next_operation()
        else:
            await self.broadcast_game_state(f"等待其他 {len(room['assignments'])} 位玩家完成猜測...")

    async def finish_game(self):
        room = game_rooms[self.room_group_name]
        room['state'] = 'finished'
        print(f"Room {self.room_name}: Game finished. Broadcasting results.")

        # Prepare payload for game_over
        # Ensure player names are included for display
        players_info_for_results = {
            pid: {'name': pdata.get('name', pid), 'isBot': pdata.get('isBot', False)}
            for pid, pdata in room['players'].items()
        }

        game_over_payload = {
            'books': room['books'],
            'players': players_info_for_results, # Send simplified player info
            'turn_order': room['turn_order'] # To display books in a consistent order
        }
        
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'broadcast_message', # Goes to broadcast_message handler
                'message_type': 'game_over', # Client-side type
                'payload': game_over_payload
            }
        )
        # Optionally, clean up the game room from game_rooms after a delay or mark as finished
        # For now, keep it for potential review, or until all players disconnect

    def prepare_game_state_payload(self, status_message=""):
        room = game_rooms.get(self.room_group_name)
        if not room:
            return {}

        # Ensure players data is serializable and doesn't expose sensitive info like channel_name
        players_public_info = {}
        for pid, pdata in room.get('players', {}).items():
            players_public_info[pid] = {
                'name': pdata.get('name', pid),
                'isBot': pdata.get('isBot', False),
                'connected': 'channel_name' in pdata # Basic connected status
            }
            
        return {
            'state': room['state'],
            'players': players_public_info, # Use public info
            'current_op_number': room.get('current_op_number', 0), # For debugging or advanced client logic
            'current_display_round': room.get('current_display_round', 0),
            'total_display_rounds': room.get('total_display_rounds', 0),
            'status_message': status_message,
            'waiting_on': list(room.get('assignments', {}).keys()),
            'turn_order': room.get('turn_order', [])
        }

    async def broadcast_game_state(self, status_message=""):
        room = game_rooms.get(self.room_group_name)
        if not room:
            return

        state_payload = self.prepare_game_state_payload(status_message)
        
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'broadcast_message', # Goes to broadcast_message handler
                'message_type': 'game_state_update', # Client-side type
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

    async def send_game_state_to_player(self, player_id, status_message=""):
        room = game_rooms.get(self.room_group_name)
        if not room:
            return

        state_payload = self.prepare_game_state_payload(status_message)
        state_payload['your_player_id'] = player_id # 讓客戶端知道自己的ID

        await self.send(text_data=json.dumps({
            'type': 'game_state_update',
            'payload': state_payload
        }))

    async def send_error(self, message):
        await self.send(text_data=json.dumps({
            'type': 'error',
            'payload': {'message': message}
        }))

    async def send_notification(self, message, level='info'):
        await self.send(text_data=json.dumps({
            'type': 'notification', # Client-side type for displaying notifications
            'payload': {'message': message, 'level': level}
        }))

    async def send_personal_message(self, event):
        """Handles sending a personal message to this specific client."""
        message_type = event['message_type']
        payload = event.get('payload', {})
        
        await self.send(text_data=json.dumps({
            'type': message_type,
            'payload': payload
        }))

    async def broadcast_message(self, event):
        """
        Handles messages sent to the group. It forwards them to all clients in the group.
        This method is called by channel_layer.group_send(... {'type': 'broadcast_message'})
        """
        message_type = event['message_type']
        payload = event.get('payload', {})

        # If this message is a game_state_update, ensure 'your_player_id' is set for each client
        if message_type == 'game_state_update':
            # The payload from broadcast_game_state is already prepared.
            # We need to add 'your_player_id' for the specific recipient.
            # This is tricky because broadcast_message is generic.
            # A better way: send_game_state_to_player for individual updates if needed,
            # or client infers its ID from initial connection or a separate message.
            # For now, client should know its ID.
            pass # Payload is already good from prepare_game_state_payload

        await self.send(text_data=json.dumps({
            'type': message_type,
            'payload': payload
        }))

    async def handle_clear_canvas_broadcast(self):
        """Handles a request to clear canvas for all players (e.g., if a round restarts or error)."""
        room = game_rooms.get(self.room_group_name)
        if not room: return

        # This is a broadcast to all players in the group
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'broadcast_message',
                'message_type': 'clear_canvas_instruction', # Client-side type
                'payload': {} 
            }
        )
        print(f"Broadcast clear canvas instruction to room {self.room_name}")

    async def send_message(self, event):
        """
        This method is the target for channel_layer.send when the type is 'send_message'.
        It directly sends the message to the WebSocket.
        """
        message_type = event['message_type']
        payload = event.get('payload', {})
        await self.send(text_data=json.dumps({
            'type': message_type,
            'payload': payload,
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
