from app.agents.base import AgentResult, BaseAgent


class ModelAgent(BaseAgent):
    name = "Model Agent"

    async def run(self, analysis_id: str, context: dict) -> AgentResult:
        return AgentResult(
            agent_name=self.name,
            title="Workbook model updated",
            reasoning="Updated income statement and DCF tabs. Formulas preserved; only input cells modified.",
            confidence=0.88,
        )
