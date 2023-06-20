from enum import Enum
from vocode.streaming.models.model import BaseModel


class ActionType(str, Enum):
    BASE = "action_base"
    NYLAS_SEND_EMAIL = "action_nylas_send_email"
    CHECK_AVAILABILITY = "check_availability"
    BOOK_APPOINTMENT = "book_appointment"
    GET_SERVICES = "get_services"
    GET_BOOKINGS = "get_bookings"
    UPDATE_BOOKING = "update_booking"
    CANCEL_BOOKING = "cancel_booking"

class ActionInput(BaseModel):
    action_type: ActionType
    params: str
    conversation_id: str
    token: str

class ActionOutput(BaseModel):
    action_type: ActionType
    response: str

class NylasSendEmailActionOutput(ActionOutput):
    action_type: ActionType = ActionType.NYLAS_SEND_EMAIL

class AvailabilityOutput(ActionOutput):
    action_type: ActionType = ActionType.CHECK_AVAILABILITY

class SchedulerOutput(ActionOutput):
    action_type: ActionType = ActionType.BOOK_APPOINTMENT

class ServicesOutput(ActionOutput):
    action_type: ActionType = ActionType.GET_SERVICES

class BookingsOutput(ActionOutput):
    action_type: ActionType = ActionType.GET_BOOKINGS

class UpdateBookingOutput(ActionOutput):
    action_type: ActionType = ActionType.UPDATE_BOOKING

class CancelBookingOutput(ActionOutput):
    action_type: ActionType = ActionType.CANCEL_BOOKING