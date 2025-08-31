from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime
from enum import Enum

class OrderStatus(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    IN_PREPARATION = "in_preparation"
    READY = "ready"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"

# Modelo para activar/desactivar takeover humano
class TakeoverRequest(BaseModel):
    """Request model for activating/deactivating human takeover."""
    customer_phone: str
    activate: bool = True


# Modelo para enviar mensajes manualmente como negocio
class MessageRequest(BaseModel):
    """Request model for sending manual messages as a business."""
    to: str  # WhatsApp format destination number
    message: str

class MenuItem(BaseModel):
    id: str
    name: str
    description: str
    price: float
    category: str
    available: bool = True
    image_url: Optional[str] = None

class CustomerProfile(BaseModel):
    phone: str
    name: Optional[str] = None
    address: Optional[str] = None
    last_interaction: Optional[datetime] = None
    preferred_language: str = "es"
    
class OrderItem(BaseModel):
    menu_item_id: str
    quantity: int = Field(gt=0)
    special_instructions: Optional[str] = None
    
class Order(BaseModel):
    id: str
    customer_phone: str
    items: List[OrderItem]
    total_amount: float
    status: OrderStatus = OrderStatus.PENDING
    created_at: datetime
    updated_at: datetime
    delivery_address: Optional[str] = None
    special_instructions: Optional[str] = None

class ConversationMessage(BaseModel):
    """Model for individual messages in a conversation."""
    role: str  # 'user' or 'assistant'
    content: str
    timestamp: float

class ConversationData(BaseModel):
    """Model for conversation data stored in files."""
    phone_number: str
    name: str = ""
    last_updated: float
    history: List[ConversationMessage]

class ConversationContext(BaseModel):
    """Model for tracking conversation state and context."""
    customer_phone: str
    last_intent: Optional[str] = None
    current_order_id: Optional[str] = None
    last_message_timestamp: Optional[datetime] = None
    human_takeover: bool = False
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.timestamp() if v else None
        }
