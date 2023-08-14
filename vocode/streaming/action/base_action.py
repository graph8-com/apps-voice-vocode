import asyncio
from typing import Any, Dict, Generic, Optional, Type, TypeVar, TYPE_CHECKING
from vocode.streaming.action.utils import exclude_keys_recursive
from vocode.streaming.models.actions import (
    ActionConfig,
    ActionInput,
    ActionOutput,
    ActionType,
    ParametersType,
    ResponseType,
)

import random

if TYPE_CHECKING:
    from vocode.streaming.utils.state_manager import ConversationStateManager

ActionConfigType = TypeVar("ActionConfigType", bound=ActionConfig)

filler_phrases = ["One sec.",  "One moment.",  "Just a moment.",  "Just a moment please.",  "Ok, one sec.",  "Ok, just a sec.",  
                  "Ok, one moment.",  "Ok, let me check.",  "Ok, um... one sec.",  "Ok, just a moment.",  "Ok, um... one moment.",  
                  "Ok, one moment please.",  "Sure, one sec.",  "Sure, just a sec.",  "Sure, one moment.",  "Sure, let me check.",  
                  "Sure, um... one sec.",  "Sure, just a moment.",  "Sure, um... one moment.",  "Sure, one moment please.",  "Alright! One sec.",  
                  "Alright! Just a sec.",  "Alright! One moment.",  "Alright! Um... one sec.",  "Alright! Just a moment.",  
                  "Alright! Um... one moment.",  "Alright! One moment please."]

class BaseAction(Generic[ActionConfigType, ParametersType, ResponseType]):
    description: str = ""

    def __init__(
        self,
        action_config: ActionConfigType,
        should_respond: bool = True,
        quiet: bool = False,
        is_interruptible: bool = True,
    ):
        self.action_config = action_config
        self.should_respond = should_respond
        self.quiet = quiet
        self.is_interruptible = is_interruptible

    def attach_conversation_state_manager(
        self, conversation_state_manager: "ConversationStateManager"
    ):
        self.conversation_state_manager = conversation_state_manager

    async def run(
        self, action_input: ActionInput[ParametersType]
    ) -> ActionOutput[ResponseType]:
        raise NotImplementedError

    @property
    def parameters_type(self) -> Type[ParametersType]:
        raise NotImplementedError

    @property
    def response_type(self) -> Type[ResponseType]:
        raise NotImplementedError

    def get_openai_function(self):
        parameters_schema = self.parameters_type.schema()
        parameters_schema = exclude_keys_recursive(parameters_schema, {"title"})
        # if self.should_respond:
        #     parameters_schema["properties"][
        #         "user_message"
        #     ] = self._user_message_param_info()
        #     required = parameters_schema.get("required", [])
        #     required.append("user_message")
        #     parameters_schema["required"] = required

        return {
            "name": self.action_config.type,
            "description": self.description,
            "parameters": parameters_schema,
        }

    def create_action_input(
        self,
        conversation_id: str,
        params: Dict[str, Any],
        user_message_tracker: Optional[asyncio.Event] = None,
    ) -> ActionInput[ParametersType]:
        if "user_message" in params:
            del params["user_message"]
        return ActionInput(
            action_config=self.action_config,
            conversation_id=conversation_id,
            params=self.parameters_type(**params),
            user_message_tracker=user_message_tracker,
        )

    def _user_message_param_info(self):
        phrase = random.choice(filler_phrases)
        return {
            "type": "string",
            "description": f"""Say "{phrase}" BEFORE making the function call""",
        }