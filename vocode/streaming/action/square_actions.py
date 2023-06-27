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


class NylasSendEmailParameters(BaseModel):
    recipient_email: str = Field(..., description="The email address of the recipient.")
    body: str = Field(..., description="The body of the email.")
    subject: Optional[str] = Field(None, description="The subject of the email.")


class NylasSendEmailResponse(BaseModel):
    success: bool


class NylasSendEmail(BaseAction[NylasSendEmailParameters, NylasSendEmailResponse]):
    description: str = "Sends an email using Nylas API."
    action_type: str = ActionType.NYLAS_SEND_EMAIL.value
    parameters_type: Type[NylasSendEmailParameters] = NylasSendEmailParameters
    response_type: Type[NylasSendEmailResponse] = NylasSendEmailResponse

    async def run(
        self, action_input: ActionInput[NylasSendEmailParameters]
    ) -> ActionOutput[NylasSendEmailResponse]:
        from nylas import APIClient

        # Initialize the Nylas client
        nylas = APIClient(
            client_id=os.getenv("NYLAS_CLIENT_ID"),
            client_secret=os.getenv("NYLAS_CLIENT_SECRET"),
            access_token=os.getenv("NYLAS_ACCESS_TOKEN"),
        )

        # Create the email draft
        draft = nylas.drafts.create()
        draft.body = action_input.params.body

        email_subject = action_input.params.subject
        draft.subject = email_subject if email_subject else "Email from Vocode"
        draft.to = [{"email": action_input.params.recipient_email.strip()}]

        # Send the email
        draft.send()

        return ActionOutput(
            action_type=action_input.action_type,
            response=NylasSendEmailResponse(success=True),
        )


class ServicesParameters(BaseModel):
    location_id: str = Field(..., description="ID corresponding to the single location if there's only one location; otherwise, ID corresponding to the location name selected by the caller.")
    token: Optional[str] = Field(None, description="token for the API call.")


class ServicesOutput(BaseModel):
    response: str

class GetServices(BaseAction[ServicesParameters, ServicesOutput]):
    description: str = "Retrieve services offered by the company"
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
            
    def _user_message_param_info(self):
        return {
            "type": "string",
            "description": """Just a moment please.""",
        }

    async def run(
        self, action_input: ActionInput[ServicesParameters]
    ) -> ActionOutput[ServicesOutput]:
        
        response = self.get_services(action_input.params.token, action_input.params.location_id)
        print(response)

        return ActionOutput(
            action_type=action_input.action_type,
            response=ServicesOutput(response=str(response)),
        )

class AvailabilityParameters(BaseModel):
    location_id: str = Field(..., description="ID corresponding to the single location if there's only one location; otherwise, ID corresponding to the location name selected by the caller.")
    service: str = Field(..., description="Name of the service that matches the caller's request.")
    date: str = Field(..., description="Month and day of the month for the appointment, formatted as: June, 5th")
    time: str = Field(..., description="Desired time for the appointment, formatted as: 8 AM")
    token: Optional[str] = Field(None, description="token for the API call.")

class AvailabilityOutput(BaseModel):
    response: str

class GetAvailability(BaseAction[AvailabilityParameters, AvailabilityOutput]):
    description: str = "Consult availability for a specific service on a 24 hour range, starting from the date and time specified"
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
    
    def parse_availability(self, datetime):
        date_time_pt_str = None  
        date_time_ahead_pt_str = None  

        try:
                    date_time_obj = parser.parse(datetime)
                    pt_timezone = timezone('US/Pacific')
                    date_time_pt = pt_timezone.localize(date_time_obj)
                    date_time_pt_str = date_time_pt.isoformat()
                    date_time_ahead_obj = date_time_pt + timedelta(hours=24)  # Add 24 hours for the square api call
                    date_time_ahead_pt_str = date_time_ahead_obj.isoformat()
        except AttributeError:
                print("no date or time found")
                pass
        return date_time_pt_str, date_time_ahead_pt_str
    
    def _user_message_param_info(self):
        return {
            "type": "string",
            "description": """Alright. Give me a sec to consult our availability.""",
        }

    async def run(
        self, action_input: ActionInput[AvailabilityParameters]
    ) -> ActionOutput[AvailabilityOutput]:
        
        av_first, av_ahead = self.parse_availability(action_input.params.date + " " + action_input.params.time)
        variation_id = self.get_variation_id(action_input.params.service, action_input.params.token, action_input.params.location_id)
        availability = self.get_availability(action_input.params.location_id, variation_id, av_first, av_ahead, action_input.params.token)
        print(availability)

        return ActionOutput(
            action_type=action_input.action_type,
            response=AvailabilityOutput(response=str(availability)),
        )
    

# class Scheduler(BaseAction[SchedulerOutput]):
#     def create_customer(self, name, phone, token):
#         try:
#             url = 'https://connect.squareup.com/v2/customers'
#             headers = {
#                 'Square-Version': '2023-04-19',
#                 'Authorization': f'Bearer {token}',
#                 'Content-Type': 'application/json'
#             }
#             data = {
#                 "given_name": f"{name}",
#                 "phone_number": f"{phone}"
#             }
#             response = requests.post(url, headers=headers, json=data)
#             response_json = response.json()
#             if 'customer' in response_json:
#                 customer_id = response_json['customer']['id']
#                 return customer_id
#             else:
#                 print("Customer creation failed.")
#         except NameError:
#             print("Variable 'name or phone' not defined.")
#         except KeyError:
#             print("Key 'customer' not found in response JSON.")

#     def get_service_data(self, token, service, location_id):
#             url = "https://connect.squareup.com/v2/catalog/list"
#             headers = {
#                 "Square-Version": "2023-04-19",
#                 "Authorization": f"Bearer {token}",
#                 "Content-Type": "application/json"
#             }

#             response = requests.get(url, headers=headers)

#             if response.status_code == 200:
#                 data = response.json()
#                 item_names = []
#                 for item in data["objects"]:
#                     if (item["type"] == "ITEM" and
#                         item['item_data']['name'] == service and
#                         item["item_data"]["product_type"] == "APPOINTMENTS_SERVICE" and
#                         (item.get("present_at_all_locations") or location_id in item.get("present_at_location_ids", []))):
#                         for variation in item['item_data']['variations']:
#                                     variation_id = variation['id']
#                                     service_version = variation['version']
#                 return variation_id, service_version
#             else:
#                 print("Request failed with status code:", response.status_code, response.json())
        
#     def get_team_member_ids(self, token):
#         url = "https://connect.squareup.com/v2/team-members/search"
#         headers = {
#             "Square-Version": "2023-04-19",
#             "Authorization": f"Bearer {token}",
#             "Content-Type": "application/json"
#         }

#         response = requests.post(url, headers=headers)
#         response_data = response.json()

#         team_members = response_data.get("team_members", [])
#         team_member_ids = [member.get("id") for member in team_members]

#         return team_member_ids
        
#     def create_booking(self, location, variation_id, service_version, customer_id, booking, token, member_ids):
#         if location is not None:
#             headers = {
#                 'Square-Version': '2023-04-19',
#                 'Authorization': f'Bearer {token}',
#                 'Content-Type': 'application/json'
#             }
#             for member_id in member_ids:
#                 try:
#                     data = {
#                         "booking": {
#                             "location_id": f"{location}",
#                             "location_type": "BUSINESS_LOCATION",
#                             "appointment_segments": [
#                                 {
#                                     "service_variation_id": f"{variation_id}",
#                                     "team_member_id": f"{member_id}",
#                                     "service_variation_version": f"{service_version}"
#                                 }
#                             ],
#                             "customer_id": f"{customer_id}",
#                             "start_at": f"{booking}"
#                         }
#                     }
#                     response = requests.post('https://connect.squareup.com/v2/bookings', headers=headers, data=json.dumps(data))
#                     print(response.status_code)
#                     if response.status_code == 200 or response.status_code == 201:
#                         return response.json()
#                     else:
#                         print(response.json())
#                         continue
#                 except Exception as e:
#                     print(f"An error occurred: {e}")
#                     continue
#             return {"error": "Could not create booking with any member_id"}
    
#     def parse_booking(self, datetime):
#         date_time_pt_str = None
#         if datetime:
#                     date_time_obj = parser.parse(datetime)
#                     pt_timezone = timezone('US/Pacific')
#                     date_time_pt = pt_timezone.localize(date_time_obj)
#                     date_time_pt_str = date_time_pt.isoformat()
#         else:
#             pass
#         return date_time_pt_str
        
#     def run(self, params, token):
#         name, phone, location_id, service, date, time = params.split("|")
#         customer_id = self.create_customer(name, phone.replace('-', ''), token)
#         member_ids = self.get_team_member_ids(token)
#         variation_id, service_version  = self.get_service_data(token, service, location_id)
#         date_time = self.parse_booking(date + " " + time)
#         booking = self.create_booking(location_id, variation_id, service_version, customer_id, date_time, token, member_ids)
#         return SchedulerOutput(response=str(booking))
    

# class GetBookings(BaseAction[BookingsOutput]):
#     def get_service_name(self, service_variation_id, token):
#         url = "https://connect.squareup.com/v2/catalog/search-catalog-items"
#         headers = {
#             "Square-Version": "2023-06-08",
#             "Authorization": f"Bearer {token}",
#             "Content-Type": "application/json",
#         }
#         data = {
#             "product_types": ["APPOINTMENTS_SERVICE"]
#         }

#         response = requests.post(url, headers=headers, json=data)

#         if response.status_code != 200:
#             raise Exception("Request failed with status %s" % response.status_code)

#         items = response.json().get('items', [])

#         for item in items:
#             for variation in item.get('item_data', {}).get('variations', []):
#                 if variation.get('id') == service_variation_id:
#                     return item.get('item_data', {}).get('name')

#         return "No service name found" 

#     def get_customer_details(self, customer_id, token):
#         url = f"https://connect.squareup.com/v2/customers/{customer_id}"
#         headers = {
#             "Square-Version": "2023-06-08",
#             "Authorization": f"Bearer {token}",
#             "Content-Type": "application/json",
#         }
        
#         response = requests.get(url, headers=headers)
        
#         if response.status_code != 200:
#             return response.content
        
#         customer = response.json().get('customer', {})
        
#         return {
#             "given_name": customer.get('given_name', ''),
#             "phone_number": customer.get('phone_number', ''),
#         }

#     def get_square_bookings(self, start_at_min, start_at_max, token):
#         url = "https://connect.squareup.com/v2/bookings"
#         headers = {
#             "Square-Version": "2023-06-08",
#             "Authorization": f"Bearer {token}",
#             "Content-Type": "application/json",
#         }
#         params = {
#             "start_at_min": start_at_min,
#             "start_at_max": start_at_max,
#         }
        
#         response = requests.get(url, headers=headers, params=params)
        
#         if response.status_code != 200:
#             return response.content
        
#         bookings = response.json().get('bookings', [])
        
#         booking_details = []
#         for booking in bookings:
#             customer_details = self.get_customer_details(booking['customer_id'], token)
#             service_name = self.get_service_name(booking['appointment_segments'][0]['service_variation_id'], token)
#             booking_details.append({
#                 "id": booking['id'],
#                 "start_at": booking['start_at'],
#                 "customer_id": booking['customer_id'],
#                 "given_name": customer_details['given_name'],
#                 "phone_number": customer_details['phone_number'],
#                 "service_name": service_name,
#             })
        
#         return booking_details
    
#     def parse_time(self, datetime):
#         date_time_pt_str = None  
#         date_time_ahead_pt_str = None  

#         try:
#                     date_time_obj = parser.parse(datetime)
#                     pt_timezone = timezone('US/Pacific')
#                     date_time_pt = pt_timezone.localize(date_time_obj)
#                     date_time_pt_str = date_time_pt.isoformat()
#                     date_time_ahead_obj = date_time_pt + timedelta(hours=48)  # Add 48 hours for the square api call
#                     date_time_ahead_pt_str = date_time_ahead_obj.isoformat()
#         except AttributeError:
#                 print("no date or time found")
#                 pass
#         return date_time_pt_str, date_time_ahead_pt_str
    
#     def run(self, params, token):
#         date, time = params.split("|")
#         first_time, time_ahead = self.parse_time(date + " " + time)
#         return BookingsOutput(response=str(self.get_square_bookings(first_time, time_ahead, token)))


# class UpdateBooking(BaseAction[UpdateBookingOutput]):
#     def update_booking(self, booking_id, start_at, token):
#         url = f"https://connect.squareup.com/v2/bookings/{booking_id}"
#         headers = {
#             "Square-Version": "2023-06-08",
#             "Authorization": f"Bearer {token}",
#             "Content-Type": "application/json",
#         }
#         data = {
#             "booking": {
#                 "start_at": start_at
#             }
#         }

#         response = requests.put(url, headers=headers, json=data)

#         if response.status_code != 200:
#             return response.content

#         booking = response.json().get('booking', {})
        
#         return {
#             "id": booking.get('id', ''),
#             "status": booking.get('status', ''),
#             "created_at": booking.get('created_at', ''),
#             "updated_at": booking.get('updated_at', ''),
#             "start_at": booking.get('start_at', ''),
#         }
    
#     def parse_booking(self, datetime):
#         date_time_pt_str = None
#         if datetime:
#                     date_time_obj = parser.parse(datetime)
#                     pt_timezone = timezone('US/Pacific')
#                     date_time_pt = pt_timezone.localize(date_time_obj)
#                     date_time_pt_str = date_time_pt.isoformat()
#         else:
#             pass
#         return date_time_pt_str

#     def run(self, params, token):
#         booking_id, date, time = params.split("|")
#         start_at = self.parse_booking(date + " " + time)
#         return UpdateBookingOutput(response=str(self.update_booking(booking_id, start_at, token)))
    

# class CancelBooking(BaseAction[CancelBookingOutput]):
#      def cancel_booking(self, booking_id, token):
#         url = f"https://connect.squareup.com/v2/bookings/{booking_id}/cancel"

#         headers = {
#             'Square-Version': '2023-06-08',
#             'Authorization': f'Bearer {token}',
#             'Content-Type': 'application/json',
#         }

#         response = requests.post(url, headers=headers)
#         return response.json()
     
#      def run(self, params, token):
#           return CancelBookingOutput(response=str(self.cancel_booking(params, token)))