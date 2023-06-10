from vocode.streaming.action.base_action import BaseAction, Scheduler, GetAvailability
from vocode.streaming.action.nylas_send_email import NylasSendEmail
from vocode.streaming.models.actions import ActionType


class ActionFactory:
    def create_action(self, action_type):
        if action_type == ActionType.NYLAS_SEND_EMAIL:
            return NylasSendEmail()
        elif action_type == ActionType.CHECK_AVAILABILITY:
            return GetAvailability()
        elif action_type == ActionType.BOOK_APPOINTMENT:
            return Scheduler()
        else:
            raise Exception("Invalid action type")