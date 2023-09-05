from typing import Optional, Type
from pydantic import BaseModel, Field
import os
from vocode.streaming.action.base_action import BaseAction
from vocode.streaming.models.actions import (
    ActionConfig,
    ActionInput,
    ActionOutput,
    ActionType,
)

import json
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
import base64
import datetime as mdate
from email.mime.text import MIMEText
from pytz import timezone
from email.mime.multipart import MIMEMultipart
import psycopg2
from psycopg2 import sql


class GoogleSendEmailActionConfig(ActionConfig, type="google_email"):
    pass

class GoogleSendEmailParameters(BaseModel):
    message: str = Field(..., description="The body of the email.")
    recipient_email: Optional[str] = Field(None, description="The email address of the recipient.")
    subject: Optional[str] = Field(None, description="The subject of the email.")
    from_email: Optional[str] = Field(None, description="The email address of the sender.")


class GoogleSendEmailResponse(BaseModel):
    response: str

class GoogleSendEmail(
    BaseAction[
        GoogleSendEmailActionConfig, GoogleSendEmailParameters, GoogleSendEmailResponse
    ]
):
    description: str = "Sends an email using Google API."
    parameters_type: Type[GoogleSendEmailParameters] = GoogleSendEmailParameters
    response_type: Type[GoogleSendEmailResponse] = GoogleSendEmailResponse

    def sendMessage(self, message, to_email, from_email):
        creds = Credentials.from_authorized_user_file('google_mail_token.json')
        service = build('gmail', 'v1', credentials=creds)

        messageText="""\
            <html>
            <head>
            <style>
            table, th, td {
                border: 1px solid black;
                border-collapse: collapse;
            }
            </style>
            </head>
            <body>
            """+message+"""
            </body>
            </html>
            """


        # Send a message
        n = mdate.datetime.now(mdate.timezone.utc)
        date = n.astimezone(timezone('US/Pacific'))
        date = f"{date.day}/{date.month}/{date.year}"
        message = MIMEMultipart()
        message['to'] = f'{to_email}'
        message['from'] = f'{from_email}'
        message['subject'] = f'Phone call message - {date}'

        # Attach the body to the message
        message.attach(MIMEText(messageText, 'html'))

        raw_message = base64.urlsafe_b64encode(message.as_bytes())
        raw_message = raw_message.decode()
        body = {'raw': raw_message}
        message = service.users().messages().send(userId='me', body=body).execute()

    async def run(
        self, action_input: ActionInput[GoogleSendEmailParameters]
    ) -> ActionOutput[GoogleSendEmailResponse]:

        email = self.sendMessage(action_input.params.message, action_input.params.recipient_email, action_input.params.from_email)

        return ActionOutput(
            action_type=self.action_config.type,
            response=GoogleSendEmailResponse(response=str(email)),
        )
    
class MessageTakingActionConfig(ActionConfig, type="take_message"):
    pass

class MessageTakingParameters(BaseModel):
    message: str = Field(..., description="The message to record.")
    contact_info: str = Field(..., description="Caller's contact information, either an email or phone number.")
    id: Optional[str] =  Field(None, description="Business ID")

class MessageTakingResponse(BaseModel):
    response: str

class MessageTaking(
    BaseAction[
        MessageTakingActionConfig, MessageTakingParameters, MessageTakingResponse
    ]
):
    description: str = "Takes a message for later review by the company or owner."
    parameters_type: Type[MessageTakingParameters] = MessageTakingParameters
    response_type: Type[MessageTakingResponse] = MessageTakingResponse

    def sendMessage(self, message, contact, id):
        url = os.getenv('POSTGRES_URL')
        conn = psycopg2.connect(url)

        message_text = f"Message recorded by Folks:\n{message}\nContact details provided by caller: {contact}"

        try:
            with conn.cursor() as cur:
                cur.execute(sql.SQL(
                    """
                    SELECT folks_phone_number FROM public.businesses
                    WHERE id = %s
                    LIMIT 1
                    """),
                    (id,)  
                )
                phone_number = cur.fetchone()

                if phone_number:
                    phone_number = phone_number[0]
                    cur.execute(sql.SQL(
                        """
                        UPDATE public.calls
                        SET message = %s
                        WHERE phone_number = %s
                        """), 
                        (message_text, phone_number)
                    )
                else:
                    return f"No business found with id: {id}"

            conn.commit()
            conn.close()
            return "Successfully sent message."

        except Exception as e:
            conn.rollback()
            return f"Failed to insert data into database: {e}"

    async def run(
        self, action_input: ActionInput[MessageTakingParameters]
    ) -> ActionOutput[MessageTakingResponse]:

        email = self.sendMessage(action_input.params.message, action_input.params.contact_info, action_input.params.id)

        return ActionOutput(
            action_type=self.action_config.type,
            response=MessageTakingResponse(response=str(email)),
        )