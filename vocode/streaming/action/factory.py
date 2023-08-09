from vocode.streaming.action.base_action import BaseAction
from vocode.streaming.action.nylas_send_email import (
    NylasSendEmail,
    NylasSendEmailActionConfig,
)
from vocode.streaming.models.actions import ActionConfig
from vocode.streaming.action.transfer_call import TransferCall, TransferCallActionConfig
from vocode.streaming.action.square_actions import *
from vocode.streaming.action.chrono_actions import *


class ActionFactory:
    def create_action(self, action_config: ActionConfig) -> BaseAction:
        if isinstance(action_config, NylasSendEmailActionConfig):
            return NylasSendEmail(action_config, should_respond=True)
        elif isinstance(action_config, TransferCallActionConfig):
            return TransferCall(action_config)
        elif isinstance(action_config, AvailabilityConfig):
            return GetAvailability(action_config)
        elif isinstance(action_config, ServicesConfig):
            return GetServices(action_config)
        elif isinstance(action_config, SchedulerConfig):
            return Scheduler(action_config)
        elif isinstance(action_config, BookingsConfig):
            return GetBookings(action_config)
        elif isinstance(action_config, CancelBookingConfig):
            return CancelBooking(action_config)
        elif isinstance(action_config, UpdateBookingConfig):
            return UpdateBooking(action_config)
        elif isinstance(action_config, BookChronoConfig):
            return BookChrono(action_config)
        elif isinstance(action_config, ServicesChronoConfig):
            return ServicesChrono(action_config)
        elif isinstance(action_config, AvailabilityChronoConfig):
            return AvailabilityChrono(action_config)
        elif isinstance(action_config, UpdateAppointmentChronoConfig):
            return UpdateAppointmentChrono(action_config)
        elif isinstance(action_config, DeleteAppointmentChronoConfig):
            return DeleteAppointmentChrono(action_config)
        else:
            raise Exception("Invalid action type")
