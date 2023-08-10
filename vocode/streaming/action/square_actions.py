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

class ServicesConfig(ActionConfig, type="get_services"):
    pass

class ServicesParameters(BaseModel):
    token: Optional[str] = Field(None, description="token for the API call.")
    timezone: Optional[str] = Field(None, description="business' timezone.")
    location_id: Optional[str] = Field(None, description="ID corresponding to the business' location.")

class ServicesOutput(BaseModel):
    response: str

class GetServices(BaseAction[ServicesConfig, ServicesParameters, ServicesOutput]):
    description: str = "Use this function if the SERVICES section is empty. Output is services offered by the company"
    action_type: str = "get_services"
    parameters_type: Type[ServicesParameters] = ServicesParameters
    response_type: Type[ServicesOutput] = ServicesOutput

    def get_services(self, token, location_id):
            url = "https://connect.squareup.com/v2/catalog/list"
            headers = {
                "Square-Version": "2023-04-19",
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json"
            }

            response = requests.get(url, headers=headers)

            if response.status_code == 200:
                data = response.json()
                item_names = []
                for item in data["objects"]:
                    if (item["type"] == "ITEM" and
                        item["item_data"]["product_type"] == "APPOINTMENTS_SERVICE" and
                        (item.get("present_at_all_locations") or location_id in item.get("present_at_location_ids", []))):
                        for variation in item['item_data']['variations']:
                                    variation_id = variation['id']
                                    service_version = variation['version']
                        item_names.append(item["item_data"]["name"])
                        # item_names.append({"Service name": item["item_data"]["name"], "Variation": variation_id, "Version": service_version})
                return item_names
            else:
                return "Request failed with status code: ", response.status_code, response.json()

    async def run(
        self, action_input: ActionInput[ServicesParameters]
    ) -> ActionOutput[ServicesOutput]:

        response = self.get_services(action_input.params.token, action_input.params.location_id)

        return ActionOutput(
            action_type=action_input.action_config.type,
            response=ServicesOutput(response=str(response)),
        )

class AvailabilityConfig(ActionConfig, type="get_availability"):
    pass

class AvailabilityParameters(BaseModel):
    service: str = Field(..., description="Name of the service that matches the caller's request.")
    date: str = Field(..., description="Desired month and day of the month for the appointment, formatted as: June, 5th")
    time: str = Field(..., description="Desired time for the appointment, formatted as: 8 AM")
    token: Optional[str] = Field(None, description="token for the API call.")
    timezone: Optional[str] = Field(None, description="business' timezone.")
    location_id: Optional[str] = Field(None, description="ID corresponding to the business' location.")

class AvailabilityOutput(BaseModel):
    response: str

class GetAvailability(BaseAction[AvailabilityConfig, AvailabilityParameters, AvailabilityOutput]):
    description: str = "Use if IMMEDIATE AVAILAVILITIES are not enough. Output is availabilities for a specific service on a 24 hour range, starting from the date and time specified"
    action_type: str = "get_availability"
    parameters_type: Type[AvailabilityParameters] = AvailabilityParameters
    response_type: Type[AvailabilityOutput] = AvailabilityOutput

    def get_variation_id(self, service, token, location_id):
            url = "https://connect.squareup.com/v2/catalog/list"
            headers = {
                "Square-Version": "2023-04-19",
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json"
            }

            response = requests.get(url, headers=headers)

            if response.status_code == 200:
                data = response.json()
                for item in data["objects"]:
                    if (item["type"] == "ITEM" and
                        item['item_data']['name'] == service and
                        item["item_data"]["product_type"] == "APPOINTMENTS_SERVICE" and
                        (item.get("present_at_all_locations") or location_id in item.get("present_at_location_ids", []))):
                        for variation in item['item_data']['variations']:
                                    variation_id = variation['id']
                return variation_id
            else:
                print("Request failed with status code:", response.status_code, response.json())

    def get_availability(self, location_id, variation_id, av_first, av_ahead, token):
        url = "https://connect.squareup.com/v2/bookings/availability/search"
        headers = {
            "Square-Version": "2023-04-19",
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        data = {
            "query": {
                "filter": {
                    "start_at_range": {
                        "end_at": f"{av_ahead}",
                        "start_at": f"{av_first}"
                    },
                    "location_id": f"{location_id}",
                    "segment_filters": [
                        {
                            "service_variation_id": f"{variation_id}"
                        }
                    ]
                }
            }
        }
        response = requests.post(url, headers=headers, json=data)
        if response.status_code == 200:
            response_json = response.json()
            if 'availabilities' in response_json and response_json['availabilities']:
                availability = response_json['availabilities'][:4]
                return availability
            else:
                print("No availabilities found in the response.")
                return None
        else:
            print("Request failed with status code:", response.status_code, response.text)

    def parse_availability(self, datetime, tz_str):
        date_time_tz_str = None  
        date_time_ahead_tz_str = None  

        try:
            date_time_obj = parser.parse(datetime)
            tz = timezone(tz_str)
            date_time_tz = tz.localize(date_time_obj)
            date_time_tz_str = date_time_tz.isoformat()
            date_time_ahead_obj = date_time_tz + timedelta(hours=24)  # Add 24 hours
            date_time_ahead_tz_str = date_time_ahead_obj.isoformat()
        except AttributeError:
            print("no date or time found")
            pass
        return date_time_tz_str, date_time_ahead_tz_str

    async def run(
        self, action_input: ActionInput[AvailabilityParameters]
    ) -> ActionOutput[AvailabilityOutput]:

        av_first, av_ahead = self.parse_availability(action_input.params.date + " " + action_input.params.time, action_input.params.timezone)
        variation_id = self.get_variation_id(action_input.params.service, action_input.params.token, action_input.params.location_id)
        availability = self.get_availability(action_input.params.location_id, variation_id, av_first, av_ahead, action_input.params.token)

        return ActionOutput(
            action_type=action_input.action_config.type,
            response=AvailabilityOutput(response=str(availability)),
        )

class SchedulerConfig(ActionConfig, type="book_appointment"):
    pass

class SchedulerParameters(BaseModel):
    name: str = Field(..., description="Name of the caller")
    phone: str = Field(..., description="Phone number of the caller")
    service: str = Field(..., description="Name of the service that matches the caller's request.")
    date: str = Field(..., description="Month and day of the month for the appointment, formatted as: June, 5th")
    time: str = Field(..., description="Desired time for the appointment, formatted as: 8 AM")
    token: Optional[str] = Field(None, description="token for the API call.")
    timezone: Optional[str] = Field(None, description="business' timezone.")
    location_id: Optional[str] = Field(None, description="ID corresponding to the business' location.")

class SchedulerOutput(BaseModel):
    response: str

class Scheduler(BaseAction[SchedulerConfig, SchedulerParameters, SchedulerOutput]):
    description: str = "Use a caller's name and phone number to book an appointment for a specific service on a given location, date and time"
    action_type: str = "book_appointment"
    parameters_type: Type[SchedulerParameters] = SchedulerParameters
    response_type: Type[SchedulerOutput] = SchedulerOutput

    def create_customer(self, name, phone, token):
        try:
            url = 'https://connect.squareup.com/v2/customers'
            headers = {
                'Square-Version': '2023-04-19',
                'Authorization': f'Bearer {token}',
                'Content-Type': 'application/json'
            }
            data = {
                "given_name": f"{name}",
                "phone_number": f"{phone}"
            }
            response = requests.post(url, headers=headers, json=data)
            response_json = response.json()
            if 'customer' in response_json:
                customer_id = response_json['customer']['id']
                return customer_id
            else:
                print("Customer creation failed.")
        except NameError:
            print("Variable 'name or phone' not defined.")
        except KeyError:
            print("Key 'customer' not found in response JSON.")

    def get_service_data(self, token, service, location_id):
            url = "https://connect.squareup.com/v2/catalog/list"
            headers = {
                "Square-Version": "2023-04-19",
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json"
            }

            response = requests.get(url, headers=headers)

            if response.status_code == 200:
                data = response.json()
                item_names = []
                for item in data["objects"]:
                    if (item["type"] == "ITEM" and
                        item['item_data']['name'] == service and
                        item["item_data"]["product_type"] == "APPOINTMENTS_SERVICE" and
                        (item.get("present_at_all_locations") or location_id in item.get("present_at_location_ids", []))):
                        for variation in item['item_data']['variations']:
                                    variation_id = variation['id']
                                    service_version = variation['version']
                return variation_id, service_version
            else:
                print("Request failed with status code:", response.status_code, response.json())

    def get_team_member_ids(self, token):
        url = "https://connect.squareup.com/v2/team-members/search"
        headers = {
            "Square-Version": "2023-04-19",
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }

        response = requests.post(url, headers=headers)
        response_data = response.json()

        team_members = response_data.get("team_members", [])
        team_member_ids = [member.get("id") for member in team_members]

        return team_member_ids

    def create_booking(self, location, variation_id, service_version, customer_id, booking, token, member_ids):
        if location is not None:
            headers = {
                'Square-Version': '2023-04-19',
                'Authorization': f'Bearer {token}',
                'Content-Type': 'application/json'
            }
            for member_id in member_ids:
                try:
                    data = {
                        "booking": {
                            "location_id": f"{location}",
                            "location_type": "BUSINESS_LOCATION",
                            "appointment_segments": [
                                {
                                    "service_variation_id": f"{variation_id}",
                                    "team_member_id": f"{member_id}",
                                    "service_variation_version": f"{service_version}"
                                }
                            ],
                            "customer_id": f"{customer_id}",
                            "start_at": f"{booking}"
                        }
                    }
                    response = requests.post('https://connect.squareup.com/v2/bookings', headers=headers, data=json.dumps(data))
                    print(response.status_code)
                    if response.status_code == 200 or response.status_code == 201:
                        return response.json()
                    else:
                        print(response.json())
                        continue
                except Exception as e:
                    print(f"An error occurred: {e}")
                    continue
            return {"error": "Could not create booking with any member_id"}

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
        self, action_input: ActionInput[SchedulerParameters]
    ) -> ActionOutput[SchedulerOutput]:

        customer_id = self.create_customer(action_input.params.name, action_input.params.phone.replace('-', ''), action_input.params.token)
        member_ids = self.get_team_member_ids(action_input.params.token)
        variation_id, service_version  = self.get_service_data(action_input.params.token, action_input.params.service, action_input.params.location_id)
        date_time = self.parse_booking(action_input.params.date + " " + action_input.params.time, action_input.params.timezone)
        booking = self.create_booking(action_input.params.location_id, variation_id, service_version, customer_id, date_time, action_input.params.token, member_ids)

        return ActionOutput(
            action_type=action_input.action_config.type,
            response=SchedulerOutput(response=str(booking)),
        )

class BookingsConfig(ActionConfig, type="get_bookings"):
    pass

class BookingsParameters(BaseModel):
    date: str = Field(..., description="Month and day of the month of the booking to look for, formatted as: June, 5th")
    time: str = Field(..., description="Time of the booking to look for, formatted as: 8 AM")
    token: Optional[str] = Field(None, description="token for the API call.")
    timezone: Optional[str] = Field(None, description="business' timezone.")
    location_id: Optional[str] = Field(None, description="ID corresponding to the business' location.")

class BookingsOutput(BaseModel):
    response: str

class GetBookings(BaseAction[BookingsConfig, BookingsParameters, BookingsOutput]):
    description: str = "Consult our current bookings on a 24 hour range, starting from the date and time specified"
    action_type: str = "get_bookings"
    parameters_type: Type[BookingsParameters] = BookingsParameters
    response_type: Type[BookingsOutput] = BookingsOutput

    def get_service_name(self, service_variation_id, token):
        url = "https://connect.squareup.com/v2/catalog/search-catalog-items"
        headers = {
            "Square-Version": "2023-06-08",
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        data = {
            "product_types": ["APPOINTMENTS_SERVICE"]
        }

        response = requests.post(url, headers=headers, json=data)

        if response.status_code != 200:
            raise Exception("Request failed with status %s" % response.status_code)

        items = response.json().get('items', [])

        for item in items:
            for variation in item.get('item_data', {}).get('variations', []):
                if variation.get('id') == service_variation_id:
                    return item.get('item_data', {}).get('name')

        return "No service name found" 

    def get_customer_details(self, customer_id, token):
        url = f"https://connect.squareup.com/v2/customers/{customer_id}"
        headers = {
            "Square-Version": "2023-06-08",
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

        response = requests.get(url, headers=headers)

        if response.status_code != 200:
            return response.content

        customer = response.json().get('customer', {})

        return {
            "given_name": customer.get('given_name', ''),
            "phone_number": customer.get('phone_number', ''),
        }

    def get_square_bookings(self, start_at_min, start_at_max, token):
        url = "https://connect.squareup.com/v2/bookings"
        headers = {
            "Square-Version": "2023-06-08",
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        params = {
            "start_at_min": start_at_min,
            "start_at_max": start_at_max,
        }

        response = requests.get(url, headers=headers, params=params)

        if response.status_code != 200:
            return response.content

        bookings = response.json().get('bookings', [])

        booking_details = []
        for booking in bookings:
            customer_details = self.get_customer_details(booking['customer_id'], token)
            service_name = self.get_service_name(booking['appointment_segments'][0]['service_variation_id'], token)
            booking_details.append({
                "id": booking['id'],
                "start_at": booking['start_at'],
                "customer_id": booking['customer_id'],
                "given_name": customer_details['given_name'],
                "phone_number": customer_details['phone_number'],
                "service_name": service_name,
            })

        return booking_details

    def parse_time(self, datetime, tz_str):
        date_time_tz_str = None  
        date_time_ahead_tz_str = None  

        try:
            date_time_obj = parser.parse(datetime)
            tz = timezone(tz_str)
            date_time_tz = tz.localize(date_time_obj)
            date_time_tz_str = date_time_tz.isoformat()
            date_time_ahead_obj = date_time_tz + timedelta(hours=24)  # Add 24 hours
            date_time_ahead_tz_str = date_time_ahead_obj.isoformat()
        except AttributeError:
            print("no date or time found")
            pass
        return date_time_tz_str, date_time_ahead_tz_str

    async def run(
        self, action_input: ActionInput[BookingsParameters]
    ) -> ActionOutput[BookingsOutput]:

        first_time, time_ahead = self.parse_time(action_input.params.date + " " + action_input.params.time, action_input.params.timezone)
        bookings = self.get_square_bookings(first_time, time_ahead, action_input.params.token)

        return ActionOutput(
            action_type=action_input.action_config.type,
            response=BookingsOutput(response=str(bookings)),
        )

class UpdateBookingConfig(ActionConfig, type="update_booking"):
    pass

class UpdateBookingParameters(BaseModel):
    booking_id: str = Field(..., description="ID of the appointment to cancel")
    date: str = Field(..., description="Month and day of the month for the new booking, formatted as: June, 5th")
    time: str = Field(..., description="Time for the new booking, formatted as: 8 AM")
    token: Optional[str] = Field(None, description="token for the API call.")
    timezone: Optional[str] = Field(None, description="business' timezone.")
    location_id: Optional[str] = Field(None, description="ID corresponding to the business' location.")

class UpdateBookingOutput(BaseModel):
    response: str

class UpdateBooking(BaseAction[UpdateBookingConfig, UpdateBookingParameters, UpdateBookingOutput]):
    description: str = "Update booking to a new date and time"
    action_type: str = "update_booking"
    parameters_type: Type[UpdateBookingParameters] = UpdateBookingParameters
    response_type: Type[UpdateBookingOutput] = UpdateBookingOutput

    def update_booking(self, booking_id, start_at, token):
        url = f"https://connect.squareup.com/v2/bookings/{booking_id}"
        headers = {
            "Square-Version": "2023-06-08",
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        data = {
            "booking": {
                "start_at": start_at
            }
        }

        response = requests.put(url, headers=headers, json=data)

        if response.status_code != 200:
            return response.content

        booking = response.json().get('booking', {})

        return {
            "id": booking.get('id', ''),
            "status": booking.get('status', ''),
            "created_at": booking.get('created_at', ''),
            "updated_at": booking.get('updated_at', ''),
            "start_at": booking.get('start_at', ''),
        }

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
        self, action_input: ActionInput[UpdateBookingParameters]
    ) -> ActionOutput[UpdateBookingOutput]:

        start_at = self.parse_booking(action_input.params.date + " " + action_input.params.time, action_input.params.timezone)
        new_booking = self.update_booking(action_input.params.booking_id, start_at, action_input.params.token)

        return ActionOutput(
            action_type=action_input.action_config.type,
            response=UpdateBookingOutput(response=str(new_booking)),
        )

class CancelBookingConfig(ActionConfig, type="cancel_booking"):
    pass

class CancelBookingParameters(BaseModel):
    booking_id: str = Field(..., description="ID of the appointment to cancel")
    token: Optional[str] = Field(None, description="token for the API call.")
    timezone: Optional[str] = Field(None, description="business' timezone.")
    location_id: Optional[str] = Field(None, description="ID corresponding to the business' location.")

class CancelBookingOutput(BaseModel):
    response: str

class CancelBooking(BaseAction[CancelBookingConfig, CancelBookingParameters, CancelBookingOutput]):
    description: str = "Cancel a specific appointment"
    action_type: str = "cancel_booking"
    parameters_type: Type[CancelBookingParameters] = CancelBookingParameters
    response_type: Type[CancelBookingOutput] = CancelBookingOutput

    def cancel_booking(self, booking_id, token):
        url = f"https://connect.squareup.com/v2/bookings/{booking_id}/cancel"

        headers = {
            'Square-Version': '2023-06-08',
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json',
        }

        response = requests.post(url, headers=headers)
        return response.json()

    async def run(
        self, action_input: ActionInput[CancelBookingParameters]
    ) -> ActionOutput[CancelBookingOutput]:

        canceled = self.cancel_booking(action_input.params.booking_id, action_input.params.token)

        return ActionOutput(
            action_type=action_input.action_config.type,
            response=CancelBookingOutput(response=str(canceled)),
        )