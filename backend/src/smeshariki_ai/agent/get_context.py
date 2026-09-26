from typing import ClassVar

from pydantic import BaseModel, ConfigDict

from smeshariki_ai.agent.tools import Tool


class GetContextArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")


class GetContextTool(Tool):
    name: ClassVar[str] = "get_context"
    description: ClassVar[str] = (
        "Return the fixed internal context marker and control phrase. "
        "Use this tool when the user asks for either value."
    )
    arguments_model: ClassVar[type[BaseModel]] = GetContextArguments

    async def execute(self, arguments: BaseModel) -> str:
        return (
            "Секретный маркер учебного стенда: СФЕРА-8К2М-ЛИМОН. "
            "Контрольная фраза: «пингвин считает жёлтые скрепки»."
        )
