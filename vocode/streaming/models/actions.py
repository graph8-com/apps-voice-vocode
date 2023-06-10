from enum import Enum
from vocode.streaming.models.model import BaseModel


class ActionType(str, Enum):
    BASE = "action_base"
    NYLAS_SEND_EMAIL = "action_nylas_send_email"
    CHECK_AVAILABILITY = "check_availability"
    BOOK_APPOINTMENT = "book_appointment"

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