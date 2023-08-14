import logging

from typing import Any, Dict, List, Optional, Tuple, Union

import openai
from typing import AsyncGenerator, Optional, Tuple

import logging
from pydantic import BaseModel
import copy

from vocode import getenv
from vocode.streaming.action.factory import ActionFactory
from vocode.streaming.agent.base_agent import RespondAgent
from vocode.streaming.models.actions import FunctionCall, FunctionFragment
from vocode.streaming.models.agent import ChatGPTAgentConfig
from vocode.streaming.agent.utils import (
    format_openai_chat_messages_from_transcript,
    collate_response_async,
    openai_get_tokens,
    vector_db_result_to_openai_chat_message,
)
from vocode.streaming.models.events import Sender
from vocode.streaming.models.transcript import Transcript
from vocode.streaming.vector_db.factory import VectorDBFactory
from vocode.streaming.action.factory import ActionFactory
from vocode.streaming.action.phone_call_action import TwilioPhoneCallAction, VonagePhoneCallAction
from vocode.streaming.models.actions import ActionInput, FunctionCall, ActionConfig
from vocode.streaming.models.message import BaseMessage
from vocode.streaming.models.transcript import Transcript
from vocode.streaming.utils.worker import InterruptibleEvent
import asyncio
import json
import logging
import random
from typing import AsyncGenerator, Generator, Generic, Optional, Tuple, TypeVar, Union
import typing
from vocode.streaming.agent.base_agent import AgentInput, AgentInputType, ActionResultAgentInput, AgentResponseStop, AgentResponseFillerAudio, AgentResponseMessage, TranscriptionAgentInput
from vocode.streaming.transcriber.base_transcriber import Transcription
from vocode.streaming.models.agent import (
    ChatGPTAgentConfig,
)

import datetime
from pytz import timezone

filler_phrases = ["One sec.",  "One moment.",  "Just a moment.",  "Just a moment please.",  "Ok, one sec.",  "Ok, just a sec.",  
                  "Ok, one moment.",  "Ok, let me check.",  "Ok, um... one sec.",  "Ok, just a moment.",  "Ok, um... one moment.",  
                  "Ok, one moment please.",  "Sure, one sec.",  "Sure, just a sec.",  "Sure, one moment.",  "Sure, let me check.",  
                  "Sure, um... one sec.",  "Sure, just a moment.",  "Sure, um... one moment.",  "Sure, one moment please.",  "Alright! One sec.",  
                  "Alright! Just a sec.",  "Alright! One moment.",  "Alright! Um... one sec.",  "Alright! Just a moment.",  
                  "Alright! Um... one moment.",  "Alright! One moment please."]


class ChatGPTAgent(RespondAgent[ChatGPTAgentConfig]):
    def __init__(
        self,
        agent_config: ChatGPTAgentConfig,
        action_factory: ActionFactory = ActionFactory(),
        logger: Optional[logging.Logger] = None,
        openai_api_key: Optional[str] = None,
        vector_db_factory=VectorDBFactory(),
    ):
        super().__init__(
            agent_config=agent_config, action_factory=action_factory, logger=logger
        )
        if agent_config.azure_params:
            openai.api_type = "azure"
            openai.api_base = getenv("AZURE_OPENAI_API_BASE")
            openai.api_version = "2023-07-01-preview"
            openai.api_key = getenv("AZURE_OPENAI_API_KEY")
        # else:
        #     openai.api_type = "open_ai"
        #     openai.api_base = "https://api.openai.com/v1"
        #     openai.api_version = None
        #     openai.api_key = openai_api_key or getenv("OPENAI_API_KEY")
        if not openai.api_key:
            raise ValueError("OPENAI_API_KEY must be set in environment or passed in")
        self.first_response = (
            self.create_first_response(agent_config.expected_first_prompt)
            if agent_config.expected_first_prompt
            else None
        )
        self.is_first_response = True

        if self.agent_config.vector_db_config:
            self.vector_db = vector_db_factory.create_vector_db(
                self.agent_config.vector_db_config
            )
        self.locations = agent_config.locations
        self.location_id = agent_config.location_id
        self.company = agent_config.company
        self.token = agent_config.token
        self.timezone = agent_config.timezone
        self.date = self.get_current_time()
        self.availabilities = None
        self.provider = agent_config.provider
        self.system_message = agent_config.prompt_preamble

    def get_current_time(self):
        try:
            date = ((datetime.datetime.now(datetime.timezone.utc)).astimezone(timezone(self.timezone))).isoformat()
            return date
        except Exception:
            date = ((datetime.datetime.now(datetime.timezone.utc)).astimezone(timezone('UTC'))).isoformat()
            return date

    async def load_availabilities(self):
        try:
            self.availabilities = json.loads(await self.agent_config.cache.get(str(self.agent_config.id+"_availabilities")))
        except Exception as e:
            self.logger.debug(f'Redis exception: {e}')
            self.availabilities = "N/A"
            pass

    def get_functions(self):
        assert self.agent_config.actions
        if not self.action_factory:
            return None
        return [
            self.action_factory.create_action(action_config).get_openai_function()
            for action_config in self.agent_config.actions
        ]

    def get_chat_parameters(self, messages: Optional[List] = None):
        assert self.transcript is not None
        messages = messages or format_openai_chat_messages_from_transcript(
            self.transcript, self.system_message.format(locations=self.locations, company=self.company, date=f"{self.date}", timezone=self.timezone, availabilities=self.availabilities)
        )
        self.logger.debug(f"PROMPT\n{messages}")
        parameters: Dict[str, Any] = {
            "messages": messages,
            "max_tokens": self.agent_config.max_tokens,
            "temperature": self.agent_config.temperature,
            "function_call": "auto", 
        }

        if self.agent_config.azure_params is not None:
            parameters["engine"] = self.agent_config.azure_params.engine
        else:
            parameters["model"] = self.agent_config.model_name

        if self.functions:
            parameters["functions"] = self.functions
            #self.logger.debug(f"FUNCTIONS\n{self.functions}")

        return parameters

    def create_first_response(self, first_prompt):
        messages = [
            (
                [{"role": "system", "content": self.system_message.format(locations=self.locations, company=self.company, date=f"{self.date}", timezone=self.timezone, availabilities=self.availabilities)}]
                if self.system_message
                else []
            )
            + [{"role": "user", "content": first_prompt}]
        ]

        parameters = self.get_chat_parameters(messages)
        return openai.ChatCompletion.create(**parameters)

    def attach_transcript(self, transcript: Transcript):
        self.transcript = transcript

    async def process(self, item: InterruptibleEvent[AgentInput]):
        if self.is_muted:
            self.logger.debug("Agent is muted, skipping processing")
            return
        await self.load_availabilities()
        assert self.transcript is not None
        try:
            agent_input = item.payload
            if isinstance(agent_input, TranscriptionAgentInput):
                transcription = typing.cast(
                    TranscriptionAgentInput, agent_input
                ).transcription
                self.transcript.add_human_message(
                    text=transcription.message,
                    conversation_id=agent_input.conversation_id,
                )
            elif isinstance(agent_input, ActionResultAgentInput):
                self.transcript.add_action_finish_log(
                    action_input=agent_input.action_input,
                    action_output=agent_input.action_output,
                    conversation_id=agent_input.conversation_id,
                )
                if agent_input.is_quiet:
                    # Do not generate a response to quiet actions
                    self.logger.debug("Action is quiet, skipping response generation")
                    return
                transcription = Transcription(
                    message=agent_input.action_output.response.json(),
                    confidence=1.0,
                    is_final=True,
                )
            else:
                raise ValueError("Invalid AgentInput type")
            goodbye_detected_task = None
            if self.agent_config.end_conversation_on_goodbye:
                goodbye_detected_task = self.create_goodbye_detection_task(
                    transcription.message
                )
            if self.agent_config.send_filler_audio:
                self.produce_interruptible_agent_response_event_nonblocking(
                    AgentResponseFillerAudio()
                )
            self.logger.debug("Responding to transcription")
            should_stop = False
            if self.agent_config.generate_responses:
                should_stop = await self.handle_generate_response(
                    transcription, agent_input
                )
            else:
                should_stop = await self.handle_respond(
                    transcription, agent_input.conversation_id
                )

            if should_stop:
                self.logger.debug("Agent requested to stop")
                self.produce_interruptible_agent_response_event_nonblocking(
                    AgentResponseStop()
                )
                return
            if goodbye_detected_task:
                try:
                    goodbye_detected = await asyncio.wait_for(
                        goodbye_detected_task, 0.1
                    )
                    if goodbye_detected:
                        self.logger.debug("Goodbye detected, ending conversation")
                        self.produce_interruptible_agent_response_event_nonblocking(
                            AgentResponseStop()
                        )
                        return
                except asyncio.TimeoutError:
                    self.logger.debug("Goodbye detection timed out")
        except asyncio.CancelledError:
            pass

    async def call_function(self, function_call: FunctionCall, agent_input: AgentInput):
        action_config = self._get_action_config(function_call.name)
        if action_config is None:
            self.logger.error(
                f"Function {function_call.name} not found in agent config, skipping"
            )
            return
        action = self.action_factory.create_action(action_config)
        params = json.loads(function_call.arguments)
        params["token"] = self.token
        params["timezone"] = self.timezone
        params["location_id"] = self.location_id
        user_message_tracker = None
        if "user_message" not in params:
            user_message = random.choice(filler_phrases)
            user_message_tracker = asyncio.Event()
            self.produce_interruptible_agent_response_event_nonblocking(
                AgentResponseMessage(message=BaseMessage(text=user_message)),
                agent_response_tracker=user_message_tracker,
            )
        action_input: ActionInput
        if isinstance(action, VonagePhoneCallAction):
            assert (
                agent_input.vonage_uuid is not None
            ), "Cannot use VonagePhoneCallActionFactory unless the attached conversation is a VonageCall"
            action_input = action.create_phone_call_action_input(
                agent_input.conversation_id,
                params,
                agent_input.vonage_uuid,
                user_message_tracker,
            )
        elif isinstance(action, TwilioPhoneCallAction):
            assert (
                agent_input.twilio_sid is not None
            ), "Cannot use TwilioPhoneCallActionFactory unless the attached conversation is a TwilioCall"
            action_input = action.create_phone_call_action_input(
                agent_input.conversation_id,
                params,
                agent_input.twilio_sid,
                user_message_tracker,
            )
        else:
            action_input = action.create_action_input(
                agent_input.conversation_id,
                params,
                user_message_tracker,
            )
        event = self.interruptible_event_factory.create_interruptible_event(
            action_input, is_interruptible=action.is_interruptible
        )
        assert self.transcript is not None
        #transcript_action = copy.deepcopy(action_input); transcript_action.params.token = ""
        self.logger.debug(f"Action input parameters: {action_input.params}")
        self.transcript.add_action_start_log(
            action_input=action_input,
            conversation_id=agent_input.conversation_id,
        )
        self.actions_queue.put_nowait(event)

    async def respond(
        self,
        human_input,
        conversation_id: str,
        is_interrupt: bool = False,
    ) -> Tuple[str, bool]:
        assert self.transcript is not None
        if is_interrupt and self.agent_config.cut_off_response:
            cut_off_response = self.get_cut_off_response()
            return cut_off_response, False
        self.logger.debug("LLM responding to human input")
        if self.is_first_response and self.first_response:
            self.logger.debug("First response is cached")
            self.is_first_response = False
            text = self.first_response
        else:
            chat_parameters = self.get_chat_parameters()
            chat_completion = await openai.ChatCompletion.acreate(**chat_parameters)
            #self.logger.debug(f"Chat completion\n {chat_completion}")
            text = chat_completion.choices[0].message.content
        self.logger.debug(f"LLM response: {text}")
        return text, False
    
    # async def print_values(self, async_gen):
    #     async for value in async_gen:
    #         print("response?", value)


    async def generate_response(
        self,
        human_input: str,
        conversation_id: str,
        is_interrupt: bool = False,
    ) -> AsyncGenerator[Union[str, FunctionCall], None]:
        if is_interrupt and self.agent_config.cut_off_response:
            cut_off_response = self.get_cut_off_response()
            yield cut_off_response
            return
        assert self.transcript is not None

        if self.agent_config.vector_db_config:
            docs_with_scores = await self.vector_db.similarity_search_with_score(
                self.transcript.get_last_user_message()[1]
            )
            docs_with_scores_str = "\n\n".join(
                [
                    "Document: "
                    + doc[0].metadata["source"]
                    + f" (Confidence: {doc[1]})\n"
                    + doc[0].lc_kwargs["page_content"].replace(r"\n", "\n")
                    for doc in docs_with_scores
                ]
            )
            vector_db_result = f"Found {len(docs_with_scores)} similar documents:\n{docs_with_scores_str}"
            messages = format_openai_chat_messages_from_transcript(
                self.transcript, self.agent_config.prompt_preamble
            )
            messages.insert(
                -1, vector_db_result_to_openai_chat_message(vector_db_result)
            )
            chat_parameters = self.get_chat_parameters(messages)
        else:
            chat_parameters = self.get_chat_parameters()
        chat_parameters["stream"] = True
        stream = await openai.ChatCompletion.acreate(**chat_parameters)
        #self.logger.debug(f"Stream\n {stream}")
        #loop = asyncio.get_event_loop()
        #loop.run_until_complete(self.print_values(stream))
        async for message in collate_response_async(
            openai_get_tokens(stream), get_functions=True
        ):
            yield message