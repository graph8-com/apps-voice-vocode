import asyncio
import json
import logging
from typing import List, Optional
import re
import typing
import openai
import copy
import random
import os
import psycopg2

from vocode import getenv
from vocode.streaming.action.factory import ActionFactory
from vocode.streaming.action.nylas_send_email import NylasSendEmail
from vocode.streaming.action.phone_call_action import (
    TwilioPhoneCallAction,
    VonagePhoneCallAction,
)
from vocode.streaming.agent.base_agent import (
    ActionResultAgentInput,
    AgentInput,
    AgentInputType,
    AgentResponseFillerAudio,
    AgentResponseMessage,
    BaseAgent,
    TranscriptionAgentInput,
)
from vocode.streaming.agent.prompts.action_prompt import SYSTEM_MESSAGE, CHRONO_MESSAGE
from vocode.streaming.agent.utils import (
    format_openai_chat_messages_from_transcript,
    stream_openai_response_async,
)
from vocode.streaming.models.actions import ActionInput
from vocode.streaming.models.agent import ActionAgentConfig
from vocode.streaming.models.message import BaseMessage
from vocode.streaming.utils.worker import InterruptibleEvent

import datetime
from pytz import timezone

filler_phrases = ["One sec.",  "One moment.",  "Just a moment.",  "Just a moment please.",  "Ok, one sec.",  "Ok, just a sec.",  
                  "Ok, one moment.",  "Ok, let me check.",  "Ok, um... one sec.",  "Ok, just a moment.",  "Ok, um... one moment.",  
                  "Ok, one moment please.",  "Sure, one sec.",  "Sure, just a sec.",  "Sure, one moment.",  "Sure, let me check.",  
                  "Sure, um... one sec.",  "Sure, just a moment.",  "Sure, um... one moment.",  "Sure, one moment please.",  "Alright! One sec.",  
                  "Alright! Just a sec.",  "Alright! One moment.",  "Alright! Um... one sec.",  "Alright! Just a moment.",  
                  "Alright! Um... one moment.",  "Alright! One moment please."]

class ActionAgent(BaseAgent[ActionAgentConfig]):
    def __init__(
        self,
        agent_config: ActionAgentConfig,
        action_factory: ActionFactory = ActionFactory(),
        logger: Optional[logging.Logger] = None,
    ):
        super().__init__(agent_config, logger=logger)
        self.agent_config = agent_config
        self.action_factory = action_factory
        self.actions_queue: asyncio.Queue[
            InterruptibleEvent[ActionInput]
        ] = asyncio.Queue()

        openai.api_key = getenv("OPENAI_API_KEY")
        if not openai.api_key:
            raise ValueError("OPENAI_API_KEY must be set in environment or passed in")
        self.functions = self.get_functions()
        self.locations = agent_config.locations
        self.company = agent_config.company
        self.token = agent_config.token
        self.timezone = agent_config.timezone
        self.date = self.get_current_time()
        self.availabilities = None
        self.provider = agent_config.provider

    async def load_availabilities(self):
        self.availabilities = json.loads(await self.agent_config.cache.get(str(self.agent_config.id+"_availabilities")))

    def get_current_time(self):
        try:
            date = ((datetime.datetime.now(datetime.timezone.utc)).astimezone(timezone(self.timezone))).isoformat()
            return date
        except Exception:
            date = ((datetime.datetime.now(datetime.timezone.utc)).astimezone(timezone('UTC'))).isoformat()
            return date
        
    def get_prompt(self):
        prompt = SYSTEM_MESSAGE.format(locations=(self.locations[0][0], self.locations[0][2]['business_hours']), company=self.company, date=f"{self.date}", timezone=self.timezone, availabilities=self.availabilities) if self.provider == "square" else CHRONO_MESSAGE.format(locations=self.locations, company=self.company, date=f"{self.date}", timezone=self.timezone, availabilities=self.availabilities)
        return prompt

    async def process(self, item: InterruptibleEvent[AgentInput]):
        await self.load_availabilities()
        assert self.transcript is not None
        try:
            self.logger.debug("Responding to transcription")
            agent_input = item.payload
            if isinstance(agent_input, TranscriptionAgentInput):
                self.transcript.add_human_message(
                    text=agent_input.transcription.message,
                    conversation_id=agent_input.conversation_id,
                )
            elif isinstance(agent_input, ActionResultAgentInput):
                self.logger.debug(f"Action output: {agent_input.action_output}")
                self.transcript.add_action_finish_log(
                    action_output=agent_input.action_output,
                    conversation_id=agent_input.conversation_id,
                )
                if agent_input.is_quiet:
                    # Do not generate a response to quiet actions
                    self.logger.debug("Action is quiet, skipping response generation")
                    return
            else:
                raise ValueError("Invalid AgentInput type")
            
            if self.agent_config.send_filler_audio:
                self.produce_interruptible_event_nonblocking(AgentResponseFillerAudio())
            self.logger.debug("Responding to transcription")

            messages = format_openai_chat_messages_from_transcript(
                self.transcript, self.get_prompt()
            )
            self.logger.debug(f"PROMPT\n{messages}")
            openai_response = await openai.ChatCompletion.acreate(
                model=self.agent_config.model_name,
                messages=messages,
                functions=self.functions,
                max_tokens=self.agent_config.max_tokens,
                temperature=self.agent_config.temperature,
            )
            if len(openai_response.choices) == 0:
                raise ValueError("OpenAI returned no choices")
            message = openai_response.choices[0].message
            if message.content:
                self.produce_interruptible_event_nonblocking(
                    AgentResponseMessage(message=BaseMessage(text=message.content))
                )
            elif message.function_call:
                action = self.action_factory.create_action(message.function_call.name)
                params = json.loads(message.function_call.arguments)
                params["token"] = self.token
                params["timezone"] = self.timezone
                params["location_id"] = self.locations[0][1]['id']
                if "user_message" in params:
                    user_message = params["user_message"]
                    self.produce_interruptible_event_nonblocking(
                        AgentResponseMessage(message=BaseMessage(text=user_message))
                    )
                elif "user_message" not in params:
                    user_message = random.choice(filler_phrases)
                    self.produce_interruptible_event_nonblocking(
                        AgentResponseMessage(message=BaseMessage(text=user_message))
                    )
                    # if self.agent_config.send_filler_audio:
                    #     self.produce_interruptible_event_nonblocking(AgentResponseFillerAudio())
                    #     self.logger.debug("Responding to transcription")
                action_input: ActionInput
                if isinstance(action, VonagePhoneCallAction):
                    assert (
                        agent_input.vonage_uuid is not None
                    ), "Cannot use VonagePhoneCallActionFactory unless the attached conversation is a VonageCall"
                    action_input = action.create_phone_call_action_input(
                        message.function_call.name, params, agent_input.vonage_uuid
                    )
                elif isinstance(action, TwilioPhoneCallAction):
                    assert (
                        agent_input.twilio_sid is not None
                    ), "Cannot use TwilioPhoneCallActionFactory unless the attached conversation is a TwilioCall"
                    action_input = action.create_phone_call_action_input(
                        message.function_call.name, params, agent_input.twilio_sid
                    )
                else:
                    action_input = action.create_action_input(
                        agent_input.conversation_id,
                        params,
                    )
                event = self.interruptible_event_factory.create(action_input)
                transcript_action = copy.deepcopy(action_input); transcript_action.params.token = ""
                self.logger.debug(f"Action input parameters: {transcript_action.params}")
                self.transcript.add_action_start_log(
                    action_input=transcript_action,
                    conversation_id=agent_input.conversation_id,
                )
                self.actions_queue.put_nowait(event)
        except asyncio.CancelledError:
            pass

    def get_functions(self):
        return [
            self.action_factory.create_action(action_type).get_openai_function()
            for action_type in self.agent_config.actions
        ]
