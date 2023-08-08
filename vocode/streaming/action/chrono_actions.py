import requests
from datetime import datetime
from typing import Optional, Type
from pydantic import BaseModel, Field
import os
from vocode.streaming.action.base_action import BaseAction
from vocode.streaming.models.actions import ActionInput, ActionOutput, ActionType, ActionConfig

import requests
import re
from dateutil import parser
from datetime import timedelta
from pytz import timezone
import json

class BookChronoConfig(ActionConfig, type="book_chrono"):
    pass

class BookChronoParameters(BaseModel):
    date: str = Field(..., description="Date and time for the appointment, formatted as: July 8th, 8 AM")
    doctor: int = Field(..., description="ID of the doctor")
    name: str = Field(..., description="Name of the patient")
    phone: int = Field(..., description="Phone number of the patient")
    duration: int = Field(..., description="Duration of the appointment to book")
    token: Optional[str] = Field(None, description="token for the API call.")
    timezone: Optional[str] = Field(None, description="business' timezone.")
    location_id: Optional[int] = Field(None, description="business' location ID.")

class BookChronoOutput(BaseModel):
    response: str

class BookChrono(BaseAction[BookChronoConfig, BookChronoParameters, BookChronoOutput]):
    description: str = "Book an appointment on a specific date and time with a doctor"
    action_type: str = "book_chrono"
    parameters_type: Type[BookChronoParameters] = BookChronoParameters
    response_type: Type[BookChronoOutput] = BookChronoOutput

    def create_patient(self, access_token, doctor, first_name, cell_phone):
        url = "https://app.drchrono.com/api/patients"
        headers = {
            'Authorization': f'Bearer {access_token}',
        }
        data = {
            'doctor': doctor,
            'first_name': first_name,
            'gender': 'UNK',
            'cell_phone': cell_phone,
        }
        response = requests.post(url, headers=headers, data=data)

        if response.status_code == 201:
            return response.json()
        else:
            response.raise_for_status()
            return response.json()

    def book_appointment(self, access_token, date, doctor, patient, office, duration):
        url = "https://app.drchrono.com/api/appointments"
        headers = {
            'Authorization': 'Bearer {}'.format(access_token),
            'Content-Type': 'application/json'
        }
        params = {
            'doctor': f'{doctor}',
            'patient': f'{patient}',
            'office': f'{office}',
            'scheduled_time': f'{date}',
            'exam_room': 1,
            'duration': f'{duration}',
        }
        response = requests.post(url, headers=headers, json=params)

        if response.status_code == 200 or 201:
            return f"Appointment successfully created with status code {response.status_code}"
        else:
            print("Failed to create appointment. Status code: ", response.status_code)
            return response.json()

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
        self, action_input: ActionInput[BookChronoParameters]
    ) -> ActionOutput[BookChronoOutput]:

        patient = self.create_patient(action_input.params.token, action_input.params.doctor, action_input.params.name, action_input.params.phone)
        date_time = self.parse_booking(action_input.params.date, action_input.params.timezone)
        response = self.book_appointment(action_input.params.token, date_time, action_input.params.doctor, patient['id'], action_input.params.location_id, action_input.params.duration)

        return ActionOutput(
            action_type=action_input.action_type,
            response=BookChronoOutput(response=str(response)),
        )


class AvailabilityChronoConfig(ActionConfig, type="availability"):
    pass

class AvailabilityChronoParameters(BaseModel):
    doctor: int = Field(..., description="ID of the doctor")
    date: str = Field(..., description="Desired month and day of the month for the appointment, formatted as: June, 5th")
    location_id: Optional[int] = Field(..., description="ID corresponding to the business' location")
    token: Optional[str] = Field(None, description="token for the API call")
    timezone: Optional[str] = Field(None, description="business' timezone")

class AvailabilityChronoOutput(BaseModel):
    response: str

class AvailabilityChrono(BaseAction[AvailabilityChronoConfig, AvailabilityChronoParameters, AvailabilityChronoOutput]):
    description: str = "Create a patient for a doctor"
    action_type: str = "availability"
    parameters_type: Type[AvailabilityChronoParameters] = AvailabilityChronoParameters
    response_type: Type[AvailabilityChronoOutput] = AvailabilityChronoOutput

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

    def list_appointments(self, access_token, date, doctor, office):

        base_url = "https://app.drchrono.com/api"

        endpoint = "/appointments"

        url = base_url + endpoint

        headers = {
            'Authorization': 'Bearer {}'.format(access_token),
            'Content-Type': 'application/json'
        }

        params = {
            'date': f'{date}',
            'doctor': f'{doctor}',
            'office': f'{office}',
            'status': 'confirmed',
            'page_size': 5 
        }

        response = requests.get(url, headers=headers, params=params)

        if response.status_code == 200:
            print("Successfully retrieved appointments.")
            return response.json() 
        else:
            print("Failed to retrieve appointments. Status code: ", response.status_code)
            return response.json()

    async def run(
        self, action_input: ActionInput[AvailabilityChronoParameters]
    ) -> ActionOutput[AvailabilityChronoOutput]:

        date = self.parse_booking(action_input.params.date, action_input.params.timezone)
        response = self.list_appointments(action_input.params.token, date, action_input.params.doctor, action_input.params.location_id)

        return ActionOutput(
            action_type=action_input.action_type,
            response=AvailabilityChronoOutput(response=str(response)),
        )

class ServicesChronoConfig(ActionConfig, type="chrono_services"):
    pass

class ServicesChronoParameters(BaseModel):
    doctor: int = Field(..., description="ID of the doctor")
    location_id: Optional[int] = Field(..., description="ID corresponding to the business' location")
    token: Optional[str] = Field(None, description="token for the API call")
    timezone: Optional[str] = Field(None, description="business' timezone")

class ServicesChronoOutput(BaseModel):
    response: str

class ServicesChrono(BaseAction[ServicesChronoConfig, ServicesChronoParameters, ServicesChronoOutput]):
    description: str = "Retrieve services offered by the doctor"
    action_type: str = "chrono_services"
    parameters_type: Type[ServicesChronoParameters] = ServicesChronoParameters
    response_type: Type[ServicesChronoOutput] = ServicesChronoOutput

    def appointment_profiles_list(access_token, cursor=None, doctor=None, page_size=None):
        url = "https://app.drchrono.com/api/appointment_profiles"
        headers = {
            'Authorization': f'Bearer {access_token}',
        }
        params = {
            'cursor': cursor,
            'doctor': doctor,
            'page_size': page_size,
        }
        response = requests.get(url, headers=headers, params=params)
        services = []
        if response.status_code == 200:
            for i in response.json()['results']:
                services.append([i['name'], i['id'], f"Duration: {i['duration']}"])
            return services
        else:
            response.raise_for_status()

    async def run(
        self, action_input: ActionInput[ServicesChronoParameters]
    ) -> ActionOutput[ServicesChronoOutput]:

        response = self.appointment_profiles_list(action_input.params.token, action_input.params.doctor)

        return ActionOutput(
            action_type=action_input.action_type,
            response=ServicesChronoOutput(response=str(response)),
        )

def delete_appointment(access_token, appointment_id):
    base_url = "https://app.drchrono.com/api"

    endpoint = f"/appointments/{appointment_id}"

    url = base_url + endpoint

    headers = {
        'Authorization': 'Bearer {}'.format(access_token),
    }

    response = requests.delete(url, headers=headers)

    if response.status_code == 204:
        print("Appointment successfully deleted.")
    else:
        print("Failed to delete appointment. Status code: ", response.status_code)
        return response.json()

def update_appointment(access_token, appointment_id):
    base_url = "https://app.drchrono.com/api"

    endpoint = f"/appointments/{appointment_id}"

    url = base_url + endpoint

    headers = {
        'Authorization': 'Bearer {}'.format(access_token),
        'Content-Type': 'application/json'
    }

    params = {
        'date': datetime.now().isoformat(), 
        'doctor': 123, 
        'office': 456, 
        'patient': 789,  
        'status': 'confirmed'  
    }

    response = requests.patch(url, headers=headers, json=params)

    if response.status_code == 200:
        print("Appointment successfully updated.")
        return response.json() 
    else:
        print("Failed to update appointment. Status code: ", response.status_code)
        return response.json()



# LOCATIONS 
def offices_list(access_token, cursor=None, doctor=None, page_size=None):
    url = "https://app.drchrono.com/api/offices"
    headers = {
        'Authorization': f'Bearer {access_token}',
    }
    params = {
        'cursor': cursor,
        'doctor': doctor,
        'page_size': page_size,
    }

    response = requests.get(url, headers=headers, params=params)

    if response.status_code == 200:
        return response.json()
    else:
        response.raise_for_status()

def appointment_profiles_read(access_token, id, doctor=None):
    url = f"https://app.drchrono.com/api/appointment_profiles/{id}"
    headers = {
        'Authorization': f'Bearer {access_token}',
    }
    params = {
        'doctor': doctor,
    }

    response = requests.get(url, headers=headers, params=params)

    if response.status_code == 200:
        return response.json()
    else:
        response.raise_for_status()

def patients_list(access_token, doctor=None, first_name=None, cell_phone=None):
    url = "https://app.drchrono.com/api/patients"
    headers = {
        'Authorization': f'Bearer {access_token}',
    }
    params = {
        'doctor': doctor,
        'first_name': first_name,
        'gender': 'UNK',
        'cell_phone': cell_phone,
    }

    response = requests.get(url, headers=headers, params=params)

    if response.status_code == 200:
        return response.json()
    else:
        response.raise_for_status()