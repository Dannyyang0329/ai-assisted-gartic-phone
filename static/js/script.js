document.addEventListener('DOMContentLoaded', function() {
    gsap.registerPlugin(TextPlugin);

    // Logo animation
    gsap.from(".logo", {duration: 1, y: -50, opacity: 0, ease: "bounce.out", delay: 0.2});

    // Intro section animations
    if (document.querySelector('.intro-section')) {
        gsap.from(".tagline", {duration: 1, y: 30, opacity: 0, ease: "power2.out", delay: 0.5});
        // Animate tagline's span for a "typing" or "reveal" effect if desired
        // gsap.from(".tagline span", {duration: 1, text: "", delay: 0.7, ease: "none"}); // Example for TextPlugin

        gsap.from(".app-description", {duration: 1, y: 30, opacity: 0, ease: "power2.out", delay: 0.8});
        
        // Animate feature items (text and icon together)
        gsap.from(".feature-item", {
            duration: 0.8, 
            opacity: 0, 
            y: 20, 
            stagger: 0.25, // Slightly increased stagger for more pronounced effect
            delay: 1.2, 
            ease: "power2.out"
        });
        // Animate feature icons specifically for a bit more flair
        gsap.from(".feature-icon", {
            duration: 0.9,
            scale: 0.5, 
            opacity: 0, 
            stagger: 0.25, 
            delay: 1.3, // Start slightly after feature-item container
            ease: "elastic.out(1.2, 0.6)" // Adjusted elasticity
        });
    }
    
    // Card animation (for the form card)
    gsap.from(".card", {duration: 1, opacity: 0, y: 50, ease: "power2.out", delay: 0.4}); // Adjusted delay


    // 設置範例房間
    const recentRooms = ['創意空間', '夢境畫布', '藝術時光', '色彩實驗', '靈感工坊'];
    const recentRoomsList = document.getElementById('recent-rooms-list');
    
    if (recentRoomsList && recentRooms.length > 0) {
        recentRooms.forEach((room, index) => {
            const li = document.createElement('li');
            li.className = 'room-item';
            li.innerHTML = `<span class="room-item-icon"></span>${room}`;
            
            // GSAP 加入動畫效果
            gsap.from(li, {
                duration: 0.6, 
                opacity: 0, 
                y: 25, 
                ease: "power2.out", 
                delay: 1.8 + index * 0.12 // Delay after intro animations, adjusted timing
            });
            
            li.onclick = function() {
                const input = document.getElementById('room-name-input');
                input.value = room;
                input.focus();
                
                // GSAP 添加視覺反饋
                gsap.to(li, {
                    backgroundColor: 'var(--secondary)', 
                    color: 'white', 
                    scale: 1.05, // Add a slight scale effect
                    duration: 0.15, 
                    yoyo: true, 
                    repeat: 1,
                    ease: "power1.inOut"
                });
            };
            recentRoomsList.appendChild(li);
        });
    }
    
    // 檢查URL參數
    const urlParams = new URLSearchParams(window.location.search);
    const errorType = urlParams.get('error');
    const rejectedUserId = urlParams.get('userid');
    const redirectRoom = urlParams.get('redirect_room');
    const roomType = urlParams.get('room_type');

    // Tooltip function using GSAP
    function showTooltip(element, message) {
        const tooltip = document.createElement('div');
        tooltip.className = 'tooltip-error'; // You might want a generic 'tooltip' class and add 'tooltip-error' for specific styling
        tooltip.textContent = message;
        document.body.appendChild(tooltip);

        const rect = element.getBoundingClientRect();
        gsap.set(tooltip, {
            top: rect.top - tooltip.offsetHeight - 8, // Position above the element, slightly more space
            left: rect.left + (element.offsetWidth / 2) - (tooltip.offsetWidth / 2), // Center horizontally
            opacity: 0,
            scale: 0.85 // Start slightly smaller
        });

        gsap.to(tooltip, {
            opacity: 1,
            scale: 1,
            duration: 0.3,
            ease: "back.out(1.7)" // A bit more bouncy
        });

        setTimeout(() => {
            gsap.to(tooltip, {
                opacity: 0,
                scale: 0.85,
                y: -10, // Move up slightly on exit
                duration: 0.3,
                ease: "power2.in",
                onComplete: () => tooltip.remove()
            });
        }, 2500); // Slightly longer display time
    }

    // 處理從其他頁面重定向過來的請求
    if (redirectRoom) {
        const roomInput = document.getElementById('room-name-input');
        if (roomInput) {
            roomInput.value = redirectRoom;
        }

        // 自動淡出 redirect-notice
        const redirectNotice = document.querySelector('.redirect-notice');
        if (redirectNotice) {
            gsap.to(redirectNotice, {
                delay: 3, // 3秒後淡出
                opacity: 0, 
                y: -20, // Slide up on fade out
                duration: 0.5, 
                ease: "power2.in",
                onComplete: () => {
                    if (redirectNotice.parentNode) {
                        redirectNotice.remove();
                    }
                }
            });
        }
        
        // 顯示提示，指示用戶需要輸入ID
        const userIdInput = document.querySelector('#user-id-input');
        if (userIdInput && !rejectedUserId) {
            // 如果沒有被拒絕的用戶ID，聚焦到用戶ID輸入框
            userIdInput.focus();
            userIdInput.classList.add('highlight');
            
            // 2秒後移除高亮效果
            setTimeout(() => {
                userIdInput.classList.remove('highlight');
            }, 2000);
            
            // 顯示提示信息
            const userIdStatus = document.querySelector('#userid-status');
            if (userIdStatus) {
                const userIdStatusText = userIdStatus.querySelector('.userid-status-text');
                userIdStatus.className = 'userid-status visible';
                userIdStatusText.textContent = '請輸入一個用戶ID以繼續';
            }
        }    
    }
    
    // 處理錯誤消息
    if (errorType) {
        const userIdInput = document.querySelector('#user-id-input');
        const userIdStatus = document.querySelector('#userid-status');
        const userIdStatusIcon = userIdStatus.querySelector('.userid-status-icon');
        const userIdStatusText = userIdStatus.querySelector('.userid-status-text');
        
        userIdStatus.className = 'userid-status visible unavailable';
        userIdStatusIcon.textContent = '✗';
        
        if (errorType === 'userid_taken' && rejectedUserId) {
            // 如果有用戶ID被拒絕的錯誤
            userIdInput.value = rejectedUserId;
            userIdStatusText.textContent = '此ID已被其他人使用';
        } else if (errorType === 'invalid_length') {
            // 如果用戶ID長度不符合要求
            userIdStatusText.textContent = '用戶ID長度必須在3-20個字符之間';
        }
        
        // 聚焦到用戶ID輸入框
        userIdInput.focus();
        userIdInput.classList.add('highlight');
        
        // 2秒後移除高亮效果
        setTimeout(() => {
            userIdInput.classList.remove('highlight');
        }, 2000);
    }
    
    // 輸入框事件處理
    document.querySelector('#room-name-input').addEventListener('keyup', function(e) {
        if (e.key === 'Enter') {
            document.querySelector('#room-name-submit').click();
        }
    });
    
    // 用戶 ID 輸入事件處理
    const userIdInput = document.querySelector('#user-id-input');
    const userIdStatus = document.querySelector('#userid-status');
    const userIdStatusIcon = userIdStatus.querySelector('.userid-status-icon');
    const userIdStatusText = userIdStatus.querySelector('.userid-status-text');
    
    let checkTimeout = null;
    userIdInput.addEventListener('input', function() {
        const userId = this.value.trim();
        
        // 清除之前的超時
        if (checkTimeout) {
            clearTimeout(checkTimeout);
        }
        
        // 重置狀態區域並使用 GSAP 顯示
        userIdStatus.className = 'userid-status visible checking'; 
        gsap.killTweensOf(userIdStatus); 
        gsap.fromTo(userIdStatus, 
            { height: 0, opacity: 0, marginBottom: 0 }, 
            { height: "auto", opacity: 1, marginBottom: "5px", duration: 0.35, ease: "power2.out" } // Slightly smoother ease
        );
        userIdStatusIcon.textContent = '?';
        gsap.to(userIdStatusText, {duration: 0.3, text: "檢查中...", ease: "none"});
        gsap.fromTo(userIdStatusIcon, {scale:0.7, opacity:0}, {scale:1, opacity:1, duration:0.4, ease:"elastic.out(1, 0.6)"});


        // 如果用戶 ID 為空，使用 GSAP 隱藏狀態
        if (!userId) {
            gsap.to(userIdStatus, {
                height: 0, 
                opacity: 0, 
                marginBottom: 0, 
                duration: 0.3, 
                ease: "power2.in",
                onComplete: () => userIdStatus.className = 'userid-status' 
            });
            return;
        }
        
        // 設置延遲以避免頻繁請求
        checkTimeout = setTimeout(() => {
            fetch(`/game/check-userid/?userid=${encodeURIComponent(userId)}`)
                .then(response => response.json())
                .then(data => {
                    if (data.available) {
                        userIdStatus.className = 'userid-status visible available';
                        userIdStatusIcon.textContent = '✓';
                        gsap.to(userIdStatusText, {duration: 0.3, text: data.message, ease: "none"});
                    } else {
                        userIdStatus.className = 'userid-status visible unavailable';
                        userIdStatusIcon.textContent = '✗';
                        gsap.to(userIdStatusText, {duration: 0.3, text: data.message, ease: "none"});
                    }
                    // Animate icon change
                    gsap.fromTo(userIdStatusIcon, {scale:0.5, opacity:0}, {scale:1, opacity:1, duration:0.4, ease:"elastic.out(1, 0.6)"});
                })
                .catch(error => {
                    console.error('檢查用戶 ID 時出錯:', error);
                    userIdStatus.className = 'userid-status visible unavailable';
                    userIdStatusIcon.textContent = '!';
                    gsap.to(userIdStatusText, {duration: 0.3, text: '檢查時發生錯誤', ease: "none"});
                    gsap.fromTo(userIdStatusIcon, {scale:0.5, opacity:0}, {scale:1, opacity:1, duration:0.4, ease:"elastic.out(1, 0.6)"});
                });
        }, 500); // 500ms 延遲，避免頻繁請求
    });
    
    // 提交按鈕事件處理
    document.querySelector('#room-name-submit').addEventListener('click', function() {
        const roomInput = document.querySelector('#room-name-input');
        const userIdInput = document.querySelector('#user-id-input');
        const roomName = roomInput.value.trim();
        const userId = userIdInput.value.trim();
        const submitButton = this;
        
        // 驗證房間名稱
        if (roomName === '') {
            showTooltip(roomInput, '請輸入房間名稱');
            roomInput.focus();
            return;
        }
        
        // 驗證用戶ID
        if (userId === '') {
            // 顯示錯誤提示
            const userIdStatus = document.querySelector('#userid-status');
            if (userIdStatus) {
                userIdStatus.className = 'userid-status visible unavailable'; 
                gsap.killTweensOf(userIdStatus);
                gsap.fromTo(userIdStatus, 
                    { height: 0, opacity: 0, marginBottom: 0 }, 
                    { height: "auto", opacity: 1, marginBottom: "5px", duration: 0.35, ease: "power2.out" }
                );
                const userIdStatusText = userIdStatus.querySelector('.userid-status-text');
                gsap.to(userIdStatusText, {duration: 0.3, text: '請輸入一個用戶ID', ease: "none"});
                 const icon = userIdStatus.querySelector('.userid-status-icon');
                 if(icon) {
                    icon.textContent = '✗';
                    gsap.fromTo(icon, {scale:0.5, opacity:0}, {scale:1, opacity:1, duration:0.4, ease:"elastic.out(1, 0.6)"});
                 }
            }
            userIdInput.focus();
            return;
        }
        
        // 檢查ID是否可用，然後跳轉
        gsap.to(submitButton, {duration: 0.2, innerHTML: '檢查中...', ease:"none"});
        submitButton.disabled = true;
        
        fetch(`/game/check-userid/?userid=${encodeURIComponent(userId)}`)
            .then(response => response.json())
            .then(data => {
                if (data.available) {
                    // ID依然可用，將用戶ID存儲在sessionStorage中
                    sessionStorage.setItem('artflow_userid', userId);
                    
                    // 構建URL到Waiting Room (不再包含userid)
                    let url = `/waiting_room/${encodeURIComponent(roomName)}/`;
                    window.location.href = url;
                } else {
                    // ID已不可用，顯示錯誤信息
                    submitButton.innerHTML = '開始創作';
                    submitButton.disabled = false;
                    
                    // 更新用戶ID狀態顯示
                    const userIdStatus = document.querySelector('#userid-status');
                    if (userIdStatus) {
                        const userIdStatusIcon = userIdStatus.querySelector('.userid-status-icon');
                        const userIdStatusText = userIdStatus.querySelector('.userid-status-text');
                        userIdStatus.className = 'userid-status visible unavailable';
                        userIdStatusIcon.textContent = '✗';
                        gsap.to(userIdStatusText, {duration: 0.3, text: '此 ID 已被其他人使用', ease: "none"});
                        gsap.fromTo(userIdStatusIcon, {scale:0.5, opacity:0}, {scale:1, opacity:1, duration:0.4, ease:"elastic.out(1, 0.6)"});
                    }
                    
                    // 聚焦到用戶ID輸入框
                    userIdInput.focus();
                }
            })
            .catch(error => {
                console.error('檢查用戶 ID 時出錯:', error);
                submitButton.innerHTML = '開始創作';
                submitButton.disabled = false;
            });
    });
});
