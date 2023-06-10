import logging
from typing import Generic, Optional, TypeVar
from vocode.streaming.models.actions import ActionOutput, ActionType, AvailabilityOutput, SchedulerOutput
import requests
import re
from dateutil import parser
from datetime import timedelta
from pytz import timezone
import json


ActionOutputType = TypeVar("ActionOutputType", bound=ActionOutput)

class BaseAction(Generic[ActionOutputType]):
    def run(self, params: str) -> ActionOutputType:
        raise NotImplementedError

class GetAvailability(BaseAction[AvailabilityOutput]):
    def get_location_and_variation_id(self, availability_check, token):
        try:
            url = "https://connect.squareup.com/v2/catalog/list"
            headers = {
                "Square-Version": "2023-04-19",
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json"
            }
            response = requests.get(url, headers=headers)
            target_item_name = f"{availability_check['service']}"
            if response.status_code == 200:
                data = response.json()
                for item in data['objects']:
                    if item['type'] == 'ITEM' and item['item_data']['name'] == target_item_name:
                        location = item['present_at_location_ids']
                        for variation in item['item_data']['variations']:
                            variation_id = variation['id']
                        return location, variation_id
                else:
                    print("Target item not found in Square catalog.")
                    return None, None
            else:
                print("Request failed with status code:", response.status_code)
                return None, None
        except NameError:
            print("Variable 'availability_check' not defined.")
            return None, None
        
    def get_availability(self, location, variation_id, availability_check, token):
        if location is None or variation_id is None:
            print("Error: Location or variation ID is None.")
            return

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
                        "end_at": f"{availability_check['av_ahead']}",
                        "start_at": f"{availability_check['av_first']}"
                    },
                    "location_id": f"{location[0]}",
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
        
    def run(self, params, token):
        services, date, time = params.split("|")
        av_first, av_ahead = self.parse_availability(date + " " + time)
        availability_check = {'service': services.capitalize(), 'av_first': av_first, 'av_ahead': av_ahead}
        location, variation_id = self.get_location_and_variation_id(availability_check, token)
        availability = self.get_availability(location, variation_id, availability_check, token)
        return AvailabilityOutput(response=str(availability))
    

class Scheduler(BaseAction[SchedulerOutput]):
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

    def get_location_sversion_and_variation_id(self, service, token):
        try:
            url = "https://connect.squareup.com/v2/catalog/list"
            headers = {
                "Square-Version": "2023-04-19",
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json"
            }
            response = requests.get(url, headers=headers)
            target_item_name = f"{service}"
            if response.status_code == 200:
                data = response.json()
                for item in data['objects']:
                    if item['type'] == 'ITEM' and item['item_data']['name'] == target_item_name:
                        location = item['present_at_location_ids']
                        for variation in item['item_data']['variations']:
                            variation_id = variation['id']
                            service_version = variation['version']
                        return location, variation_id, service_version
                else:
                    print("Target item not found in Square catalog.")
                    return None, None, None
            else:
                print("Request failed with status code:", response.status_code)
                return None, None, None
        except NameError:
            print("Variable 'availability_check' not defined.")
            return None, None, None
        
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
                            "location_id": f"{location[0]}",
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
    
    def parse_booking(self, datetime):
        date_time_pt_str = None
        if datetime:
                    date_time_obj = parser.parse(datetime)
                    pt_timezone = timezone('US/Pacific')
                    date_time_pt = pt_timezone.localize(date_time_obj)
                    date_time_pt_str = date_time_pt.isoformat()
        else:
            pass
        return date_time_pt_str
        
    def run(self, params, token):
        name, phone, service, date, time = params.split("|")
        customer_id = self.create_customer(name, phone.replace('-', ''), token)
        member_ids = self.get_team_member_ids(token)
        location, variation_id, service_version,  = self.get_location_sversion_and_variation_id(service, token)
        date_time = self.parse_booking(date + " " + time)
        booking = self.create_booking(location, variation_id, service_version, customer_id, date_time, token, member_ids)
        return SchedulerOutput(response=str(booking))
