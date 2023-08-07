from vocode.streaming.action.base_action import BaseAction
from vocode.streaming.action.nylas_send_email import NylasSendEmail
from vocode.streaming.models.actions import ActionType
from vocode.streaming.action.square_actions import GetServices, GetAvailability, Scheduler, GetBookings, CancelBooking, UpdateBooking
from vocode.streaming.action.chrono_actions import BookChrono, AvailabilityChrono, ServicesChrono


class ActionFactory:
    def create_action(self, action_type: str) -> BaseAction:
        if action_type == ActionType.NYLAS_SEND_EMAIL:
            return NylasSendEmail(should_respond=True)
        elif action_type == "get_availability":
            return GetAvailability()
        elif action_type == "book_appointment":
            return Scheduler()
        elif action_type == "get_services":
            return GetServices()
        elif action_type == "get_bookings":
            return GetBookings()
        elif action_type == "update_booking":
            return UpdateBooking()
        elif action_type == "cancel_booking":
            return CancelBooking()
        elif action_type == "book_chrono":
            return BookChrono()
        elif action_type == "availability":
            return AvailabilityChrono()
        elif action_type == "chrono_services":
            return ServicesChrono()
        else:
            raise Exception("Invalid action type")
