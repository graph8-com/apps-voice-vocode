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
    

def appointment_templates_list(token, cursor, doctor, office, page_size, profile):
    BASE_URL = "https://app.drchrono.com/api"
    HEADERS = {
    "Authorization": f"Bearer {token}",
    "Content-Type": "application/json",
}
    params = {
        "cursor": cursor,
        "doctor": doctor,
        "office": office,
        "page_size": page_size,
        "profile": profile,
    }
    params = {k: v for k, v in params.items() if v is not None}

    response = requests.get(f"{BASE_URL}/appointment_templates_list", headers=HEADERS, params=params)

    if response.status_code == 200:
        return response.json()
    else:
        return response.status_code, response.text


def appointment_templates_read(token, id, doctor, office, profile):
    BASE_URL = "https://app.drchrono.com/api"
    HEADERS = {
    "Authorization": f"Bearer {token}",
    "Content-Type": "application/json",
}
    params = {
        "doctor": doctor,
        "office": office,
        "profile": profile,
        "verbose": True,
        "available": True,
    }
    params = {k: v for k, v in params.items() if v is not None}

    response = requests.get(f"{BASE_URL}/appointment_templates_read/{id}", headers=HEADERS, params=params)

    if response.status_code == 200:
        return response.json()
    else:
        return response.status_code, response.text
    

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