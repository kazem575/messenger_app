from pydantic import BaseModel, EmailStr, Field, ConfigDict
from datetime import datetime
from typing import Optional, List


class UserCreate(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    email: EmailStr
    password: str = Field(..., min_length=4, max_length=72)


class UserLogin(BaseModel):
    username: str
    password: str


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    email: str
    is_online: bool
    last_seen: Optional[datetime] = None
    created_at: datetime


class MessageCreate(BaseModel):
    receiver_id: Optional[int] = None
    group_id: Optional[int] = None
    content: str = Field(..., min_length=1, max_length=5000)
    message_type: str = "text"
    file_url: Optional[str] = None
    reply_to_id: Optional[int] = None


class MessageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    sender_id: int
    receiver_id: Optional[int] = None
    group_id: Optional[int] = None
    content: str
    message_type: str = "text"
    file_url: Optional[str] = None
    reply_to_id: Optional[int] = None
    timestamp: datetime
    is_read: bool
    is_edited: bool = False
    is_deleted: bool = False


class MessageUpdate(BaseModel):
    content: str = Field(..., min_length=1, max_length=5000)


class ContactRequestCreate(BaseModel):
    to_user_id: int


class ContactResponse(BaseModel):
    id: int
    username: str
    is_online: bool
    last_seen: Optional[datetime] = None


class GroupCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    member_ids: List[int] = []


class GroupResponse(BaseModel):
    id: int
    name: str
    creator_id: int
    members: List[dict] = []
    created_at: datetime