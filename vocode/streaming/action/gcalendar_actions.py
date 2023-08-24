import requests
from datetime import datetime, timedelta
from typing import Optional, Type
from pydantic import BaseModel, Field
import os
from vocode.streaming.action.base_action import BaseAction
from vocode.streaming.models.actions import ActionInput, ActionOutput, ActionType, ActionConfig

import requests
import re
from dateutil import parser
from pytz import timezone
import json

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

class BookGoogleConfig(ActionConfig, type="book_google"):
    pass

class BookGoogleParameters(BaseModel):
    date: str = Field(..., description="Date and time for the appointment, formatted as: July 8th, 8 AM")
    name: str = Field(..., description="Name provided by the caller")
    phone: int = Field(..., description="Phone number provided by the caller")
    token: Optional[str] = Field(None, description="token for the API call.")
    timezone: Optional[str] = Field(None, description="business' timezone.")
    location_id: Optional[int] = Field(None, description="business' location ID.")

class BookGoogleOutput(BaseModel):
    response: str

class BookChrono(BaseAction[BookGoogleConfig, BookGoogleParameters, BookGoogleOutput]):
    description: str = "Book an appointment on a specific date and time"
    action_type: str = "book_google"
    parameters_type: Type[BookGoogleParameters] = BookGoogleParameters
    response_type: Type[BookGoogleOutput] = BookGoogleOutput
    
    def create_booking(self, name, location, tz_str, date):
        creds = Credentials.from_authorized_user_file('token.json')
        service = build('calendar', 'v3', credentials=creds)
        event = {
                'summary': f'Appointment for {name}',
                'location': f'{location}',
                'description': f'Booked by folks on {datetime.now(timezone(tz_str))}',
                'start': {
                    'dateTime': f'{date}',
                    'timeZone': f'{tz_str}',
                },
                'end': {
                    'dateTime': f'{date + timedelta(minutes=60)}',
                    'timeZone': f'{tz_str}',
                },
                'reminders': {
                    'useDefault': False,
                    'overrides': [
                    {'method': 'email', 'minutes': 24 * 60},
                    {'method': 'popup', 'minutes': 10},
                    ],
                },
                }

        event = service.events().insert(calendarId='primary', body=event).execute()
        return 'Event created: %s' % (event.get('htmlLink'))

    def parse_booking(self, datetime, tz_str):
        date_time_pt_str = None
        if datetime:
                    date_time_obj = parser.parse(datetime)
                    pt_timezone = timezone(tz_str)
                    date_time_pt = pt_timezone.localize(date_time_obj)
                    date_time_pt_str = date_time_pt.isoformat()
        else:
            pass
        return date_time_pt_str

    async def run(
        self, action_input: ActionInput[BookGoogleParameters]
    ) -> ActionOutput[BookGoogleOutput]:

        date_time = self.parse_booking(action_input.params.date, action_input.params.timezone)
        response = self.create_booking(action_input.params.name, action_input.params.location_id, action_input.params.timezone, date_time)

        return ActionOutput(
            action_type=action_input.action_config.type,
            response=BookGoogleOutput(response=str(response)),
        )
    
class AvailabilityGoogleConfig(ActionConfig, type="google_availability"):
    pass

class AvailabilityGoogleParameters(BaseModel):
    date: str = Field(..., description="Desired month and day of the month for the appointment, formatted as: June, 5th")
    token: Optional[str] = Field(None, description="token for the API call.")
    timezone: Optional[str] = Field(None, description="business' timezone.")
    location_id: Optional[int] = Field(None, description="business' location ID.")

class AvailabilityGoogleOutput(BaseModel):
    response: str

class AvailabilityChrono(BaseAction[AvailabilityGoogleConfig, AvailabilityGoogleParameters, AvailabilityGoogleOutput]):
    description: str = "Consult booked appointments. Output is the next 5 booked appointments, starting from the date and time specified."
    action_type: str = "google_availability"
    parameters_type: Type[AvailabilityGoogleParameters] = AvailabilityGoogleParameters
    response_type: Type[AvailabilityGoogleOutput] = AvailabilityGoogleOutput
    
    def get_bookings(self, tz_str, date):
        creds = Credentials.from_authorized_user_file('token.json')
        service = build('calendar', 'v3', credentials=creds)
        
        try:
                    time = self.parse_time(date, tz_str)
                    print('Getting the upcoming 10 events')
                    events_result = service.events().list(calendarId='primary', timeMin=time,
                                                        maxResults=5, singleEvents=True,
                                                        orderBy='startTime').execute()
                    events = events_result.get('items', [])

                    if not events:
                        return 'No upcoming events found.'

                    for event in events:
                        start = event['start'].get('dateTime', event['start'].get('date'))
                        return start, event['summary']

        except HttpError as error:
                        return 'An error occurred: %s' % error

    def parse_time(self, datetime, tz_str):
        date_time_pt_str = None
        if datetime:
                    date_time_obj = parser.parse(datetime)
                    pt_timezone = timezone(tz_str)
                    date_time_pt = pt_timezone.localize(date_time_obj)
                    date_time_pt_str = date_time_pt.isoformat()
        else:
            pass
        return date_time_pt_str

    async def run(
        self, action_input: ActionInput[AvailabilityGoogleParameters]
    ) -> ActionOutput[AvailabilityGoogleOutput]:

        response = self.get_bookings(action_input.params.timezone, action_input.params.date)

        return ActionOutput(
            action_type=action_input.action_config.type,
            response=AvailabilityGoogleOutput(response=str(response)),
        )