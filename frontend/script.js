// ============ تنظیمات ============
const API_BASE = window.location.origin;

let currentUser = null;
let currentUsername = '';
let currentChatUser = null;
let currentChatGroup = null;
let ws = null;
let token = '';
let userList = [];
let contactList = [];
let groupList = [];
let pendingRequests = [];
let sentRequests = [];
let isAtBottom = true;
let newMessageCount = 0;
let renderedMessageIds = new Set();
let currentTab = 'all';
let typingTimeout = null;
let userOnlineNotified = new Set();
let replyToMessage = null;

// ============ توابع کمکی ============
function showLogin() {
    document.getElementById('loginPage').classList.add('active');
    document.getElementById('registerPage').classList.remove('active');
    document.getElementById('chatPage').classList.remove('active');
}

function showRegister() {
    document.getElementById('loginPage').classList.remove('active');
    document.getElementById('registerPage').classList.add('active');
    document.getElementById('chatPage').classList.remove('active');
}

function showChat() {
    document.getElementById('loginPage').classList.remove('active');
    document.getElementById('registerPage').classList.remove('active');
    document.getElementById('chatPage').classList.add('active');
}

function showMessage(element, text, type) {
    element.textContent = text;
    element.className = 'message ' + type;
}

function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// ============ ثبت نام ============
async function register() {
    const username = document.getElementById('registerUsername').value.trim();
    const email = document.getElementById('registerEmail').value.trim();
    const password = document.getElementById('registerPassword').value;
    const msg = document.getElementById('registerMessage');

    if (!username || !email || !password) {
        showMessage(msg, '❌ لطفاً تمام فیلدها را پر کنید', 'error');
        return;
    }

    showMessage(msg, '⏳ در حال ارسال...', 'loading');

    try {
        const response = await fetch(`${API_BASE}/api/register`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username, email, password })
        });

        const data = await response.json();

        if (response.ok) {
            showMessage(msg, '✅ ثبت نام موفق!', 'success');
            document.getElementById('registerUsername').value = '';
            document.getElementById('registerEmail').value = '';
            document.getElementById('registerPassword').value = '';
            setTimeout(() => showLogin(), 1500);
        } else {
            showMessage(msg, '❌ ' + (data.detail || 'خطای ناشناخته'), 'error');
        }
    } catch (error) {
        console.error('Error:', error);
        showMessage(msg, '❌ خطا در ارتباط با سرور', 'error');
    }
}

// ============ ورود ============
async function login() {
    const username = document.getElementById('loginUsername').value.trim();
    const password = document.getElementById('loginPassword').value;
    const msg = document.getElementById('loginMessage');

    if (!username || !password) {
        showMessage(msg, '❌ لطفاً نام کاربری و رمز عبور را وارد کنید', 'error');
        return;
    }

    showMessage(msg, '⏳ در حال ارسال...', 'loading');

    try {
        const response = await fetch(`${API_BASE}/api/login`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username, password })
        });

        const data = await response.json();

        if (response.ok) {
            token = data.access_token;
            currentUser = data.user_id;
            currentUsername = data.username;

            showMessage(msg, '✅ ورود موفق!', 'success');

            if ('Notification' in window && Notification.permission === 'default') {
                Notification.requestPermission();
            }

            showChat();
            connectWebSocket();
            loadUsers();
            loadContacts();
            loadGroups();
            loadPendingRequests();
        } else {
            showMessage(msg, '❌ ' + (data.detail || 'نام کاربری یا رمز اشتباه'), 'error');
        }
    } catch (error) {
        console.error('Error:', error);
        showMessage(msg, '❌ خطا در ارتباط با سرور', 'error');
    }
}

// ============ WebSocket ============
function connectWebSocket() {
    if (!token) return;

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = window.location.host;
    const wsUrl = `${protocol}//${host}/ws?token=${token}`;

    console.log('🔌 اتصال WebSocket:', wsUrl);
    ws = new WebSocket(wsUrl);

    ws.onopen = function () {
        console.log('✅ WebSocket متصل شد');
        document.getElementById('statusDot').classList.add('connected');
        document.getElementById('statusText').textContent = 'متصل';
    };

    ws.onmessage = function (event) {
        try {
            const data = JSON.parse(event.data);

            if (data.type === 'new_message') {
                handleNewMessage(data.message);
            } else if (data.type === 'message_edited') {
                updateMessageInUI(data.message);
            } else if (data.type === 'message_deleted') {
                removeMessageFromUI(data.message.id);
            } else if (data.type === 'user_online') {
                loadUsers();
                if (data.user_id !== currentUser && data.ask_contact) {
                    showUserOnlineNotification(data.user_id, data.username);
                }
            } else if (data.type === 'user_offline') {
                loadUsers();
            } else if (data.type === 'typing') {
                handleTypingIndicator(data);
            } else if (data.type === 'contact_request') {
                showContactRequestNotification(data.from);
                loadPendingRequests();
            } else if (data.type === 'contact_accepted') {
                showNotification(`✅ ${data.by.username} درخواست شما را قبول کرد`, 'success');
                loadContacts();
                loadUsers();
            } else if (data.type === 'group_member_left') {
                showNotification(`👋 ${data.user.username} از گروه خارج شد`, 'info');
                loadGroups();
            }
        } catch (e) {
            console.error('❌ خطا در پردازش WebSocket:', e);
        }
    };

    ws.onclose = function () {
        console.log('⚠️ WebSocket قطع شد');
        document.getElementById('statusDot').classList.remove('connected');
        document.getElementById('statusText').textContent = 'قطع شده';
        if (currentUser) {
            setTimeout(connectWebSocket, 3000);
        }
    };

    ws.onerror = function (error) {
        console.error('❌ WebSocket error:', error);
    };
}

function handleNewMessage(message) {
    if (renderedMessageIds.has(message.id)) {
        loadUsers();
        return;
    }

    const isMyMessage = message.sender_id === currentUser;
    const isCurrentChat =
        (message.receiver_id && message.receiver_id === currentChatUser) ||
        (message.group_id && message.group_id === currentChatGroup);

    if (isMyMessage) {
        if (isCurrentChat) displayMessage(message, true);
    } else {
        if (isCurrentChat) {
            displayMessage(message, false);
            if (!isAtBottom) {
                newMessageCount++;
                showScrollToBottomButton();
            }
        } else {
            const sender = userList.find(u => u.id === message.sender_id);
            if (sender) {
                showNotification(`📩 پیام جدید از ${sender.username}`, 'info');
                sendBrowserNotification('پیام جدید', `از ${sender.username}`);
            }
        }
    }
    loadUsers();
}

// ============ تایپ ============
function onTyping() {
    if (!ws || ws.readyState !== WebSocket.OPEN) return;

    const target = currentChatUser
        ? { receiver_id: currentChatUser }
        : currentChatGroup
        ? { group_id: currentChatGroup }
        : null;

    if (!target) return;

    if (typingTimeout) clearTimeout(typingTimeout);

    ws.send(JSON.stringify({ type: 'typing', ...target }));

    typingTimeout = setTimeout(() => {
        ws.send(JSON.stringify({ type: 'stop_typing', ...target }));
    }, 2000);
}

function handleTypingIndicator(data) {
    const isCurrent =
        (data.sender_id === currentChatUser) ||
        (data.group_id && data.group_id === currentChatGroup);

    if (!isCurrent) return;

    const indicator = document.getElementById('typingIndicator');
    if (data.is_typing) {
        indicator.style.display = 'flex';
        if (isAtBottom) {
            const container = document.getElementById('chatContainer');
            setTimeout(() => container.scrollTop = container.scrollHeight, 50);
        }
    } else {
        indicator.style.display = 'none';
    }
}

// ============ نوتیفیکیشن مرورگر ============
function sendBrowserNotification(title, body) {
    if ('Notification' in window && Notification.permission === 'granted') {
        if (document.hidden) {
            new Notification(title, { body: body });
        }
    }
}

// ============ تب‌ها ============
function switchTab(tab, btn) {
    currentTab = tab;
    document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
    if (btn) btn.classList.add('active');

    if (tab === 'all') {
        renderUsers();
    } else if (tab === 'groups') {
        renderGroups();
    } else if (tab === 'requests') {
        renderRequests();
    }
}

// ============ لیست مخاطبان ============
async function loadUsers() {
    try {
        const response = await fetch(`${API_BASE}/api/users`, {
            headers: { 'Authorization': `Bearer ${token}` }
        });

        if (response.ok) {
            userList = await response.json();
            const onlineCount = userList.filter(u => u.is_online).length;
            document.getElementById('onlineCount').textContent = onlineCount;

            if (currentTab === 'all') {
                renderUsers();
            }
        }
    } catch (error) {
        console.error('خطا:', error);
    }
}

function renderUsers() {
    const usersList = document.getElementById('usersList');

    if (userList.length === 0) {
        usersList.innerHTML = '<div class="loading">هنوز مخاطبی ندارید</div>';
        return;
    }

    usersList.innerHTML = '';
    userList.forEach(user => {
        const div = document.createElement('div');
        div.className = 'user-item';
        if (currentChatUser === user.id) div.classList.add('active');

        div.innerHTML = `
            <div class="user-info">
                <span class="user-status ${user.is_online ? 'online' : 'offline'}"></span>
                <span>${escapeHtml(user.username)}</span>
            </div>
        `;
        div.onclick = () => openChat(user);
        usersList.appendChild(div);
    });
}

// ============ لیست مخاطبان (Contacts) ============
async function loadContacts() {
    try {
        const response = await fetch(`${API_BASE}/api/contacts`, {
            headers: { 'Authorization': `Bearer ${token}` }
        });

        if (response.ok) {
            contactList = await response.json();
        }
    } catch (error) {
        console.error('خطا:', error);
    }
}

// ============ لیست گروه‌ها ============
async function loadGroups() {
    try {
        const response = await fetch(`${API_BASE}/api/groups`, {
            headers: { 'Authorization': `Bearer ${token}` }
        });

        if (response.ok) {
            groupList = await response.json();
            if (currentTab === 'groups') {
                renderGroups();
            }
        }
    } catch (error) {
        console.error('خطا:', error);
    }
}

function renderGroups() {
    const usersList = document.getElementById('usersList');

    if (groupList.length === 0) {
        usersList.innerHTML = '<div class="loading">هنوز گروهی ندارید</div>';
        return;
    }

    usersList.innerHTML = '';
    groupList.forEach(group => {
        const div = document.createElement('div');
        div.className = 'user-item';
        if (currentChatGroup === group.id) div.classList.add('active');

        div.innerHTML = `
            <div class="user-info">
                <span class="user-avatar">👥</span>
                <span>${escapeHtml(group.name)}</span>
            </div>
            <span style="font-size:11px;color:#999;">${group.members.length} عضو</span>
        `;
        div.onclick = () => openGroupChat(group);
        usersList.appendChild(div);
    });
}

// ============ درخواست‌ها ============
async function loadPendingRequests() {
    try {
        const response = await fetch(`${API_BASE}/api/contacts/pending`, {
            headers: { 'Authorization': `Bearer ${token}` }
        });

        if (response.ok) {
            pendingRequests = await response.json();
            updateRequestsBadge();
            if (currentTab === 'requests') {
                renderRequests();
            }
        }
    } catch (error) {
        console.error('Error:', error);
    }
}

function updateRequestsBadge() {
    const badge = document.getElementById('requestsBadge');
    if (pendingRequests.length > 0) {
        badge.textContent = pendingRequests.length;
        badge.style.display = 'inline-block';
    } else {
        badge.style.display = 'none';
    }
}

function renderRequests() {
    const usersList = document.getElementById('usersList');

    if (pendingRequests.length === 0) {
        usersList.innerHTML = '<div class="loading">درخواستی ندارید</div>';
        return;
    }

    usersList.innerHTML = '';
    pendingRequests.forEach(req => {
        const div = document.createElement('div');
        div.className = 'user-item';
        div.innerHTML = `
            <div class="user-info">
                <span>👤 ${escapeHtml(req.user.username)}</span>
            </div>
            <div style="display:flex;gap:4px;">
                <button class="request-btn" style="background:#4caf50 !important;"
                        onclick="event.stopPropagation(); acceptContact(${req.request_id}, this)">✅</button>
                <button class="request-btn" style="background:#e74c3c !important;"
                        onclick="event.stopPropagation(); rejectContact(${req.request_id}, this)">❌</button>
            </div>
        `;
        usersList.appendChild(div);
    });
}

async function requestContact(userId) {
    try {
        const response = await fetch(`${API_BASE}/api/contacts/request/${userId}`, {
            method: 'POST',
            headers: { 'Authorization': `Bearer ${token}` }
        });

        const data = await response.json();

        if (response.ok) {
            showNotification('✅ درخواست ارسال شد', 'success');
        } else {
            showNotification('❌ ' + (data.detail || 'خطا'), 'error');
        }
    } catch (error) {
        console.error('Error:', error);
        showNotification('❌ خطا در ارتباط', 'error');
    }
}

async function acceptContact(requestId, btn) {
    try {
        const response = await fetch(`${API_BASE}/api/contacts/accept/${requestId}`, {
            method: 'POST',
            headers: { 'Authorization': `Bearer ${token}` }
        });

        if (response.ok) {
            showNotification('✅ قبول شد', 'success');
            loadPendingRequests();
            loadContacts();
            loadUsers();
            renderRequests();
        }
    } catch (error) {
        console.error('Error:', error);
    }
}

async function rejectContact(requestId, btn) {
    try {
        const response = await fetch(`${API_BASE}/api/contacts/reject/${requestId}`, {
            method: 'POST',
            headers: { 'Authorization': `Bearer ${token}` }
        });

        if (response.ok) {
            loadPendingRequests();
            renderRequests();
        }
    } catch (error) {
        console.error('Error:', error);
    }
}

function showContactRequestNotification(user, requestId = null) {
    const notifications = document.getElementById('notifications');
    const notif = document.createElement('div');
    notif.className = 'notification info';
    const reqId = requestId || user.request_id;
    notif.innerHTML = `
        <span>👤 <strong>${escapeHtml(user.username)}</strong> می‌خواهد مخاطب شود</span>
        <div class="notification-actions">
            <button class="accept-btn" onclick="acceptContact(${reqId}, this); this.parentElement.parentElement.remove();">✅</button>
            <button class="reject-btn" onclick="rejectContact(${reqId}, this); this.parentElement.parentElement.remove();">❌</button>
        </div>
    `;
    notifications.appendChild(notif);
    setTimeout(() => notif.remove(), 15000);
}

function showUserOnlineNotification(userId, username) {
    if (userOnlineNotified.has(userId)) return;
    userOnlineNotified.add(userId);

    const notifications = document.getElementById('notifications');
    const notif = document.createElement('div');
    notif.className = 'notification info';
    notif.innerHTML = `
        <span>👤 <strong>${escapeHtml(username)}</strong> وارد شد</span>
        <div class="notification-actions">
            <button class="accept-btn" onclick="requestContact(${userId}); this.parentElement.parentElement.remove();">➕ مخاطب</button>
            <button class="reject-btn" onclick="this.parentElement.parentElement.remove();">✖</button>
        </div>
    `;
    notifications.appendChild(notif);
    setTimeout(() => notif.remove(), 15000);
}

function showNotification(text, type = 'info') {
    const notifications = document.getElementById('notifications');
    const notif = document.createElement('div');
    notif.className = 'notification ' + type;
    notif.textContent = text;
    notifications.appendChild(notif);
    setTimeout(() => notif.remove(), 4000);
}

// ============ باز کردن چت خصوصی ============
async function openChat(user) {
    currentChatUser = user.id;
    currentChatGroup = null;
    newMessageCount = 0;
    cancelReply();
    document.getElementById('scrollToBottomBtn').style.display = 'none';
    document.getElementById('typingIndicator').style.display = 'none';
    renderedMessageIds.clear();

    try {
        const response = await fetch(`${API_BASE}/api/messages/${user.id}`, {
            headers: { 'Authorization': `Bearer ${token}` }
        });

        if (response.ok) {
            const messages = await response.json();
            const messagesDiv = document.getElementById('messages');
            messagesDiv.innerHTML = '';

            if (messages.length === 0) {
                messagesDiv.innerHTML = '<div class="loading">هنوز پیامی نیست</div>';
            } else {
                messages.forEach(msg => {
                    const isSent = msg.sender_id === currentUser;
                    displayMessage(msg, isSent, true);
                });
            }

            setTimeout(scrollToBottom, 100);
        }
    } catch (error) {
        console.error('خطا:', error);
    }
}

// ============ باز کردن چت گروهی ============
async function openGroupChat(group) {
    currentChatGroup = group.id;
    currentChatUser = null;
    newMessageCount = 0;
    cancelReply();
    document.getElementById('scrollToBottomBtn').style.display = 'none';
    document.getElementById('typingIndicator').style.display = 'none';
    renderedMessageIds.clear();

    try {
        const response = await fetch(`${API_BASE}/api/groups/${group.id}/messages`, {
            headers: { 'Authorization': `Bearer ${token}` }
        });

        if (response.ok) {
            const messages = await response.json();
            const messagesDiv = document.getElementById('messages');
            messagesDiv.innerHTML = '';

            if (messages.length === 0) {
                messagesDiv.innerHTML = '<div class="loading">هنوز پیامی نیست</div>';
            } else {
                messages.forEach(msg => {
                    const isSent = msg.sender_id === currentUser;
                    displayMessage(msg, isSent, true);
                });
            }

            setTimeout(scrollToBottom, 100);
        }
    } catch (error) {
        console.error('خطا:', error);
    }
}

// ============ نمایش پیام ============
function displayMessage(message, isSent, skipDuplicateCheck = false) {
    if (!skipDuplicateCheck && renderedMessageIds.has(message.id)) return;
    renderedMessageIds.add(message.id);

    const messagesDiv = document.getElementById('messages');
    const placeholder = messagesDiv.querySelector('div.loading');
    if (placeholder) placeholder.remove();

    const msgDiv = document.createElement('div');
    msgDiv.className = `chat-message ${isSent ? 'sent' : 'received'}`;
    msgDiv.dataset.messageId = message.id;

    const timeStr = formatTime(message.timestamp);

    if (message.is_deleted) {
        msgDiv.innerHTML = `
            <em style="opacity:0.5;">این پیام حذف شده است</em>
            <div class="message-time">${timeStr}</div>
        `;
        msgDiv.style.opacity = '0.5';
    } else {
        let contentHtml = '';

        if (message.message_type === 'image' && message.file_url) {
            contentHtml = `<img src="${message.file_url}" alt="image" onclick="window.open('${message.file_url}', '_blank')">`;
        } else if (message.message_type === 'file' && message.file_url) {
            contentHtml = `<a href="${message.file_url}" target="_blank">📎 دانلود فایل</a>`;
        } else {
            contentHtml = escapeHtml(message.content);
        }

        const editBadge = message.is_edited
            ? ' <span style="font-size:10px;opacity:0.5;">(ویرایش شده)</span>'
            : '';

        // اسم فرستنده (فقط توی گروه)
        const senderName = (!isSent && message.group_id && message.sender_username)
            ? `<div class="sender-name">${escapeHtml(message.sender_username)}</div>`
            : '';

        // نقل‌قول (Reply)
        let replyHtml = '';
        if (message.reply_to) {
            replyHtml = `
                <div class="message-reply" onclick="scrollToMessage(${message.reply_to.id})">
                    <span class="reply-sender-name">${escapeHtml(message.reply_to.sender_username)}</span>
                    <div class="reply-content">${escapeHtml(message.reply_to.content)}</div>
                </div>
            `;
        }

        const actions = `
            <div class="message-actions">
                <button onclick="startReply(${message.id}, '${escapeHtml(message.content).replace(/'/g, "\\'")}', '${escapeHtml(message.sender_username || currentUsername)}')">↩️</button>
                ${isSent ? `
                    <button onclick="startEditMessage(${message.id})">✏️</button>
                    <button onclick="deleteMessage(${message.id})">🗑️</button>
                ` : ''}
            </div>
        `;

        msgDiv.innerHTML = `
            ${senderName}
            ${replyHtml}
            <div class="message-content">${contentHtml}${editBadge}</div>
            <div class="message-time">${timeStr}</div>
            ${actions}
        `;
    }

    messagesDiv.appendChild(msgDiv);

    if (isAtBottom) {
        setTimeout(scrollToBottom, 50);
    }
}

// ============ Reply ============
function startReply(messageId, content, senderName) {
    replyToMessage = {
        id: messageId,
        content: content,
        sender: senderName
    };

    document.getElementById('replySender').textContent = senderName;
    document.getElementById('replyText').textContent = content.substring(0, 100);
    document.getElementById('replyBox').style.display = 'flex';
    document.getElementById('messageInput').focus();
}

function cancelReply() {
    replyToMessage = null;
    document.getElementById('replyBox').style.display = 'none';
}

function scrollToMessage(messageId) {
    const msgEl = document.querySelector(`[data-message-id="${messageId}"]`);
    if (msgEl) {
        msgEl.scrollIntoView({ behavior: 'smooth', block: 'center' });
        msgEl.style.transition = 'background 0.5s';
        msgEl.style.background = 'rgba(255, 235, 59, 0.5)';
        setTimeout(() => {
            msgEl.style.background = '';
        }, 1500);
    }
}

// ============ فرمت زمان ============
function formatTime(timestamp) {
    try {
        if (!timestamp) return nowTime();
        let date;
        if (typeof timestamp === 'string') {
            let ts = timestamp.replace(' ', 'T');
            if (!ts.endsWith('Z') && !ts.includes('+')) ts += 'Z';
            date = new Date(ts);
        } else {
            date = new Date(timestamp);
        }
        if (isNaN(date.getTime())) return nowTime();
        return date.toLocaleTimeString('fa-IR', { hour: '2-digit', minute: '2-digit' });
    } catch (e) {
        return nowTime();
    }
}

function nowTime() {
    return new Date().toLocaleTimeString('fa-IR', { hour: '2-digit', minute: '2-digit' });
}

// ============ اسکرول ============
function showScrollToBottomButton() {
    const btn = document.getElementById('scrollToBottomBtn');
    btn.style.display = 'block';
    btn.textContent = `⬇️ رفتن به آخرین پیام (${newMessageCount})`;
}

function scrollToBottom() {
    const container = document.getElementById('chatContainer');
    container.scrollTop = container.scrollHeight;
    isAtBottom = true;
    newMessageCount = 0;
    document.getElementById('scrollToBottomBtn').style.display = 'none';
}

function checkScrollPosition() {
    const container = document.getElementById('chatContainer');
    const threshold = 100;
    const isNearBottom = container.scrollHeight - container.scrollTop - container.clientHeight < threshold;
    if (isNearBottom) {
        isAtBottom = true;
        document.getElementById('scrollToBottomBtn').style.display = 'none';
        newMessageCount = 0;
    } else {
        isAtBottom = false;
    }
}

// ============ ویرایش ============
function startEditMessage(messageId) {
    const msgEl = document.querySelector(`[data-message-id="${messageId}"]`);
    if (!msgEl) return;

    const contentDiv = msgEl.querySelector('.message-content');
    const oldContent = contentDiv.textContent.replace('(ویرایش شده)', '').trim();

    contentDiv.innerHTML = `
        <input type="text" class="edit-input" value="${escapeHtml(oldContent)}" 
               onkeypress="if(event.key==='Enter') saveEdit(${messageId})"
               onkeydown="if(event.key==='Escape') cancelEdit(${messageId}, '${escapeHtml(oldContent).replace(/'/g, "\\'")}')">
        <div style="display:flex; gap:4px; margin-top:4px;">
            <button onclick="saveEdit(${messageId})" style="font-size:11px; padding:2px 8px; width:auto; margin:0;">✅</button>
            <button onclick="cancelEdit(${messageId}, '${escapeHtml(oldContent).replace(/'/g, "\\'")}')" style="font-size:11px; padding:2px 8px; width:auto; margin:0; background:#999;">✖</button>
        </div>
    `;

    const input = contentDiv.querySelector('.edit-input');
    input.focus();
    input.select();
}

async function saveEdit(messageId) {
    const msgEl = document.querySelector(`[data-message-id="${messageId}"]`);
    const input = msgEl.querySelector('.edit-input');
    const newContent = input.value.trim();

    if (!newContent) return;

    try {
        const response = await fetch(`${API_BASE}/api/messages/${messageId}`, {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${token}`
            },
            body: JSON.stringify({ content: newContent })
        });

        if (!response.ok) {
            const error = await response.json();
            showNotification('❌ ' + (error.detail || 'خطا'), 'error');
        }
    } catch (error) {
        console.error('Error:', error);
    }
}

function cancelEdit(messageId, oldContent) {
    const msgEl = document.querySelector(`[data-message-id="${messageId}"]`);
    const contentDiv = msgEl.querySelector('.message-content');
    contentDiv.innerHTML = escapeHtml(oldContent);
}

// ============ حذف ============
async function deleteMessage(messageId) {
    if (!confirm('حذف این پیام؟')) return;

    try {
        const response = await fetch(`${API_BASE}/api/messages/${messageId}`, {
            method: 'DELETE',
            headers: { 'Authorization': `Bearer ${token}` }
        });

        if (!response.ok) {
            const error = await response.json();
            showNotification('❌ ' + (error.detail || 'خطا'), 'error');
        }
    } catch (error) {
        console.error('Error:', error);
    }
}

function updateMessageInUI(message) {
    const oldEl = document.querySelector(`[data-message-id="${message.id}"]`);
    if (oldEl) {
        oldEl.remove();
        renderedMessageIds.delete(message.id);
    }
    const isSent = message.sender_id === currentUser;
    displayMessage(message, isSent, true);
}

function removeMessageFromUI(messageId) {
    const msgEl = document.querySelector(`[data-message-id="${messageId}"]`);
    if (msgEl) {
        msgEl.remove();
        renderedMessageIds.delete(messageId);
    }
}

// ============ ارسال پیام ============
async function sendMessage() {
    const input = document.getElementById('messageInput');
    const content = input.value.trim();

    if (!content) return;
    if (!currentChatUser && !currentChatGroup) {
        showNotification('❌ کاربر یا گروهی انتخاب نشده', 'error');
        return;
    }

    input.value = '';

    const payload = {
        content: content,
        message_type: 'text'
    };

    if (currentChatUser) payload.receiver_id = currentChatUser;
    if (currentChatGroup) payload.group_id = currentChatGroup;
    if (replyToMessage) payload.reply_to_id = replyToMessage.id;

    try {
        const response = await fetch(`${API_BASE}/api/messages`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${token}`
            },
            body: JSON.stringify(payload)
        });

        if (response.ok) {
            cancelReply();
            scrollToBottom();
        } else {
            const error = await response.json();
            showNotification('❌ ' + (error.detail || 'خطا'), 'error');
        }
    } catch (error) {
        console.error('Error:', error);
        showNotification('❌ خطا در ارتباط', 'error');
    }
}

// ============ آپلود فایل ============
async function uploadFile(event) {
    const file = event.target.files[0];
    if (!file) return;
    if (!currentChatUser && !currentChatGroup) {
        showNotification('❌ کاربر یا گروهی انتخاب نشده', 'error');
        return;
    }

    const formData = new FormData();
    formData.append('file', file);

    try {
        showNotification('⏳ در حال آپلود...', 'info');

        const uploadResponse = await fetch(`${API_BASE}/api/upload`, {
            method: 'POST',
            headers: { 'Authorization': `Bearer ${token}` },
            body: formData
        });

        if (!uploadResponse.ok) throw new Error('Upload failed');

        const uploadData = await uploadResponse.json();
        const isImage = file.type.startsWith('image/');

        const payload = {
            content: file.name,
            message_type: isImage ? 'image' : 'file',
            file_url: uploadData.url
        };
        if (currentChatUser) payload.receiver_id = currentChatUser;
        if (currentChatGroup) payload.group_id = currentChatGroup;

        const msgResponse = await fetch(`${API_BASE}/api/messages`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${token}`
            },
            body: JSON.stringify(payload)
        });

        if (msgResponse.ok) {
            showNotification('✅ ارسال شد', 'success');
            scrollToBottom();
        }
    } catch (error) {
        console.error('Error:', error);
        showNotification('❌ خطا در آپلود', 'error');
    }

    event.target.value = '';
}

// ============ Modal ساخت گروه ============
function openCreateGroupModal() {
    document.getElementById('createGroupModal').style.display = 'flex';
    document.getElementById('groupName').value = '';

    const list = document.getElementById('groupMembersList');
    if (contactList.length === 0) {
        list.innerHTML = '<div style="text-align:center;color:#999;padding:10px;">هنوز مخاطبی ندارید</div>';
        return;
    }

    list.innerHTML = '';
    contactList.forEach(user => {
        const div = document.createElement('div');
        div.className = 'member-item';
        div.innerHTML = `
            <input type="checkbox" id="member-${user.id}" value="${user.id}">
            <label for="member-${user.id}">${escapeHtml(user.username)}</label>
        `;
        list.appendChild(div);
    });
}

function closeCreateGroupModal() {
    document.getElementById('createGroupModal').style.display = 'none';
}

async function createGroup() {
    const name = document.getElementById('groupName').value.trim();

    if (!name) {
        showNotification('❌ اسم گروه را وارد کنید', 'error');
        return;
    }

    const checkboxes = document.querySelectorAll('#groupMembersList input[type="checkbox"]:checked');
    const memberIds = Array.from(checkboxes).map(cb => parseInt(cb.value));

    if (memberIds.length === 0) {
        showNotification('❌ حداقل یک عضو انتخاب کنید', 'error');
        return;
    }

    try {
        const response = await fetch(`${API_BASE}/api/groups`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${token}`
            },
            body: JSON.stringify({ name, member_ids: memberIds })
        });

        if (response.ok) {
            showNotification('✅ گروه ساخته شد', 'success');
            closeCreateGroupModal();
            loadGroups();
            switchTab('groups', document.querySelectorAll('.tab')[1]);
        } else {
            const error = await response.json();
            showNotification('❌ ' + (error.detail || 'خطا'), 'error');
        }
    } catch (error) {
        console.error('Error:', error);
        showNotification('❌ خطا در ارتباط', 'error');
    }
}

// ============ ترک گروه ============
async function leaveGroup(groupId) {
    if (!confirm('از گروه خارج می‌شوی؟ پیام‌هایت از گروه پاک می‌شوند.')) return;

    try {
        const response = await fetch(`${API_BASE}/api/groups/${groupId}/leave`, {
            method: 'POST',
            headers: { 'Authorization': `Bearer ${token}` }
        });

        if (response.ok) {
            showNotification('✅ از گروه خارج شدی', 'success');
            if (currentChatGroup === groupId) {
                currentChatGroup = null;
                document.getElementById('messages').innerHTML = '';
            }
            loadGroups();
        }
    } catch (error) {
        console.error('Error:', error);
    }
}

// ============ تم تاریک ============
function toggleDarkMode() {
    document.body.classList.toggle('dark-mode');
    const isDark = document.body.classList.contains('dark-mode');
    localStorage.setItem('darkMode', isDark ? 'on' : 'off');
    console.log('🌙 Dark mode:', isDark ? 'ON' : 'OFF');
}

if (localStorage.getItem('darkMode') === 'on') {
    document.body.classList.add('dark-mode');
}

// ============ خروج ============
async function logout() {
    try {
        await fetch(`${API_BASE}/api/logout`, {
            method: 'POST',
            headers: { 'Authorization': `Bearer ${token}` }
        });
    } catch (error) {
        console.error('خطا:', error);
    }

    if (ws) ws.close();

    currentUser = null;
    currentChatUser = null;
    currentChatGroup = null;
    token = '';
    userList = [];
    contactList = [];
    groupList = [];
    renderedMessageIds.clear();
    userOnlineNotified.clear();
    cancelReply();

    document.getElementById('messages').innerHTML = '';
    document.getElementById('usersList').innerHTML = '';
    document.getElementById('messageInput').value = '';
    document.getElementById('onlineCount').textContent = '0';
    document.getElementById('statusDot').classList.remove('connected');
    document.getElementById('statusText').textContent = 'قطع شده';

    showLogin();
}

console.log('✅ script.js v20 بارگذاری شد!');