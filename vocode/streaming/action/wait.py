from typing import Type

from pydantic.v1 import BaseModel, Field

from vocode.streaming.action.base_action import BaseAction
from vocode.streaming.models.actions import ActionConfig as VocodeActionConfig
from vocode.streaming.models.actions import ActionInput, ActionOutput


class WaitVocodeActionConfig(VocodeActionConfig, type="action_wait"):  # type: ignore
    seconds: int = Field(default=30, description="Number of seconds to wait for.")


class WaitParameters(BaseModel):
    pass


class WaitOutput(BaseModel):
    success: bool


class WaitResponse(BaseModel):
    seconds: int


class Wait(
    BaseAction[
        WaitVocodeActionConfig,
        WaitParameters,
        WaitOutput,
    ]
):
    description: str = (
    "Instantly trigger this function if a user indicates a need to pause. "
    "This includes ALL expressions about waiting, pausing, or getting someone else involved, such as: "
    "1. Pause requests: 'be right back', 'just a second', 'could you give me a moment?', 'let me move to a quieter place'\n"
    "2. Involving others: 'let me get him on the phone', 'let me ask my manager'\n"
    "CRITICAL: NEVER generate ANY verbal message before calling this function. ALWAYS call this function silently, adding a polite "
    "acknowledgment in the `user_message` parameter of this function. "
    "This function handles ALL such requests made by humans. Never answer such requests conversationally. "
    "Do not use this for automated messages or answering machines. "
    )
    parameters_type: Type[WaitParameters] = WaitParameters
    response_type: Type[WaitOutput] = WaitOutput

    def __init__(
        self,
        action_config: WaitVocodeActionConfig,
    ):
        super().__init__(
            action_config,
            quiet=True,
            should_respond="always",
        )

    async def run(self, action_input: ActionInput[WaitParameters]) -> ActionOutput[WaitOutput]:
        if action_input.user_message_tracker is not None:
            await action_input.user_message_tracker.wait()

        return ActionOutput(
            action_type=action_input.action_config.type,
            response=WaitOutput(success=True),
        )
