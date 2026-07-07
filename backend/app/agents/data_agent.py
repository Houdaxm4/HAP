from app.agents.base import AgentResult, BaseAgent


class DataAgent(BaseAgent):
    name = "Data Agent"

    async def run(self, analysis_id: str, context: dict) -> AgentResult:
        return AgentResult(
            agent_name=self.name,
            title="SEC filing data ingested",
            reasoning="Pulled latest 10-Q/10-K filings. Pre-announcement estimates excluded per run filter.",
            confidence=0.95,
        )
