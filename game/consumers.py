import json
import asyncio
import hashlib
from channels.generic.websocket import AsyncWebsocketConsumer
from collections import defaultdict, deque
import random

# 簡易的記憶體內儲存來管理房間狀態
# 注意：這在多個伺服器實例下無法運作，生產環境需要更健壯的方案 (例如 Redis, 資料庫)
game_rooms = {}

class GameConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.room_name = self.scope['url_route']['kwargs'].get('room_name', 'default')
        # 將房間名轉換為 MD5 哈希值，確保只包含合法字符
        room_name_hash = hashlib.md5(self.room_name.encode('utf-8')).hexdigest()
        self.room_group_name = f'game_{room_name_hash}'
        self.player_id = self.channel_name # 暫時用 channel_name 作為玩家 ID

        # 初始化房間狀態 (如果不存在)
        if self.room_group_name not in game_rooms:
            game_rooms[self.room_group_name] = {
                'original_room_name': self.room_name, # 保存原始房間名稱以供顯示
                'players': {}, # {player_id: {'name': 'PlayerName', 'connected': True}}
                'state': 'waiting', # waiting, prompting, drawing, guessing, finished
                'prompts': {}, # {player_id: prompt_text}
                'books': {}, # {original_player_id: [{'type': 'prompt', 'data': text}, {'type': 'drawing', 'data': data_url, 'player': player_id}, ...]}
                'current_round': 0,
                'assignments': {}, # {player_id: task_data} # 當前回合分配給玩家的任務
                'turn_order': [] # 玩家順序
            }

        # 加入房間群組
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )
        await self.accept()

        # 添加玩家到房間狀態
        room = game_rooms[self.room_group_name]
        room['players'][self.player_id] = {'name': f'Player_{len(room["players"]) + 1}', 'connected': True} # 簡單命名
        print(f"Player {self.player_id} connected to {self.room_group_name} ({self.room_name}). Players: {room['players']}")

        # 向所有玩家廣播更新後的狀態
        await self.broadcast_game_state("玩家加入")

    async def disconnect(self, close_code):
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

    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
            message_type = data.get('type')
            payload = data.get('payload', {})
            room = game_rooms.get(self.room_group_name)

            if not room:
                print(f"Error: Room {self.room_group_name} not found.")
                return

            print(f"Received message type: {message_type} from {self.player_id} in {self.room_group_name}")

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
                await self.handle_user_info(payload)
            # 可以添加其他訊息類型處理

        except json.JSONDecodeError:
            print(f"Error decoding JSON: {text_data}")
        except Exception as e:
            print(f"Error processing message: {e}")
            import traceback
            traceback.print_exc()


    # --- 訊息處理函數 ---
    async def handle_chat_message(self, message):
         if message:
             room = game_rooms[self.room_group_name]
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

    async def handle_start_game(self):
        room = game_rooms[self.room_group_name]
        # 檢查是否可以開始遊戲 (例如：至少2個玩家)
        if room['state'] == 'waiting' and len(room['players']) >= 2: # 至少需要2個玩家才能交換
            room['state'] = 'prompting'
            room['prompts'] = {} # 清空上一局的題目
            room['books'] = {pid: [] for pid in room['players']} # 為每個玩家初始化故事本
            room['current_round'] = 0
            room['turn_order'] = list(room['players'].keys())
            random.shuffle(room['turn_order']) # 隨機排序玩家

            print(f"Game starting in room {self.room_group_name}. Turn order: {room['turn_order']}")

            # 向所有玩家請求題目
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'broadcast_message',
                    'message_type': 'request_prompt',
                    'payload': {} # 可以包含提示訊息
                }
            )
            await self.broadcast_game_state("遊戲開始，請輸入題目")
        else:
             # 可以發送錯誤訊息給發起者
             await self.send(text_data=json.dumps({
                 'type': 'error',
                 'payload': {'message': f'無法開始遊戲，需要至少 2 位玩家，目前 {len(room["players"])} 位。'}
             }))


    async def handle_submit_prompt(self, prompt_text):
        room = game_rooms[self.room_group_name]
        if room['state'] == 'prompting' and prompt_text:
            if self.player_id not in room['prompts']: # 防止重複提交
                room['prompts'][self.player_id] = prompt_text
                # 將題目加入對應玩家的故事本開頭
                room['books'][self.player_id].append({'type': 'prompt', 'data': prompt_text, 'player': self.player_id})

                print(f"Player {self.player_id} submitted prompt: {prompt_text}")

                # 檢查是否所有人都提交了題目
                if len(room['prompts']) == len(room['players']):
                    print(f"All prompts received in {self.room_group_name}. Moving to drawing round.")
                    await self.start_drawing_round()
                else:
                    # 可以選擇性地廣播進度
                    await self.broadcast_game_state(f"{len(room['prompts'])} / {len(room['players'])} 位玩家已提交題目")


    async def handle_submit_drawing(self, drawing_data):
        room = game_rooms[self.room_group_name]
        assignment_key = f"drawing_{self.player_id}" # 假設用這個 key 儲存繪畫任務

        if room['state'] == 'drawing' and drawing_data and self.player_id in room['assignments']:
            task = room['assignments'].pop(self.player_id) # 獲取並移除已完成的任務
            original_player_id = task['original_player_id']

            # 將繪畫加入對應的故事本
            room['books'][original_player_id].append({'type': 'drawing', 'data': drawing_data, 'player': self.player_id})
            print(f"Player {self.player_id} submitted drawing for book {original_player_id}")


            # 檢查是否所有繪畫都已提交
            if not room['assignments']: # 如果 assignments 為空，表示本輪所有繪畫完成
                print(f"All drawings received for round {room['current_round']} in {self.room_group_name}. Moving to guessing round.")
                await self.start_guessing_round()
            else:
                 await self.broadcast_game_state(f"等待其他 {len(room['assignments'])} 位玩家完成繪畫...")


    async def handle_submit_guess(self, guess_text):
        room = game_rooms[self.room_group_name]
        assignment_key = f"guess_{self.player_id}" # 假設用這個 key 儲存猜測任務

        if room['state'] == 'guessing' and guess_text and self.player_id in room['assignments']:
            task = room['assignments'].pop(self.player_id) # 獲取並移除已完成的任務
            original_player_id = task['original_player_id']

            # 將猜測加入對應的故事本
            room['books'][original_player_id].append({'type': 'guess', 'data': guess_text, 'player': self.player_id})
            print(f"Player {self.player_id} submitted guess for book {original_player_id}")


            # 檢查是否所有猜測都已提交
            if not room['assignments']: # 如果 assignments 為空，表示本輪所有猜測完成
                print(f"All guesses received for round {room['current_round']} in {self.room_group_name}.")
                # 判斷遊戲是否結束或進入下一輪繪畫
                if room['current_round'] >= len(room['players']) -1 : # 輪數達到玩家數 - 1
                     await self.finish_game()
                else:
                     await self.start_drawing_round() # 開始下一輪繪畫
            else:
                 await self.broadcast_game_state(f"等待其他 {len(room['assignments'])} 位玩家完成猜測...")

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


    # --- 遊戲流程控制函數 ---
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


    # --- 廣播和發送輔助函數 ---
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
            # (包括 game_state_update, chat, request_prompt, game_over 等)
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

    async def handle_user_info(self, payload):
        room = game_rooms[self.room_group_name]
        if self.player_id in room['players']:
            display_name = payload.get('displayName', '未命名玩家')
            room['players'][self.player_id]['name'] = display_name
            await self.broadcast_game_state(f"玩家 {display_name} 加入了房間")
