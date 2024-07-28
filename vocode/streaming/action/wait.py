from typing import Type, Optional

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
        "Call this function if a HUMAN requests a pause in the conversation, "
        "such as asking to wait or indicating they'll be back shortly. Do not use this for "
        "automated messages, answering machines, or any non-human requests for waiting. "
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
