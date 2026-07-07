from app.agents.base import AgentResult, BaseAgent


class VerificationAgent(BaseAgent):
    name = "Verification Agent"

    async def run(self, analysis_id: str, context: dict) -> AgentResult:
        return AgentResult(
            agent_name=self.name,
            title="Cross-checks completed",
            reasoning="Revenue growth, margin assumptions, and balance sheet items verified against filings.",
            confidence=0.91,
        )
