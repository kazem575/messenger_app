from fastapi import (
    FastAPI, Depends, HTTPException, status, WebSocket,
    WebSocketDisconnect, UploadFile, File, Request
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy.orm import Session
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
import os
from datetime import datetime, timedelta, timezone
import json
import traceback
import shutil
import uuid

from database import (
    SessionLocal, User, Message, Contact, ContactRequest, 
    ContactRequestAttempt, Group, GroupMember
)
from models import (
    UserCreate, UserLogin, UserResponse,
    MessageCreate, MessageResponse, MessageUpdate,
    ContactRequestCreate, ContactResponse,
    GroupCreate, GroupResponse
)
from auth import (
    get_db, authenticate_user, create_access_token, get_current_user,
    get_password_hash, ACCESS_TOKEN_EXPIRE_MINUTES, decode_token
)
from websocket_manager import manager

# ============ Rate Limiter ============
limiter = Limiter(key_func=get_remote_address)

app = FastAPI(title="پیام‌رسان تحت وب", version="4.0.0")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# ============ CORS ============
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:8000",
        "http://127.0.0.1:8000",
        "https://message-box.ir",
        "https://www.message-box.ir",
        "https://desktop-1ebo8os.taile7482d.ts.net",
        "http://desktop-1ebo8os.taile7482d.ts.net",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============ مسیرها ============
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
frontend_path = os.path.join(BASE_DIR, "frontend")
uploads_path = os.path.join(BASE_DIR, "backend", "uploads")
os.makedirs(uploads_path, exist_ok=True)

print(f"📁 frontend: {frontend_path}")
print(f"📁 uploads: {uploads_path}")

if os.path.exists(frontend_path):
    app.mount("/static", StaticFiles(directory=frontend_path), name="static")
    print("✅ frontend found")

@app.get("/api/files/{filename}")
async def get_file(filename: str, token: str = None, db: Session = Depends(get_db)):
    try:
        if not token:
            raise HTTPException(status_code=401, detail="توکن لازم است")
        
        payload = decode_token(token)
        if not payload:
            raise HTTPException(status_code=401, detail="توکن نامعتبر")
        
        username = payload.get("sub")
        user = db.query(User).filter(User.username == username).first()
        if not user:
            raise HTTPException(status_code=401, detail="کاربر پیدا نشد")
        
        filepath = os.path.join(uploads_path, filename)
        if not os.path.exists(filepath):
            raise HTTPException(status_code=404, detail="فایل پیدا نشد")
        
        return FileResponse(filepath)
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ get_file error: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="خطای داخلی سرور")
# ============ توابع کمکی ============
def user_to_dict(user: User) -> dict:
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "is_online": manager.is_online(user.id),
        "last_seen": user.last_seen.isoformat() if user.last_seen else None,
        "created_at": user.created_at.isoformat() if user.created_at else None,
    }


def message_to_dict(msg: Message, db: Session = None) -> dict:
    result = {
        "id": msg.id,
        "sender_id": msg.sender_id,
        "receiver_id": msg.receiver_id,
        "group_id": msg.group_id,
        "content": msg.content,
        "message_type": msg.message_type,
        "file_url": msg.file_url,
        "reply_to_id": msg.reply_to_id,
        "timestamp": msg.timestamp.isoformat() if msg.timestamp else None,
        "is_read": msg.is_read,
        "is_edited": msg.is_edited,
        "is_deleted": msg.is_deleted,
    }

    if db:
        sender = db.query(User).filter(User.id == msg.sender_id).first()
        if sender:
            result["sender_username"] = sender.username

        if msg.reply_to_id:
            reply_msg = db.query(Message).filter(Message.id == msg.reply_to_id).first()
            if reply_msg:
                reply_sender = db.query(User).filter(User.id == reply_msg.sender_id).first()
                result["reply_to"] = {
                    "id": reply_msg.id,
                    "content": reply_msg.content[:100],
                    "sender_username": reply_sender.username if reply_sender else "Unknown",
                }

    return result


async def send_ws(user_id: int, data: dict):
    try:
        await manager.send_personal_message(json.dumps(data, ensure_ascii=False), user_id)
    except Exception as e:
        print(f"❌ WS error to {user_id}: {e}")


# ============ صفحه اصلی ============
@app.get("/")
def root():
    return {"message": "پیام‌رسان v4.0", "docs": "/docs"}


@app.get("/static")
@app.get("/static/")
async def serve_index():
    index_path = os.path.join(frontend_path, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    raise HTTPException(status_code=404, detail="index.html not found")


# ============ ثبت‌نام ============
@app.post("/api/register")
@limiter.limit("10/hour")
def register(request: Request, user: UserCreate, db: Session = Depends(get_db)):
    try:
        existing = db.query(User).filter(
            (User.username == user.username) | (User.email == user.email)
        ).first()
        if existing:
            raise HTTPException(status_code=400, detail="نام کاربری یا ایمیل قبلاً ثبت شده")

        db_user = User(
            username=user.username,
            email=user.email,
            password_hash=get_password_hash(user.password),
        )
        db.add(db_user)
        db.commit()
        db.refresh(db_user)
        return user_to_dict(db_user)
    except HTTPException:
        raise
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


# ============ ورود ============
@app.post("/api/login")
@limiter.limit("20/minute")
def login(request: Request, user: UserLogin, db: Session = Depends(get_db)):
    try:
        db_user = authenticate_user(db, user.username, user.password)
        if not db_user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="نام کاربری یا رمز عبور اشتباه است"
            )

        db_user.is_online = True
        db_user.last_seen = datetime.now(timezone.utc)
        db.commit()

        token = create_access_token(
            data={"sub": user.username},
            expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        )
        return {
            "access_token": token,
            "token_type": "bearer",
            "user_id": db_user.id,
            "username": db_user.username,
        }
    except HTTPException:
        raise
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


# ============ خروج ============
@app.post("/api/logout")
def logout(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    current_user.is_online = False
    current_user.last_seen = datetime.now(timezone.utc)
    db.commit()
    return {"message": "خارج شدید"}


# ============ لیست کاربران ============
@app.get("/api/users")
def get_users(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    contacts = db.query(Contact).filter(Contact.user_id == current_user.id).all()
    contact_ids = [c.contact_id for c in contacts]
    if not contact_ids:
        return []
    users = db.query(User).filter(User.id.in_(contact_ids)).all()
    return [user_to_dict(u) for u in users]

# ============ لیست همه کاربران (برای تب «همه کاربران») ============
@app.get("/api/users/all")
def get_all_users(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """همه کاربران به‌جز خودم"""
    users = db.query(User).filter(User.id != current_user.id).all()
    return [user_to_dict(u) for u in users]


# ============ چک کن کاربر قبلاً چند بار جواب داده ============
@app.get("/api/contact-attempts/{target_user_id}")
def get_contact_attempts(
    target_user_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """چند بار کاربر به درخواست این کاربر جواب داده"""
    attempts = db.query(ContactRequestAttempt).filter(
        ContactRequestAttempt.user_id == current_user.id,
        ContactRequestAttempt.target_user_id == target_user_id
    ).order_by(ContactRequestAttempt.attempted_at.desc()).limit(3).all()
    
    return {
        "count": len(attempts),
        "attempts": [
            {
                "answer": a.answer,
                "attempted_at": a.attempted_at.isoformat()
            }
            for a in attempts
        ],
        "can_ask": len(attempts) < 3
    }


# ============ ثبت جواب کاربر (آره/نه) ============
@app.post("/api/contact-attempts/{target_user_id}")
def record_contact_attempt(
    target_user_id: int,
    answer: str,  # "accepted" یا "rejected"
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """ثبت جواب کاربر به درخواست مخاطب"""
    if answer not in ["accepted", "rejected"]:
        raise HTTPException(status_code=400, detail="جواب نامعتبر")
    
    # چک کن قبلاً ۳ بار جواب نداده
    existing_count = db.query(ContactRequestAttempt).filter(
        ContactRequestAttempt.user_id == current_user.id,
        ContactRequestAttempt.target_user_id == target_user_id
    ).count()
    
    if existing_count >= 3:
        raise HTTPException(status_code=400, detail="سقف جواب‌ها پر شده")
    
    # ثبت
    attempt = ContactRequestAttempt(
        user_id=current_user.id,
        target_user_id=target_user_id,
        answer=answer
    )
    db.add(attempt)
    db.commit()
    
    return {
        "message": "ثبت شد",
        "count": existing_count + 1,
        "can_ask": (existing_count + 1) < 3
    }
# ============ درخواست‌های در انتظار ============
@app.get("/api/contacts/pending")
def get_pending(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    requests = db.query(ContactRequest).filter(
        ContactRequest.to_user_id == current_user.id,
        ContactRequest.status == "pending"
    ).all()

    result = []
    for r in requests:
        user = db.query(User).filter(User.id == r.from_user_id).first()
        if user:
            result.append({
                "request_id": r.id,
                "user": user_to_dict(user),
                "created_at": r.created_at.isoformat()
            })
    return result


# ============ درخواست‌های فرستاده‌شده ============
@app.get("/api/contacts/sent")
def get_sent(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    requests = db.query(ContactRequest).filter(
        ContactRequest.from_user_id == current_user.id,
        ContactRequest.status == "pending"
    ).all()

    result = []
    for r in requests:
        user = db.query(User).filter(User.id == r.to_user_id).first()
        if user:
            result.append({
                "request_id": r.id,
                "user": user_to_dict(user),
                "created_at": r.created_at.isoformat()
            })
    return result


# ============ لیست مخاطبان ============
@app.get("/api/contacts")
def get_contacts(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    contacts = db.query(Contact).filter(Contact.user_id == current_user.id).all()
    result = []
    for c in contacts:
        user = db.query(User).filter(User.id == c.contact_id).first()
        if user:
            result.append(user_to_dict(user))
    return result


# ============ درخواست مخاطب ============
@app.post("/api/contacts/request/{user_id}")
async def request_contact(
    user_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="نمی‌تونی به خودت درخواست بدی")

    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="کاربر پیدا نشد")

    existing = db.query(ContactRequest).filter(
        ContactRequest.from_user_id == current_user.id,
        ContactRequest.to_user_id == user_id,
        ContactRequest.status == "pending"
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="قبلاً درخواست دادی")

    already = db.query(Contact).filter(
        Contact.user_id == current_user.id,
        Contact.contact_id == user_id
    ).first()
    if already:
        raise HTTPException(status_code=400, detail="قبلاً مخاطب هستید")

    req = ContactRequest(from_user_id=current_user.id, to_user_id=user_id)
    db.add(req)
    db.commit()

    await send_ws(user_id, {
        "type": "contact_request",
        "from": user_to_dict(current_user),
    })

    return {"message": "درخواست ارسال شد"}


# ============ قبول درخواست ============
@app.post("/api/contacts/accept/{request_id}")
async def accept_contact(
    request_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    req = db.query(ContactRequest).filter(
        ContactRequest.id == request_id,
        ContactRequest.to_user_id == current_user.id,
        ContactRequest.status == "pending"
    ).first()

    if not req:
        raise HTTPException(status_code=404, detail="درخواست پیدا نشد")

    req.status = "accepted"

    db.add(Contact(user_id=current_user.id, contact_id=req.from_user_id))
    db.add(Contact(user_id=req.from_user_id, contact_id=current_user.id))
    db.commit()

    await send_ws(req.from_user_id, {
        "type": "contact_accepted",
        "by": user_to_dict(current_user),
    })
    await send_ws(current_user.id, {
        "type": "contact_accepted",
        "by": user_to_dict(current_user),
    })

    return {"message": "قبول شد"}


# ============ رد درخواست ============
@app.post("/api/contacts/reject/{request_id}")
def reject_contact(
    request_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    req = db.query(ContactRequest).filter(
        ContactRequest.id == request_id,
        ContactRequest.to_user_id == current_user.id,
        ContactRequest.status == "pending"
    ).first()

    if not req:
        raise HTTPException(status_code=404, detail="درخواست پیدا نشد")

    req.status = "rejected"
    db.commit()
    return {"message": "رد شد"}


# ============ حذف مخاطب ============
@app.delete("/api/contacts/{user_id}")
def delete_contact(
    user_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    db.query(Contact).filter(
        Contact.user_id == current_user.id,
        Contact.contact_id == user_id
    ).delete()
    db.query(Contact).filter(
        Contact.user_id == user_id,
        Contact.contact_id == current_user.id
    ).delete()
    db.commit()
    return {"message": "حذف شد"}


# ============ ارسال پیام ============
@app.post("/api/messages")
@limiter.limit("60/minute")
async def send_message(
    request: Request,
    message: MessageCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    try:
        if not message.receiver_id and not message.group_id:
            raise HTTPException(status_code=400, detail="گیرنده یا گروه لازم است")

        if message.receiver_id:
            receiver = db.query(User).filter(User.id == message.receiver_id).first()
            if not receiver:
                raise HTTPException(status_code=404, detail="گیرنده پیدا نشد")

        if message.group_id:
            group = db.query(Group).filter(Group.id == message.group_id).first()
            if not group:
                raise HTTPException(status_code=404, detail="گروه پیدا نشد")
            is_member = db.query(GroupMember).filter(
                GroupMember.group_id == message.group_id,
                GroupMember.user_id == current_user.id
            ).first()
            if not is_member:
                raise HTTPException(status_code=403, detail="عضو گروه نیستی")

        if message.reply_to_id:
            reply_msg = db.query(Message).filter(Message.id == message.reply_to_id).first()
            if not reply_msg:
                raise HTTPException(status_code=404, detail="پیام پاسخ پیدا نشد")

        db_message = Message(
            sender_id=current_user.id,
            receiver_id=message.receiver_id,
            group_id=message.group_id,
            content=message.content,
            message_type=message.message_type,
            file_url=message.file_url,
            reply_to_id=message.reply_to_id,
        )
        db.add(db_message)
        db.commit()
        db.refresh(db_message)

        result = message_to_dict(db_message, db)
        data = {"type": "new_message", "message": result}

        if message.receiver_id:
            await send_ws(message.receiver_id, data)
            await send_ws(current_user.id, data)

        if message.group_id:
            members = db.query(GroupMember).filter(
                GroupMember.group_id == message.group_id
            ).all()
            for m in members:
                await send_ws(m.user_id, data)

        return result
    except HTTPException:
        raise
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


# ============ دریافت پیام‌های خصوصی ============
@app.get("/api/messages/{user_id}")
def get_messages(
    user_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    messages = db.query(Message).filter(
        Message.group_id == None,
        (
            ((Message.sender_id == current_user.id) & (Message.receiver_id == user_id)) |
            ((Message.sender_id == user_id) & (Message.receiver_id == current_user.id))
        )
    ).order_by(Message.timestamp).all()

    changed = False
    for msg in messages:
        if msg.receiver_id == current_user.id and not msg.is_read:
            msg.is_read = True
            changed = True
    if changed:
        db.commit()

    return [message_to_dict(m, db) for m in messages]


# ============ ویرایش پیام ============
@app.put("/api/messages/{message_id}")
async def update_message(
    message_id: int,
    update: MessageUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    msg = db.query(Message).filter(Message.id == message_id).first()
    if not msg:
        raise HTTPException(status_code=404, detail="پیام پیدا نشد")
    if msg.sender_id != current_user.id:
        raise HTTPException(status_code=403, detail="اجازه نداری")
    if msg.is_deleted:
        raise HTTPException(status_code=400, detail="پیام حذف‌شده")

    msg.content = update.content
    msg.is_edited = True
    db.commit()
    db.refresh(msg)

    result = message_to_dict(msg, db)
    data = {"type": "message_edited", "message": result}

    if msg.receiver_id:
        await send_ws(msg.receiver_id, data)
    if msg.group_id:
        members = db.query(GroupMember).filter(
            GroupMember.group_id == msg.group_id
        ).all()
        for m in members:
            await send_ws(m.user_id, data)
    await send_ws(current_user.id, data)

    return result


# ============ حذف پیام ============
@app.delete("/api/messages/{message_id}")
async def delete_message(
    message_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    msg = db.query(Message).filter(Message.id == message_id).first()
    if not msg:
        raise HTTPException(status_code=404, detail="پیام پیدا نشد")
    if msg.sender_id != current_user.id:
        raise HTTPException(status_code=403, detail="اجازه نداری")

    msg.is_deleted = True
    msg.content = ""
    db.commit()
    db.refresh(msg)

    result = message_to_dict(msg, db)
    data = {"type": "message_deleted", "message": result}

    if msg.receiver_id:
        await send_ws(msg.receiver_id, data)
    if msg.group_id:
        members = db.query(GroupMember).filter(
            GroupMember.group_id == msg.group_id
        ).all()
        for m in members:
            await send_ws(m.user_id, data)
    await send_ws(current_user.id, data)

    return result


# ============ آپلود فایل ============
@app.post("/api/upload")
@limiter.limit("20/hour")
async def upload_file(
    request: Request,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
):
    try:
        # محدودیت حجم فایل (۱۰ مگابایت)
        MAX_SIZE = 10 * 1024 * 1024
        file.file.seek(0, 2)
        size = file.file.tell()
        file.file.seek(0)
        if size > MAX_SIZE:
            raise HTTPException(status_code=413, detail="فایل بزرگ‌تر از ۱۰ مگابایت")

        ext = os.path.splitext(file.filename)[1]
        filename = f"{uuid.uuid4()}{ext}"
        filepath = os.path.join(uploads_path, filename)

        with open(filepath, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        return {
            "url": f"/uploads/{filename}",
            "filename": file.filename,
            "size": os.path.getsize(filepath),
        }
    except HTTPException:
        raise
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


# ============ گروه‌ها ============
@app.post("/api/groups")
async def create_group(
    group: GroupCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    contacts = db.query(Contact).filter(Contact.user_id == current_user.id).all()
    contact_ids = [c.contact_id for c in contacts]

    for mid in group.member_ids:
        if mid not in contact_ids and mid != current_user.id:
            raise HTTPException(
                status_code=400,
                detail=f"کاربر {mid} جزو مخاطبان شما نیست"
            )

    db_group = Group(name=group.name, creator_id=current_user.id)
    db.add(db_group)
    db.commit()
    db.refresh(db_group)

    db.add(GroupMember(group_id=db_group.id, user_id=current_user.id))
    for mid in group.member_ids:
        db.add(GroupMember(group_id=db_group.id, user_id=mid))
    db.commit()

    # اطلاع به همه اعضا
    all_members = [current_user.id] + group.member_ids
    for member_id in all_members:
        await send_ws(member_id, {
            "type": "new_group",
            "group": {
                "id": db_group.id,
                "name": db_group.name,
                "creator_id": db_group.creator_id,
            }
        })

    return {"id": db_group.id, "name": db_group.name}


@app.get("/api/groups")
def get_groups(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    members = db.query(GroupMember).filter(GroupMember.user_id == current_user.id).all()
    result = []
    for m in members:
        g = db.query(Group).filter(Group.id == m.group_id).first()
        if g:
            group_members = db.query(GroupMember).filter(
                GroupMember.group_id == g.id
            ).all()
            members_list = []
            for gm in group_members:
                u = db.query(User).filter(User.id == gm.user_id).first()
                if u:
                    members_list.append({
                        "id": u.id,
                        "username": u.username,
                        "is_online": manager.is_online(u.id),
                    })

            result.append({
                "id": g.id,
                "name": g.name,
                "creator_id": g.creator_id,
                "created_at": g.created_at.isoformat(),
                "members": members_list,
            })
    return result


@app.get("/api/groups/{group_id}")
def get_group(
    group_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    g = db.query(Group).filter(Group.id == group_id).first()
    if not g:
        raise HTTPException(status_code=404, detail="گروه پیدا نشد")

    is_member = db.query(GroupMember).filter(
        GroupMember.group_id == group_id,
        GroupMember.user_id == current_user.id
    ).first()
    if not is_member:
        raise HTTPException(status_code=403, detail="عضو گروه نیستی")

    group_members = db.query(GroupMember).filter(
        GroupMember.group_id == g.id
    ).all()
    members_list = []
    for gm in group_members:
        u = db.query(User).filter(User.id == gm.user_id).first()
        if u:
            members_list.append({
                "id": u.id,
                "username": u.username,
                "is_online": manager.is_online(u.id),
            })

    return {
        "id": g.id,
        "name": g.name,
        "creator_id": g.creator_id,
        "created_at": g.created_at.isoformat(),
        "members": members_list,
    }


@app.get("/api/groups/{group_id}/messages")
def get_group_messages(
    group_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    is_member = db.query(GroupMember).filter(
        GroupMember.group_id == group_id,
        GroupMember.user_id == current_user.id
    ).first()
    if not is_member:
        raise HTTPException(status_code=403, detail="عضو گروه نیستی")

    messages = db.query(Message).filter(
        Message.group_id == group_id
    ).order_by(Message.timestamp).all()

    return [message_to_dict(m, db) for m in messages]


@app.post("/api/groups/{group_id}/leave")
async def leave_group(
    group_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    is_member = db.query(GroupMember).filter(
        GroupMember.group_id == group_id,
        GroupMember.user_id == current_user.id
    ).first()
    if not is_member:
        raise HTTPException(status_code=403, detail="عضو گروه نیستی")

    db.query(Message).filter(
        Message.group_id == group_id,
        Message.sender_id == current_user.id
    ).delete()

    db.query(GroupMember).filter(
        GroupMember.group_id == group_id,
        GroupMember.user_id == current_user.id
    ).delete()
    db.commit()

    remaining = db.query(GroupMember).filter(
        GroupMember.group_id == group_id
    ).count()
    if remaining == 0:
        db.query(Group).filter(Group.id == group_id).delete()
        db.commit()

    members = db.query(GroupMember).filter(
        GroupMember.group_id == group_id
    ).all()
    for m in members:
        await send_ws(m.user_id, {
            "type": "group_member_left",
            "group_id": group_id,
            "user": user_to_dict(current_user),
        })

    return {"message": "از گروه خارج شدی"}


# ============ WebSocket ============
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, token: str = None):
    print(f"🔌 WebSocket request, token: {token[:30] if token else 'NONE'}...")

    if not token:
        print("❌ No token provided")
        await websocket.close(code=1008, reason="Token required")
        return

    payload = decode_token(token)
    if not payload:
        print("❌ Invalid token")
        await websocket.close(code=1008, reason="Invalid token")
        return

    username = payload.get("sub")
    if not username:
        print("❌ No username in payload")
        await websocket.close(code=1008, reason="Invalid payload")
        return

    db_check = SessionLocal()
    try:
        user = db_check.query(User).filter(User.username == username).first()
        if not user:
            print(f"❌ User {username} not found")
            await websocket.close(code=1008, reason="User not found")
            return
        user_id = user.id
    finally:
        db_check.close()

    await manager.connect(websocket, user_id)
    print(f"🔌 User {user_id} ({username}) connected via WS")

    db = SessionLocal()
    try:
        u = db.query(User).filter(User.id == user_id).first()
        if u:
            u.is_online = True
            u.last_seen = datetime.now(timezone.utc)
            db.commit()

        online_users = manager.get_online_users()
        for other_id in online_users:
            if other_id == user_id:
                continue

            is_contact = db.query(Contact).filter(
                Contact.user_id == other_id,
                Contact.contact_id == user_id
            ).first()

            has_request = db.query(ContactRequest).filter(
                ContactRequest.from_user_id == other_id,
                ContactRequest.to_user_id == user_id,
                ContactRequest.status == "pending"
            ).first()

            await manager.send_personal_message(
                json.dumps({
                    "type": "user_online",
                    "user_id": user_id,
                    "username": username,
                    "ask_contact": not is_contact and not has_request,
                }, ensure_ascii=False),
                other_id
            )

        while True:
            data = await websocket.receive_text()
            try:
                msg_data = json.loads(data)
                msg_type = msg_data.get("type")

                if msg_type == "typing":
                    receiver_id = msg_data.get("receiver_id")
                    group_id = msg_data.get("group_id")

                    if receiver_id:
                        await manager.send_personal_message(
                            json.dumps({
                                "type": "typing",
                                "sender_id": user_id,
                                "is_typing": True,
                            }, ensure_ascii=False),
                            receiver_id
                        )
                    elif group_id:
                        members = db.query(GroupMember).filter(
                            GroupMember.group_id == group_id,
                            GroupMember.user_id != user_id
                        ).all()
                        for m in members:
                            await manager.send_personal_message(
                                json.dumps({
                                    "type": "typing",
                                    "sender_id": user_id,
                                    "group_id": group_id,
                                    "is_typing": True,
                                }, ensure_ascii=False),
                                m.user_id
                            )
                elif msg_type == "stop_typing":
                    receiver_id = msg_data.get("receiver_id")
                    group_id = msg_data.get("group_id")

                    if receiver_id:
                        await manager.send_personal_message(
                            json.dumps({
                                "type": "typing",
                                "sender_id": user_id,
                                "is_typing": False,
                            }, ensure_ascii=False),
                            receiver_id
                        )
                    elif group_id:
                        members = db.query(GroupMember).filter(
                            GroupMember.group_id == group_id,
                            GroupMember.user_id != user_id
                        ).all()
                        for m in members:
                            await manager.send_personal_message(
                                json.dumps({
                                    "type": "typing",
                                    "sender_id": user_id,
                                    "group_id": group_id,
                                    "is_typing": False,
                                }, ensure_ascii=False),
                                m.user_id
                            )
            except json.JSONDecodeError:
                pass

    except WebSocketDisconnect:
        manager.disconnect(user_id)
        print(f"🔌 User {user_id} disconnected")

        db2 = SessionLocal()
        try:
            u = db2.query(User).filter(User.id == user_id).first()
            if u:
                u.is_online = False
                u.last_seen = datetime.now(timezone.utc)
                db2.commit()

            await manager.broadcast(json.dumps({
                "type": "user_offline",
                "user_id": user_id,
                "username": username,
            }, ensure_ascii=False))
        finally:
            db2.close()
    except Exception as e:
        print(f"❌ WS error: {e}")
        traceback.print_exc()
        manager.disconnect(user_id)
    finally:
        db.close()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)