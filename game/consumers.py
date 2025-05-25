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
from .llm_client import LLMClient, image_bytes_to_data_url, data_url_to_image_bytes # Added

# 添加基本日誌設置
logger = logging.getLogger(__name__)

# 簡易的記憶體內儲存來管理房間狀態
# 注意：這在多個伺服器實例下無法運作，生產環境需要更健壯的方案 (例如 Redis, 資料庫)
game_rooms = {}
waiting_rooms = {}

# Create an instance of the LLMClient
# This will load API keys and prompts when the Django application starts.
try:
    llm_client = LLMClient()
except ValueError as e:
    logger.error(f"Failed to initialize LLMClient: {e}")
    llm_client = None # Set to None if initialization fails
except Exception as e:
    logger.error(f"An unexpected error occurred during LLMClient initialization: {e}")
    llm_client = None


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
        bot_id = f"bot_{bot_count + 1}" # Ensure unique bot IDs if bots are removed and re-added
        bot_name = "畫畫機器人" + str(bot_count + 1)
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
        # if num_actual_players < 2: # 至少需要2名人類玩家才能開始遊戲 (例如，2人遊戲，N=2, N-1=1輪操作)
        #                          # 根據使用者描述，N至少為2。如果N=2, 總共2個條目，1次繪畫。
        #                          # 如果N=3, 總共3個條目，1畫1猜。
        #                          # 遊戲至少需要2人。
        #     await self.send(text_data=json.dumps({
        #         'type': 'error',
        #         'payload': {'message': '至少需要2名玩家才能開始遊戲'}
        #     }))
        #     return
            
        hash_key = hashlib.md5(self.room_name.encode('utf-8')).hexdigest()
        game_room_key = f'game_{hash_key}'
        
        all_player_ids_in_order = list(room['players'].keys())

        # Calculate max AI assists allowed per human player
        # (玩家數量/2)-1, ensuring it's not negative, and using floor for integer division
        max_ai_assists_allowed = max(0, math.floor(len(all_player_ids_in_order) / 2) - 1)
        
        # Initialize AI assist usage tracking for human players
        ai_assist_usage = {
            player_id: 0 
            for player_id, p_data in room['players'].items() 
            if not p_data.get('isBot', False)
        }

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
            'game_log': [],
            'max_ai_assists_allowed': max_ai_assists_allowed, # 新增：最大AI輔助次數
            'ai_assist_usage': ai_assist_usage             # 新增：AI輔助使用記錄
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
                logger.warning(f"GameConsumer: 房間 {self.room_group_name} 不存在，但收到訊息類型 {message_type} from {self.player_id}")
                return

            logger.debug(f"GameConsumer: Received message type: {message_type} from {self.player_id} in {self.room_name}. Payload: {payload}")

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
            elif message_type == 'clear_canvas':
                await self.handle_clear_canvas()
            elif message_type == 'ai_assist_drawing':
                await self.handle_ai_assist_drawing(payload)
            elif message_type == 'navigate_book': # 新增：處理書本導覽請求
                await self.handle_navigate_book(payload)
        except json.JSONDecodeError:
            print(f"Error decoding JSON: {text_data}")
        except Exception as e:
            print(f"Error processing message: {e}")
            import traceback
            traceback.print_exc()

    async def handle_start_game(self):
        room = game_rooms.get(self.room_group_name)
        if not room:
            logger.warning(f"Room {self.room_group_name} not found in handle_start_game for player {self.player_id}.")
            return

        logger.info(f"Player {self.player_id} triggered handle_start_game for room {self.room_name}. Current state: {room['state']}, Prompting initiated: {room.get('prompting_initiated', False)}")

        if room['state'] == 'initializing' and not room.get('prompting_initiated', False):
            all_non_bots_connected = True
            missing_players = []
            if not room.get('turn_order'):
                logger.warning(f"Room {self.room_name}: turn_order is empty or not set. Cannot check player readiness.")
                all_non_bots_connected = False
            else:
                for player_id_in_order in room['turn_order']:
                    player_data = room['players'].get(player_id_in_order)
                    if not player_data:
                        logger.warning(f"Room {self.room_name}: Player data for {player_id_in_order} not found in room['players'] during readiness check.")
                        all_non_bots_connected = False
                        missing_players.append(f"{player_id_in_order} (data missing)")
                        break
                    
                    if not player_data.get('isBot', False): # It's a human player
                        if not player_data.get('channel_name'): # Check if connected to GameConsumer
                            all_non_bots_connected = False
                            logger.info(f"Room {self.room_name}: Player {player_id_in_order} (human) not yet fully connected to GameConsumer (no channel_name). Waiting...")
                            missing_players.append(player_id_in_order)
                            # Do not break here, log all missing players for better diagnostics
            
            if missing_players:
                 logger.info(f"Room {self.room_name}: Still waiting for human players to connect: {missing_players}")

            if all_non_bots_connected:
                logger.info(f"Room {self.room_name}: All human players detected as connected. Initiating prompting round.")
                room['prompting_initiated'] = True # Set flag before calling
                await self.start_prompting_round()
            else:
                logger.info(f"Room {self.room_name}: Not all human players are connected yet. Prompting round will not start yet.")
        elif room.get('prompting_initiated'):
            logger.info(f"Room {self.room_name}: Prompting round already initiated or in progress. Player {self.player_id} sending 'start_game' again.")
            # Optionally, resend current game state to this player if they might have missed it
            await self.send_game_state_to_player(self.player_id, "遊戲已開始，同步狀態...")
        elif room['state'] != 'initializing':
            logger.info(f"Room {self.room_name}: Game is not in 'initializing' state (current: {room['state']}). Player {self.player_id} sent 'start_game'.")
            await self.send_game_state_to_player(self.player_id, "遊戲已在進行中，同步狀態...")


    async def start_prompting_round(self):
        """開始提示輸入階段"""
        room = game_rooms.get(self.room_group_name)
        if not room:
            logger.error(f"start_prompting_round: Room {self.room_group_name} not found!")
            return

        # Ensure this runs only once if prompting_initiated was the guard
        # Or, if state is already 'prompting', it might be a re-entry, be careful.
        if room['state'] != 'initializing': # Check should be against 'initializing'
            logger.warning(f"Room {self.room_name}: Attempted to start prompting round when not in initializing state (current: {room['state']}). Current op_number: {room.get('current_op_number')}")
            # If already prompting, perhaps just resend state or assignments to late joiners if supported.
            # For now, we prevent re-entry if not initializing.
            return

        logger.info(f"Room {self.room_name}: Executing start_prompting_round.")
        room['state'] = 'prompting'
        room['current_op_number'] = 0 
        room['current_display_round'] = 0 
        room['assignments'] = {player_id: {'type': 'prompt'} for player_id in room['turn_order']}
        
        logger.info(f"Room {self.room_name}: Initial assignments for prompting: {list(room['assignments'].keys())}")
        await self.broadcast_game_state("請所有玩家提交一個有趣的題目！") 

        bots_processed_count = 0
        for player_id in room['turn_order']: 
            player_data = room['players'].get(player_id)
            if not player_data:
                logger.warning(f"Room {self.room_name}: Player data not found for {player_id} in start_prompting_round (turn_order). Skipping.")
                continue

            if player_data.get('isBot', False):
                # Bot logic: auto-submit prompt
                bot_prompt = None
                if llm_client:
                    try:
                        logger.info(f"Room {self.room_name}: Bot {player_id} attempting to generate prompt via LLM.")
                        generated_text = await sync_to_async(llm_client.generate_text_from_text)()
                        if generated_text and generated_text.strip():
                            bot_prompt = generated_text.strip()
                            logger.info(f"Room {self.room_name}: Bot {player_id} LLM generated prompt: {bot_prompt}")
                        else:
                            logger.warning(f"Room {self.room_name}: Bot {player_id} LLM returned empty prompt.")
                    except Exception as e:
                        logger.error(f"Room {self.room_name}: Bot {player_id} error generating prompt via LLM: {e}")
                
                if not bot_prompt: # Fallback to predefined prompts
                    logger.info(f"Room {self.room_name}: Bot {player_id} falling back to predefined prompt.")
                    bot_prompts_list = [
                        "一隻太空貓在月球上釣魚", "一個害羞的機器人送花", "魔法森林裡的秘密派對",
                        "沉睡火山上的冰淇淋店", "會飛的豬在雲中賽跑", "水下城市的爵士樂隊",
                        "時間旅行者遺失了他的手錶", "一隻愛讀書的龍", "隱形人在玩捉迷藏"
                    ]
                    bot_prompt = random.choice(bot_prompts_list)
                
                room['books'][player_id].append({
                    'type': 'prompt',
                    'data': bot_prompt,
                    'player': player_id,
                    'round': 0 # Initial prompt is round 0
                })
                if player_id in room['assignments']:
                    del room['assignments'][player_id] 
                logger.info(f"Room {self.room_name}: Bot {player_id} ({player_data.get('name', '')}) auto-submitted prompt: {bot_prompt}")
                bots_processed_count += 1
            else:
                # Real player logic
                player_channel_name = player_data.get('channel_name')
                logger.info(f"Room {self.room_name}: Processing real player {player_id} ({player_data.get('name', '')}). Channel name from room data: '{player_channel_name}'")
                if player_channel_name:
                    logger.info(f"Room {self.room_name}: Sending 'assign_prompt' to player {player_id} on channel {player_channel_name}.")
                    await self.channel_layer.send(
                        player_channel_name,
                        {
                            'type': 'send_message', 
                            'message_type': 'assign_prompt', 
                            'payload': {} 
                        }
                    )
                else:
                    logger.warning(f"Room {self.room_name}: Real player {player_id} ({player_data.get('name', '')}) HAS NO CHANNEL_NAME during start_prompting_round. Client UI should update via game_state_update if they are in waiting_on.")

        if bots_processed_count > 0:
            logger.info(f"Room {self.room_name}: Bots have processed. Remaining assignments: {list(room['assignments'].keys())}")
            if not room['assignments']: 
                logger.info(f"Room {self.room_name}: All prompts submitted (all bots or bots + instant human submissions). Starting first operation.")
                # Ensure not to call start_next_operation if game already moved past prompting by a quick human
                if room['state'] == 'prompting': # Double check state
                    await self.start_next_operation()
            else:
                await self.broadcast_game_state(f"機器人已完成出題，等待 {len(room['assignments'])} 位玩家...")
        
        # If no bots, the first broadcast_game_state is active.
        # Transition to next phase is handled by the last real player's submission.
        logger.info(f"Room {self.room_name}: Finished start_prompting_round. Current assignments: {list(room['assignments'].keys())}")

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
            logger.info(f"Room {self.room_name}: Op# {op_num} exceeds total_ops {room['total_ops']}. Finishing game.")
            await self.finish_game()
            return

        is_drawing_op = (op_num % 2 == 1)
        room['current_display_round'] = math.ceil(op_num / 2.0)
        
        current_assignments = {} 
        action_type = 'draw' if is_drawing_op else 'guess'
        next_state = 'drawing' if is_drawing_op else 'guessing'
        room['state'] = next_state

        logger.info(f"Room {self.room_name}: Starting Op# {op_num} (Display Round {room['current_display_round']}) - Type: {next_state}")

        bots_processed_this_op = False

        for i, current_player_id in enumerate(room['turn_order']):
            player_data = room['players'].get(current_player_id)
            if not player_data:
                logger.warning(f"Room {self.room_name}: Player data for {current_player_id} not found in start_next_operation. Skipping.")
                continue

            book_owner_index = (i - op_num % num_players + num_players) % num_players
            original_book_owner_id = room['turn_order'][book_owner_index]
            
            book_content = room['books'][original_book_owner_id]
            if not book_content:
                logger.error(f"Room {self.room_name}: Book for {original_book_owner_id} is empty for Op# {op_num} by {current_player_id}!")
                continue 
            
            item_to_process = book_content[-1]

            task_payload_for_assignment = {
                'original_player_id': original_book_owner_id,
                'ui_round': room['current_display_round']
            }
            client_message_payload = {
                'original_player': original_book_owner_id, 
                'round': room['current_display_round']
            }

            if is_drawing_op:
                if item_to_process['type'] not in ['prompt', 'guess']:
                    logger.error(f"Room {self.room_name}: Expected prompt or guess for drawing by {current_player_id}, got {item_to_process['type']}")
                    continue
                
                task_payload_for_assignment['type'] = 'draw'
                task_payload_for_assignment['prompt_or_guess'] = item_to_process['data']
                client_message_payload['prompt_or_guess'] = item_to_process['data']
                client_message_type = 'request_drawing'

                if player_data.get('isBot', False):
                    # 機器人繪畫邏輯
                    bot_drawing = None
                    text_to_draw = item_to_process['data']
                    if llm_client:
                        try:
                            logger.info(f"Room {self.room_name}: Bot {current_player_id} attempting to generate image for: '{text_to_draw}'")
                            image_bytes = await sync_to_async(llm_client.generate_image_bytes_from_text)(text_to_draw)
                            if image_bytes:
                                # Convert image_bytes to data URL
                                bot_drawing = await sync_to_async(image_bytes_to_data_url)(image_bytes, mime_type="image/png") # Assuming PNG
                                if bot_drawing:
                                    logger.info(f"Room {self.room_name}: Bot {current_player_id} LLM generated image successfully.")
                                else:
                                    logger.warning(f"Room {self.room_name}: Bot {current_player_id} failed to convert LLM image bytes to data URL.")
                            else:
                                logger.warning(f"Room {self.room_name}: Bot {current_player_id} LLM returned no image bytes.")
                        except Exception as e:
                            logger.error(f"Room {self.room_name}: Bot {current_player_id} error generating image via LLM: {e}")

                    if not bot_drawing: # Fallback to placeholder SVG
                        logger.info(f"Room {self.room_name}: Bot {current_player_id} falling back to placeholder drawing.")
                        bot_drawing_placeholders = [
                            "data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIyMDAiIGhlaWdodD0iMTUwIj48cmVjdCB3aWR0aD0iMTAwJSIgaGVpZ2h0PSIxMDAlIiBmaWxsPSIjZjBlNmYyIi8+PHRleHQgeD0iNTAlIiB5PSI1MCUiIGRvbWluYW50LWJhc2VsaW5lPSJtaWRkbGUiIHRleHQtYW5jaG9yPSJtaWRkbGUiIGZvbnQtZmFtaWx5PSJhcmlhbCIgZm9udC1zaXplPSIxNiIgZmlsbD0iIzU1NSI+Qm90J3MgQXJ0PC90ZXh0Pjwvc3ZnPg==",
                            "data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIyMDAiIGhlaWdodD0iMTUwIj48cmVjdCB3aWR0aD0iMTAwJSIgaGVpZ2h0PSIxMDAlIiBmaWxsPSIjZDJmMmVhIi8+PGNpcmNsZSBjeD0iMTAwIiBjeT0iNzUiIHI9IjQwIiBmaWxsPSIjZmZjMzMzIi8+PHRleHQgeD0iNTAlIiB5PSI1MCUiIGRvbWluYW50LWJhc2VsaW5lPSJtaWRkbGUiIHRleHQtYW5jaG9yPSJtaWRkbGUiIGZvbnQtZmFtaWx5PSJhcmlhbCIgZm9udC1zaXplPSIxMiIgZmlsbD0iIzMzMyI+Um9ib3QtRGF2aW5jaTwvdGV4dD48L3N2Zz4=",
                            "data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIyMDAiIGhlaWdodD0iMTUwIj48cmVjdCB3aWR0aD0iMTAwJSIgaGVpZ2h0PSIxMDAlIiBmaWxsPSIjZThlMWY2Ii8+PHBhdGggZD0iTTUwIDMwIEwxNTAgMzAgTDEwMCAxMjAgWiIgZmlsbD0iI2FmY2RmNSIvPjx0ZXh0IHg9IjUwJSIgeT0iNzAlIiBkb21pbmFudC1JYXNlbGluZT0ibWlkZGxlIiB0ZXh0LWFuY2hvcj0ibWlkZGxlIiBmb250LWZhbWlseT0iY291cmllciIgZm9udC1zaXplPSIxNCIgZmlsbD0iIzY2Njg3YiI+QklPIC1SVEZMT1c8L3RleHQ+PC9zdmc+"
                        ]
                        bot_drawing = random.choice(bot_drawing_placeholders)
                    
                    room['books'][original_book_owner_id].append({
                        'type': 'drawing',
                        'data': bot_drawing,
                        'player': current_player_id, 
                        'round': room['current_display_round']
                    })
                    logger.info(f"Room {self.room_name}: Bot {current_player_id} ({player_data.get('name', '')}) auto-submitted drawing for book {original_book_owner_id}.")
                    bots_processed_this_op = True
                    continue 
            else: # Guessing Op
                if item_to_process['type'] != 'drawing':
                    logger.error(f"Room {self.room_name}: Expected drawing for guessing by {current_player_id}, got {item_to_process['type']}")
                    continue
                
                task_payload_for_assignment['type'] = 'guess'
                task_payload_for_assignment['drawing_data'] = item_to_process['data'] # For human player assignment data
                client_message_payload['drawing_data'] = item_to_process['data'] # For client message
                client_message_type = 'request_guess'

                if player_data.get('isBot', False):
                    # 機器人猜測邏輯
                    bot_guess = None
                    drawing_data_url = item_to_process['data']
                    if llm_client:
                        try:
                            logger.info(f"Room {self.room_name}: Bot {current_player_id} attempting to generate guess for drawing.")
                            # Convert data URL to image bytes
                            image_bytes, mime_type = await sync_to_async(data_url_to_image_bytes)(drawing_data_url)
                            if image_bytes and mime_type:
                                generated_text = await sync_to_async(llm_client.generate_text_from_image_bytes)(image_bytes, mime_type=mime_type)
                                if generated_text and generated_text.strip():
                                    bot_guess = generated_text.strip()
                                    logger.info(f"Room {self.room_name}: Bot {current_player_id} LLM generated guess: {bot_guess}")
                                else:
                                    logger.warning(f"Room {self.room_name}: Bot {current_player_id} LLM returned empty guess.")
                            else:
                                logger.warning(f"Room {self.room_name}: Bot {current_player_id} failed to convert drawing data URL to bytes for LLM.")
                        except Exception as e:
                            logger.error(f"Room {self.room_name}: Bot {current_player_id} error generating guess via LLM: {e}")
                    
                    if not bot_guess: # Fallback to predefined guesses
                        logger.info(f"Room {self.room_name}: Bot {current_player_id} falling back to predefined guess.")
                        bot_guess_phrases = [
                            "一隻貓在彈吉他", "一個快樂的太陽", "跳舞的機器人", "飛碟綁架了一頭牛",
                            "巫師在施法", "一條龍在噴火", "太空人在月球漫步", "一個巨大的甜甜圈",
                            "唱歌的胡蘿蔔", "戴著帽子的蛇"
                        ]
                        bot_guess = random.choice(bot_guess_phrases)
                    
                    room['books'][original_book_owner_id].append({
                        'type': 'guess',
                        'data': bot_guess,
                        'player': current_player_id, # 機器人是 "猜測者"
                        'round': room['current_display_round']
                    })
                    logger.info(f"Room {self.room_name}: Bot {current_player_id} ({player_data.get('name', '')}) auto-submitted guess '{bot_guess}' for book {original_book_owner_id}.")
                    bots_processed_this_op = True
                    continue # 機器人已完成，跳過任務分配和訊息發送

            # 對於真人玩家，或未被自動處理的機器人任務
            current_assignments[current_player_id] = task_payload_for_assignment
            
            if player_data.get('channel_name'):
                await self.channel_layer.send(
                    player_data['channel_name'],
                    {
                        'type': 'send_message',
                        'message_type': client_message_type,
                        'payload': client_message_payload
                    }
                )
                logger.info(f"Room {self.room_name}: Assigned task to {current_player_id}: {task_payload_for_assignment['type']} for book {original_book_owner_id} (Op# {op_num})")
            else:
                if not player_data.get('isBot', False): # 只記錄真人玩家的此類警告
                     logger.warning(f"Room {self.room_name}: Real player {current_player_id} has no channel_name. Task {task_payload_for_assignment['type']} assigned but cannot send direct message.")

        room['assignments'] = current_assignments
        
        status_msg_prefix = f"第 {room['current_display_round']} 回合 - "
        status_msg_main = "請開始繪畫！" if is_drawing_op else "請開始猜測！"

        if bots_processed_this_op: 
            current_action_description = "繪畫" if is_drawing_op else "猜測"
            if not room['assignments']: 
                logger.info(f"Room {self.room_name}: All {current_action_description} tasks for Op# {op_num} completed by bots or instant human submissions. Starting next operation.")
                # 確保在正確的狀態下才推進 (drawing 或 guessing)
                if room['state'] == next_state: 
                     await self.start_next_operation()
                return 
            else:
                await self.broadcast_game_state(f"{status_msg_prefix}機器人已完成{current_action_description}，等待 {len(room['assignments'])} 位玩家...")
        else:
            await self.broadcast_game_state(f"{status_msg_prefix}{status_msg_main}")

        logger.info(f"Room {self.room_name}: Finished Op# {op_num} setup. Current assignments: {list(room['assignments'].keys())}")

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
        room['current_results_book_index'] = 0 # 初始化結果書本索引
        print(f"Room {self.room_name}: Game finished. Broadcasting results.")

        # Prepare payload for game_over
        # Ensure player names are included for display
        players_info_for_results = {
            pid: {
                'name': pdata.get('name', pid), 
                'isBot': pdata.get('isBot', False),
                'isHost': pdata.get('isHost', False)  # 添加 isHost 資訊
            }
            for pid, pdata in room['players'].items()
        }

        game_over_payload = {
            'books': room['books'],
            'players': players_info_for_results, # Send simplified player info
            'turn_order': room['turn_order'], # To display books in a consistent order
            'initial_book_index': room.get('current_results_book_index', 0) # 添加初始書本索引
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
                'isHost': pdata.get('isHost', False), # 添加 isHost 資訊
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
            'turn_order': room.get('turn_order', []),
            'max_ai_assists_allowed': room.get('max_ai_assists_allowed', 0), # 新增
            'ai_assist_usage': room.get('ai_assist_usage', {})             # 新增
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

    async def handle_navigate_book(self, payload):
        room = game_rooms.get(self.room_group_name)
        if not room or room['state'] != 'finished':
            # 僅在遊戲結束狀態下允許導覽
            logger.warning(f"Navigate book attempt in non-finished state or room not found. Room: {self.room_name}, State: {room.get('state') if room else 'N/A'}")
            return

        if self.player_id != room.get('host_id'):
            await self.send_error("只有房主才能切換書本。")
            return

        direction = payload.get('direction')
        current_index = room.get('current_results_book_index', 0)
        
        # turn_order 應該在 room['books'] 的鍵中，或者直接用 room['turn_order']
        # 假設 displayedBooksOrder (即 room['turn_order']) 是有效的
        num_books = len(room.get('turn_order', []))
        if num_books == 0:
            logger.warning(f"No books to navigate in room {self.room_name}.")
            return


        if direction == 'next' and current_index < num_books - 1:
            room['current_results_book_index'] += 1
        elif direction == 'prev' and current_index > 0:
            room['current_results_book_index'] -= 1
        else:
            # 無效方向或已在邊界，不執行操作或可選擇發送錯誤
            logger.debug(f"Navigate book: Invalid direction '{direction}' or at boundary. Index: {current_index}, NumBooks: {num_books}")
            return

        logger.info(f"Room {self.room_name}: Host {self.player_id} navigated book. New index: {room['current_results_book_index']}")

        # 向房間內所有客戶端廣播新的書本索引
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'broadcast_message', # 使用現有的 broadcast_message 處理器
                'message_type': 'update_displayed_book', # 客戶端將監聽此類型
                'payload': {'book_index': room['current_results_book_index']}
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

    async def handle_ai_assist_drawing(self, payload):
        """處理 AI 輔助繪畫請求"""
        room = game_rooms.get(self.room_group_name)
        # 初始化 is_bot 以確保在所有路徑中都已定義
        is_bot = False 
        # 初始化 response_remaining_assists 的預設值
        # 如果房間或玩家資料不存在，預設剩餘次數為0
        response_remaining_assists = 0
        max_allowed_assists = 0


        if not room:
            logger.error(f"Room {self.room_name} not found for AI assist.")
            await self.send(text_data=json.dumps({
                'type': 'ai_drawing_result', 'payload': {'success': False, 'error': "遊戲房間不存在。", 'remaining_ai_assists': 0}
            }))
            return

        player_data = room['players'].get(self.player_id)
        if not player_data:
            await self.send(text_data=json.dumps({
                'type': 'ai_drawing_result', 'payload': {'success': False, 'error': "找不到玩家資料。", 'remaining_ai_assists': 0}
            }))
            return

        is_bot = player_data.get('isBot', False)
        max_allowed_assists = room.get('max_ai_assists_allowed', 0)
        
        current_player_usage = 0
        if not is_bot:
            current_player_usage = room.get('ai_assist_usage', {}).get(self.player_id, 0)
        
        response_remaining_assists = max_allowed_assists - current_player_usage
        if is_bot: # 機器人不受限，可以顯示為最大允許次數
            response_remaining_assists = max_allowed_assists

        try:
            prompt_text = payload.get('prompt')
            drawing_data_url = payload.get('drawing')
            
            if not prompt_text or not drawing_data_url:
                await self.send(text_data=json.dumps({
                    'type': 'ai_drawing_result', 
                    'payload': {'success': False, 'error': "缺少必要的繪畫或描述資訊", 'remaining_ai_assists': response_remaining_assists}
                }))
                return
            
            if not llm_client:
                logger.error(f"Room {self.room_name}: LLM Client not initialized.")
                await self.send(text_data=json.dumps({
                    'type': 'ai_drawing_result', 
                    'payload': {'success': False, 'error': "AI 服務未啟動", 'remaining_ai_assists': response_remaining_assists}
                }))
                return

            if not is_bot:
                if current_player_usage >= max_allowed_assists:
                    logger.info(f"Room {self.room_name}: Player {self.player_id} has no AI assists remaining (used {current_player_usage}/{max_allowed_assists}).")
                    await self.send(text_data=json.dumps({
                        'type': 'ai_drawing_result',
                        'payload': {'success': False, 'error': '已達 AI 輔助次數上限', 'remaining_ai_assists': max(0, response_remaining_assists)}
                    }))
                    return
            
            logger.info(f"Room {self.room_name}: Processing AI assist for {self.player_id}. Human assists before this use: {response_remaining_assists if not is_bot else 'N/A (Bot)'}")
            
            image_bytes, mime_type = data_url_to_image_bytes(drawing_data_url)
            if not image_bytes:
                logger.error(f"Room {self.room_name}: Failed to convert drawing data URL to image bytes.")
                await self.send(text_data=json.dumps({
                    'type': 'ai_drawing_result', 
                    'payload': {'success': False, 'error': "處理圖像資料失敗", 'remaining_ai_assists': response_remaining_assists}
                }))
                return
            
            if not is_bot:
                current_player_usage += 1
                room['ai_assist_usage'][self.player_id] = current_player_usage
                response_remaining_assists = max_allowed_assists - current_player_usage
            
            result_image_bytes = llm_client.generate_image_from_image(
                image_bytes, 
                prompt_text=prompt_text, 
                mime_type=mime_type
            )
            
            if not result_image_bytes:
                logger.error(f"Room {self.room_name}: LLM returned no image bytes for AI drawing.")
                await self.send(text_data=json.dumps({
                    'type': 'ai_drawing_result',
                    'payload': {'success': False, 'error': 'AI 生成圖像失敗，請重試', 'remaining_ai_assists': response_remaining_assists}
                }))
                return
            
            result_data_url = image_bytes_to_data_url(result_image_bytes, mime_type)
            if not result_data_url:
                logger.error(f"Room {self.room_name}: Failed to convert result image bytes to data URL.")
                await self.send(text_data=json.dumps({
                    'type': 'ai_drawing_result',
                    'payload': {'success': False, 'error': '處理結果圖像失敗', 'remaining_ai_assists': response_remaining_assists}
                }))
                return
            
            await self.send(text_data=json.dumps({
                'type': 'ai_drawing_result',
                'payload': {'success': True, 'image': result_data_url, 'remaining_ai_assists': response_remaining_assists}
            }))
            logger.info(f"Room {self.room_name}: Successfully processed AI assist for {self.player_id}. Human assists remaining: {response_remaining_assists if not is_bot else 'N/A (Bot)'}")
            
        except Exception as e:
            logger.error(f"Room {self.room_name}: Error processing AI assist drawing for {self.player_id}: {e}", exc_info=True)
            # 在發生未知錯誤時，response_remaining_assists 會是基於嘗試使用前的狀態（如果錯誤發生在計數增加前）
            # 或嘗試使用後的狀態（如果錯誤發生在計數增加後）。目前邏輯是在LLM調用前增加計數。
            await self.send(text_data=json.dumps({
                'type': 'ai_drawing_result',
                'payload': {'success': False, 'error': "AI 處理過程出錯", 'remaining_ai_assists': response_remaining_assists}
            }))
