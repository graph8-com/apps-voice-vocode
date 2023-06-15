import asyncio
import logging
from typing import List, Optional
import re
import typing
import openai

from vocode import getenv
from vocode.streaming.action.factory import ActionFactory
from vocode.streaming.action.nylas_send_email import NylasSendEmail
from vocode.streaming.agent.base_agent import (
    ActionResultAgentInput,
    AgentInput,
    AgentInputType,
    AgentResponseFillerAudio,
    AgentResponseMessage,
    BaseAgent,
    TranscriptionAgentInput,
)

from vocode.streaming.agent.utils import (
    format_openai_chat_messages_from_transcript,
    stream_openai_response_async,
)
from vocode.streaming.models.agent import ActionAgentConfig, FolksActionAgentConfig
from vocode.streaming.models.actions import ActionInput
from vocode.streaming.agent.action_agent import ActionAgent
from vocode.streaming.models.message import BaseMessage
from vocode.streaming.utils.worker import InterruptibleEvent
from enum import Enum
from vocode.streaming.models.model import BaseModel
import datetime
from pytz import timezone

from vocode.streaming.agent.prompts.action_prompt import PROMPT, SYSTEM_MESSAGE
#from agents.action_types import FolksActionAgentConfig, FolksActionInput, ActionInput

n = datetime.datetime.now(datetime.timezone.utc)
date = n.astimezone(timezone('US/Pacific'))
date_iso = date.isoformat()


class FolksActionAgent(BaseAgent[FolksActionAgentConfig]):
    def __init__(
        self,
        agent_config: FolksActionAgentConfig,
        action_factory: ActionFactory = ActionFactory(),
        logger: Optional[logging.Logger] = logging.getLogger(__name__),
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
        self.locations = agent_config.locations
        self.company = agent_config.company
        self.token = agent_config.token
        for action_type in agent_config.actions:
            action = self.action_factory.create_action(action_type)
    
    def get_locations_names(self, locations):
        names = []
        for i in locations:
            for k, v in i.items():
                names.append(k)
        return names
    
    def search_location_id(self, locations, key):
        for dictionary in locations:
            if key in dictionary:
                return dictionary[key]
        return "ID not found"

    def _create_prompt(self):
        assert self.transcript is not None
        return PROMPT.format(
            company=self.company, locations=self.get_locations_names(self.locations), date=f"{date_iso}", transcript=self.transcript.to_string(include_timestamps=False), 
        )

    async def process(self, item: InterruptibleEvent[AgentInput]):
        assert self.transcript is not None
        try:
            agent_input = item.payload
            if isinstance(agent_input, TranscriptionAgentInput):
                self.transcript.add_human_message(
                    text=agent_input.transcription.message,
                    conversation_id=agent_input.conversation_id,
                )
            elif isinstance(agent_input, ActionResultAgentInput):
                self.transcript.add_action_log(
                    action_output=agent_input.action_output,
                    conversation_id=agent_input.conversation_id,
                )
            else:
                raise ValueError("Invalid AgentInput type")

            messages = [{"role": "system", "content": SYSTEM_MESSAGE.format(company=self.company)},
                        {"role": "system", "content": self._create_prompt()}]
            print(self._create_prompt())
            openai_response = await openai.ChatCompletion.acreate(
                model="gpt-4",
                messages=messages,
                max_tokens=500,
                temperature=0.0,
                stream=True,
            )
            verbose_response = ""
            async for message in stream_openai_response_async(
                openai_response,
                get_text=lambda choice: choice.get("delta", {}).get("content"),
                sentence_endings=["\n"],
            ):
                maybe_response = self.extract_response(message)
                if maybe_response:
                    self.produce_interruptible_event_nonblocking(
                        AgentResponseMessage(message=BaseMessage(text=maybe_response))
                    )
                verbose_response += f"{message}\n"
            for action_input in self.get_action_inputs(
                verbose_response, agent_input.conversation_id
            ):
                event = self.interruptible_event_factory.create(action_input)
                self.actions_queue.put_nowait(event)
        except asyncio.CancelledError as e:
            print(f"{e}")
            pass

    def extract_action(self, response: str):
        match = re.search(r"Action:\s*(.*)", response)
        return match.group(1).strip() if match else None

    def extract_parameters(self, response: str):
        match = re.search(r"Action parameters:\s*(.*)", response)
        return match.group(1).strip() if match else ""

    def extract_response(self, response: str):
        match = re.search(r"Response:\s*(.*)", response)
        return match.group(1).strip() if match else ""
    
    def add_location_id(self, extracted_params):
            for location in self.get_locations_names(self.locations):
                if extracted_params == location:
                    extracted_params = self.search_location_id(self.locations, location)
                    return extracted_params
            return extracted_params

    def get_action_inputs(
        self, response: str, conversation_id: str
    ) -> List[ActionInput]:
        extracted_action = self.extract_action(response)
        extracted_parameters = self.extract_parameters(response)
        if extracted_action == "get_services":
            extracted_parameters = self.add_location_id(extracted_parameters)
        if extracted_action == "check_availability":
            location_name, service, date, time = extracted_parameters.split("|")
            location_id = self.add_location_id(location_name)
            extracted_parameters = extracted_parameters.replace(location_name, location_id)
        if extracted_action == "book_appointment":
            name, phone, location_name, service, date, time = extracted_parameters.split("|")
            location_id = self.add_location_id(location_name)
            extracted_parameters = extracted_parameters.replace(location_name, location_id)
        
        action_inputs = []
        for action_type in self.agent_config.actions:
            if action_type.value == extracted_action:
                action_inputs.append(
                    ActionInput(
                        action_type=action_type,
                        params=extracted_parameters,
                        conversation_id=conversation_id,
                        token=self.token,
                    )
                )
        return action_inputs