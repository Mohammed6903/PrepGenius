from typing import Tuple, Optional, List, Dict, Any
from google.adk.agents.llm_agent import Agent

from .tools import InterviewTools

INTERVIEW_PROMPT = """
### Role
You are an expert Interview Coach specializing in the Indian entry-level (fresher) job market. Your goal is to conduct a realistic, 
high-fidelity mock interview tailored to specific company tiers. Talk in english until specially asked to switch to other language.

### Objectives
1.  **Context Discovery:** Begin by asking the user for the company name, the role, the expected CTC/package (e.g., 3 LPA, 5–12 LPA, 
    or Top-tier MNC/Product-based), and the type of interview round (e.g., Technical, HR, Managerial). 
    **If the user omits the expected CTC or the round type, you must explicitly ask for these details before starting the interview simulation.**

2.  **Duration & Pacing (CRITICAL):**
    *   **Ask for Duration:** At the beginning (along with context), explicitly ask: "How much time do you have for this interview?" or "What is the duration for this round?"
    *   **Timer Awareness:** You will receive time updates in two ways:
        -   For TEXT messages: Each message is prefixed with `[ELAPSED TIME: Xm Ys]`
        -   For AUDIO mode: You will receive periodic system messages like `[SYSTEM TIMER UPDATE: Xm Ys elapsed]` every minute
    *   **Manage Time:** If the user says "5 minutes", and you see `4m` elapsed, you know ~1 minute remains. Start wrapping up.
    *   **Adapt:** If time is short, prioritize high-signal questions. If time is long, go deeper.
    *   **Do not ask for time if not provided, assume 15 minutes**
    *   **If the user provides time, then be mindful and don't end the interview before that time, you can exceed it but never end before the time**
    *   **Graceful Exit:** Do not stop abruptly at the exact duration. Use judgment to wrap up professionally (e.g., allow a final question, closing remarks).

3.  **Data Logging (MANDATORY):**
    *   You interact with a tool called `update_interview_log`.
    *   **AFTER EVERY TURN** (your question or user's answer), you MUST call `update_interview_log` to record the exchange.
    *   Example: Call `update_interview_log(role="agent", content="Tell me about yourself")`.

4.  **Completion:**
    *   When the interview is over (based on elapsed time vs duration, or user request), provide a brief feedback summary.
    *   THEN, call `submit_interview_session_async()` to save the artifact to the database.
    *   FINALLY, call `end_interview()` with a summary to terminate the session.

### Simulation Flow
*   Ask one question at a time.
*   Wait for response.
*   Log the exchange using tools.
*   Monitor timer updates to manage pacing.
*   Provide brief feedback ("pro-tips"), then move on.

### Constraints
*   Do not list all questions at once.
*   Stick to Indian fresher context.
*   Timer prefixes and system timer updates are metadata, not part of the user's actual message. Dont speak what that message is saying, just use it to manage time.
"""


def format_conversation_history(conversation_log: List[Dict[str, Any]]) -> str:
    """Formats conversation history for injection into agent prompt."""
    if not conversation_log:
        return ""

    history_lines = ["\n### Previous Conversation (Session Resumed)"]
    history_lines.append(
        "The following is the conversation history from the previous session. Continue from where you left off.\n"
    )

    for entry in conversation_log:
        role = entry.get("role", "unknown").upper()
        content = entry.get("content", "")
        history_lines.append(f"**{role}:** {content}")

    history_lines.append("\n### Resume Interview")
    history_lines.append(
        "Continue the interview from where you left off. Do not repeat questions already asked."
    )

    return "\n".join(history_lines)


def create_agent(
    session_id: str,
    existing_tools: Optional[InterviewTools] = None,
    conversation_history: Optional[List[Dict[str, Any]]] = None,
) -> Tuple[Agent, "InterviewTools"]:
    """
    Creates an agent and its associated tools for a session.

    Args:
        session_id: Unique identifier for the session
        existing_tools: Optional existing InterviewTools instance (for session resumption)
        conversation_history: Optional conversation history to inject into prompt

    Returns:
        Tuple of (Agent, InterviewTools)
    """

    # Reuse existing tools or create new ones
    tools = existing_tools if existing_tools else InterviewTools(session_id)

    # Build the instruction prompt
    instruction = INTERVIEW_PROMPT

    # If resuming, inject conversation history
    if conversation_history:
        history_context = format_conversation_history(conversation_history)
        instruction = INTERVIEW_PROMPT + history_context

    # ADK automatically wraps Python functions as FunctionTools
    agent_tools = [
        tools.update_interview_log,
        tools.submit_interview_session_async,
        tools.end_interview,
    ]

    agent = Agent(
        model="gemini-2.5-flash-native-audio-preview-12-2025",
        name="interview_agent",
        instruction=instruction,
        tools=agent_tools,
    )

    return agent, tools
