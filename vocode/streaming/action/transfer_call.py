import os
import aiohttp

from aiohttp import BasicAuth
from typing import Type, Optional, Any
from pydantic import BaseModel, Field
from vocode.streaming.action.base_action import BaseAction
from vocode.streaming.models.actions import ActionInput, ActionOutput
from vocode.streaming.action.phone_call_action import TwilioPhoneCallAction


class TransferCallParameters(BaseModel):
    to_phone: int = Field(..., description="phone number to transfer the call to, written as: 1234567890")
    token: Optional[str] = Field(None, description="token for the API call.")
    timezone: Optional[str] = Field(None, description="business' timezone.")
    location_id: Optional[Any] = Field(None, description="business' location ID.")


class TransferCallResponse(BaseModel):
    status: str


class TransferCall(TwilioPhoneCallAction[TransferCallParameters, TransferCallResponse]):
    description: str = "transfers the call. use when you need to connect the active call to a human."
    action_type: str = "transfer_call"
    parameters_type: Type[TransferCallParameters] = TransferCallParameters
    response_type: Type[TransferCallResponse] = TransferCallResponse

    async def transfer_call(self, twilio_call_sid, to_phone):
        twilio_account_sid = os.environ["TWILIO_ACCOUNT_SID"]
        twilio_auth_token = os.environ["TWILIO_AUTH_TOKEN"]

        url = "https://api.twilio.com/2010-04-01/Accounts/{twilio_account_sid}/Calls/{twilio_auth_token}.json".format(
            twilio_account_sid=twilio_account_sid, twilio_auth_token=twilio_call_sid
        )

        twiml_data = "<Response><Dial>{to_phone}</Dial></Response>".format(
            to_phone=to_phone
        )

        payload = {"Twiml": twiml_data}

        auth = BasicAuth(twilio_account_sid, twilio_auth_token)

        async with aiohttp.ClientSession(auth=auth) as session:
            async with session.post(url, data=payload) as response:
                if response.status != 200:
                    print(await response.text())
                    raise Exception("failed to update call")
                else:
                    return await response.json()

    async def run(
        self, action_input: ActionInput[TransferCallParameters]
    ) -> ActionOutput[TransferCallResponse]:
        twilio_call_sid = self.get_twilio_sid(action_input)

        await self.transfer_call(twilio_call_sid, action_input.params.to_phone)

        return ActionOutput(
            action_type=action_input.action_type,
            response=TransferCallResponse(status="success"),
        )