import asyncio
from enum import Enum
from typing import Generic, Optional, TypeVar
from pydantic import BaseModel
from vocode.streaming.models.model import TypedModel


class ActionType(str, Enum):
    BASE = "action_base"
    NYLAS_SEND_EMAIL = "action_nylas_send_email"
    TRANSFER_CALL = "action_transfer_call"
    SQUARE_BOOK = "book_appointment"
    CHRONO_BOOK = "book_chrono"
    SQUARE_SERVICES = "get_services"
    CHRONO_SERVICES = "chrono_services"
    SQUARE_AVAIL = "get_availability"
    CHRONO_AVAIL = "availability"
    SQUARE_UPDATE = "update_booking"
    SQUARE_BOOKINGS = "get_bookings"
    SQUARE_CANCEL = "cancel_booking"

class ActionConfig(TypedModel, type=ActionType.BASE):
    pass


ParametersType = TypeVar("ParametersType", bound=BaseModel)


class ActionInput(BaseModel, Generic[ParametersType]):
    action_config: ActionConfig
    conversation_id: str
    params: ParametersType
    user_message_tracker: Optional[asyncio.Event] = None

    class Config:
        arbitrary_types_allowed = True



class FunctionFragment(BaseModel):
    name: str
    arguments: str


class FunctionCall(BaseModel):
    name: str
    arguments: str


class VonagePhoneCallActionInput(ActionInput[ParametersType]):
    vonage_uuid: str


class TwilioPhoneCallActionInput(ActionInput[ParametersType]):
    twilio_sid: str


ResponseType = TypeVar("ResponseType", bound=BaseModel)


class ActionOutput(BaseModel, Generic[ResponseType]):
    action_type: str
    response: ResponseType
