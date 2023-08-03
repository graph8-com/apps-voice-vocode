import requests
from datetime import datetime
from typing import Optional, Type
from pydantic import BaseModel, Field
import os
from vocode.streaming.action.base_action import BaseAction
from vocode.streaming.models.actions import ActionInput, ActionOutput, ActionType

import requests
import re
from dateutil import parser
from datetime import timedelta
from pytz import timezone
import json


class BookChronoParameters(BaseModel):
    date: str = Field(..., description="Date and time for the appointment, formatted as: July 8th, 8 AM")
    doctor: int = Field(..., description="ID of the doctor")
    patient: int = Field(..., description="ID of the patient")
    token: Optional[str] = Field(None, description="token for the API call.")
    timezone: Optional[str] = Field(None, description="business' timezone.")

class BookChronoOutput(BaseModel):
    response: str

class BookChrono(BaseAction[BookChronoParameters, BookChronoOutput]):
    description: str = "Book an appointment on a specific date and time with a doctor"
    action_type: str = "book_chrono"
    parameters_type: Type[BookChronoParameters] = BookChronoParameters
    response_type: Type[BookChronoOutput] = BookChronoOutput

    def book_appointment(self, access_token, date, doctor, patient):
        url = "https://app.drchrono.com/api/appointments"
        headers = {
            'Authorization': 'Bearer {}'.format(access_token),
            'Content-Type': 'application/json'
        }

        params = {
            'date': f'{date}', 
            'doctor': f'{doctor}',
            'patient': f'{patient}',
        }

        response = requests.post(url, headers=headers, json=params)

        if response.status_code == 200:
            print("Appointment successfully created.")
            return response.json()
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
        
        date_time = self.parse_booking(action_input.params.date, action_input.params.timezone)
        response = self.book_appointment(action_input.params.token, date_time, action_input.params.doctor, action_input.params.patient)

        return ActionOutput(
            action_type=action_input.action_type,
            response=BookChronoOutput(response=str(response)),
        )


class PatientChronoParameters(BaseModel):
    doctor: int = Field(..., description="ID of the doctor")
    patient: str = Field(..., description="Patient's first name")
    phone: int = Field(..., description="Patient's phone number")
    token: Optional[str] = Field(None, description="token for the API call.")
    timezone: Optional[str] = Field(None, description="business' timezone.")

class PatientChronoOutput(BaseModel):
    response: str

class PatientChrono(BaseAction[PatientChronoParameters, PatientChronoOutput]):
    description: str = "Create a patient for a doctor"
    action_type: str = "create_patient"
    parameters_type: Type[PatientChronoParameters] = PatientChronoParameters
    response_type: Type[PatientChronoOutput] = PatientChronoOutput

    def patients_create(access_token, doctor=None, first_name=None, cell_phone=None):
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

    async def run(
        self, action_input: ActionInput[PatientChronoParameters]
    ) -> ActionOutput[PatientChronoOutput]:
        
        response = self.patients_create(action_input.params.token, action_input.params.doctor, action_input.params.patient, action_input.params.phone)

        return ActionOutput(
            action_type=action_input.action_type,
            response=PatientChronoOutput(response=str(response)),
        )
    


def list_appointments(access_token):

    base_url = "https://app.drchrono.com/api"

    endpoint = "/appointments"

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
        'status': 'confirmed', 
        'page_size': 20 
    }

    response = requests.get(url, headers=headers, params=params)

    if response.status_code == 200:
        print("Successfully retrieved appointments.")
        return response.json() 
    else:
        print("Failed to retrieve appointments. Status code: ", response.status_code)
        return response.json()

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
    
def list_doctors(access_token):
    base_url = "https://app.drchrono.com/api"

    endpoint = "/doctors"

    url = base_url + endpoint

    headers = {
        'Authorization': 'Bearer {}'.format(access_token),
    }

    params = {
        'page_size': 50 
    }

    response = requests.get(url, headers=headers, params=params)

    if response.status_code == 200:
        print("Successfully retrieved doctors.")
        return response.json()
    else:
        print("Failed to retrieve doctors. Status code: ", response.status_code)
        return response.json()
    

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

def patients_create(access_token, doctor=None, first_name=None, cell_phone=None):
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

def offices_read(access_token, id, doctor=None):
    url = f"https://app.drchrono.com/api/offices/{id}"
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

def book_appointment(access_token, date, doctor=None, patient=None, office=None, exam_room=None, duration=None):
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
            'exam_room': f'{exam_room}',
            'duration': f'{duration}',
        }

        response = requests.post(url, headers=headers, json=params)

        if response.status_code == 200 or 201:
            print("Appointment successfully created.")
            return response.json()
        else:
            print("Failed to create appointment. Status code: ", response.status_code)
            return response.json()
        
def parse_booking(datetime, tz_str):
        date_time_pt_str = None
        if datetime:
                    date_time_obj = parser.parse(datetime)
                    pt_timezone = timezone(tz_str)
                    date_time_pt = pt_timezone.localize(date_time_obj)
                    date_time_pt_str = date_time_pt.isoformat()
        else:
            pass
        return date_time_pt_str