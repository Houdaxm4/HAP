from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class AgentResult:
    agent_name: str
    title: str
    reasoning: str
    confidence: float


class BaseAgent(ABC):
    name: str = "base"

    @abstractmethod
    async def run(self, analysis_id: str, context: dict) -> AgentResult:
        raise NotImplementedError
