import asyncio
import time
from typing import Dict, List, Any, Optional
from .db import db_instance

class InterviewTools:
    def __init__(self, session_id: str):
        self.session_id = session_id
        # In-memory storage for the conversation artifact
        self.conversation_log: List[Dict[str, Any]] = []
        # Event to signal interview termination
        self.termination_event = asyncio.Event()
        # Timer tracking
        self.start_time: Optional[float] = None
        self.is_timer_running: bool = False

    def start_timer(self) -> None:
        """Starts the session timer."""
        self.start_time = time.time()
        self.is_timer_running = True

    def stop_timer(self) -> None:
        """Stops the session timer."""
        self.is_timer_running = False

    def get_elapsed_time(self) -> str:
        """
        Returns the elapsed time since the interview started.
        Format: "Xm Ys" (e.g., "2m 35s")
        """
        if self.start_time is None:
            return "0m 0s"
        
        if not self.is_timer_running:
            return "Timer stopped"
        
        elapsed = time.time() - self.start_time
        minutes = int(elapsed // 60)
        seconds = int(elapsed % 60)
        return f"{minutes}m {seconds}s"

    def update_interview_log(self, role: str, content: str) -> str:
        """
        Appends the latest interaction to the ongoing interview log.
        Call this after every question or answer exchange.
        
        Args:
            role: 'agent' or 'user'
            content: The text content of the message.
        """
        entry = {
            "role": role,
            "content": content,
            "timestamp": self.get_elapsed_time() if self.is_timer_running else None
        }
        self.conversation_log.append(entry)
        return f"Logged {role} message."

    async def submit_interview_session_async(self) -> str:
        """
        Saves the complete interview session to the database.
        Call this ONLY when the interview is finished.
        """
        # Stop the timer when session is saved
        self.stop_timer()
        
        session_data = {
            "session_id": self.session_id,
            "conversation": self.conversation_log,
            "status": "completed"
        }
        try:
            doc_id = await db_instance.save_session_document(session_data)
            return f"Interview session saved with ID: {doc_id}"
        except Exception as e:
            return f"Error saving session: {str(e)}"

    def end_interview(self, summary: str) -> str:
        """
        Signals the end of the interview and terminates the session.
        Call this after providing final feedback and saving the session.
        
        Args:
            summary: A brief summary or closing remarks for the interview.
        """
        # Stop the timer
        self.stop_timer()
        # Set the termination event to signal main.py to close the connection
        self.termination_event.set()
        return f"Interview ended. Summary: {summary}"

