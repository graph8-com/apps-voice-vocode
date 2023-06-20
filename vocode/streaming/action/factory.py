from vocode.streaming.action.base_action import BaseAction, Scheduler, GetAvailability, GetServices, GetBookings, UpdateBooking, CancelBooking
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
        elif action_type == ActionType.GET_SERVICES:
            return GetServices()
        elif action_type == ActionType.GET_BOOKINGS:
            return GetBookings()
        elif action_type == ActionType.UPDATE_BOOKING:
            return UpdateBooking()
        elif action_type == ActionType.CANCEL_BOOKING:
            return CancelBooking()
        else:
            raise Exception("Invalid action type")