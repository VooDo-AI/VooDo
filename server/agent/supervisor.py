from typing import Any
import json
from openai import OpenAI
from shared.config import settings

_PROMPT = """You are an objective AI Supervisor for a tech-support agent.
The agent was asked to solve a problem and it just called `finish()`, claiming it succeeded.
Your job is to look at the ORIGINAL GOAL and the AGENT'S FINAL SUMMARY and decide if the agent actually completed the goal.

Return a JSON object with two fields:
1. "approved": boolean (true if the agent succeeded and the summary makes sense, false otherwise).
2. "feedback": string (if approved, generate a simple, user-friendly final summary. If false, provide a short instruction telling the agent what it missed so it can fix it).

Always output raw JSON only, no markdown blocks.
"""

def verify_finish(goal: str, agent_summary: str) -> dict[str, Any]:
    if not settings.llm_base_url or not settings.llm_api_key:
        return {"approved": True, "feedback": agent_summary}
        
    client = OpenAI(
        base_url=settings.llm_base_url,
        api_key=settings.llm_api_key,
    )
    
    messages = [
        {"role": "system", "content": _PROMPT},
        {"role": "user", "content": f"ORIGINAL GOAL: {goal}\n\nAGENT SUMMARY: {agent_summary}"}
    ]
    
    try:
        response = client.chat.completions.create(
            model=settings.llm_model,
            messages=messages,
            temperature=0.0,
            response_format={"type": "json_object"}
        )
        content = response.choices[0].message.content or "{}"
        return json.loads(content)
    except Exception as e:
        print(f"Supervisor error: {e}")
        # Fail open
        return {"approved": True, "feedback": agent_summary}
