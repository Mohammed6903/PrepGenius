import os
import json
import asyncio
import base64
import warnings

from pathlib import Path
from dotenv import load_dotenv

from google.genai.types import (
    Part,
    Content,
    Blob,
)

from google.adk.runners import InMemoryRunner
from google.adk.agents.live_request_queue import LiveRequestQueue
from google.adk.agents.run_config import RunConfig

from fastapi import FastAPI, WebSocket
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from src.agent import create_agent
from src.tools import InterviewTools

warnings.filterwarnings("ignore", category=UserWarning, module="pydantic")

#
# ADK Streaming
#

# Load Gemini API Key
load_dotenv()

APP_NAME = "ADK Streaming example"


async def start_agent_session(
    user_id: str,
    is_audio: bool = False,
    existing_tools: InterviewTools | None = None,
    conversation_history: list | None = None,
):
    """
    Starts an agent session.

    Args:
        user_id: User identifier
        is_audio: Whether to use audio mode
        existing_tools: Optional existing InterviewTools instance (for resumption)
        conversation_history: Optional conversation history (for resumption)

    Returns:
        Tuple of (live_events, live_request_queue, interview_tools)
    """

    # Create agent (will reuse tools if provided)
    agent, interview_tools = create_agent(
        user_id,
        existing_tools=existing_tools,
        conversation_history=conversation_history,
    )

    # Create a Runner
    runner = InMemoryRunner(
        app_name=APP_NAME,
        agent=agent,
    )

    # Create a Session
    session = await runner.session_service.create_session(
        app_name=APP_NAME,
        user_id=user_id,
    )

    # Set response modality
    modality = "AUDIO" if is_audio else "TEXT"
    run_config = RunConfig(response_modalities=[modality])

    # Create a LiveRequestQueue for this session
    live_request_queue = LiveRequestQueue()

    # Start agent session
    live_events = runner.run_live(
        session=session,
        live_request_queue=live_request_queue,
        run_config=run_config,
    )
    return live_events, live_request_queue, interview_tools


async def agent_to_client_messaging(websocket, live_events):
    """Agent to client communication"""
    while True:
        async for event in live_events:
            # If the turn complete or interrupted, send it
            if event.turn_complete or event.interrupted:
                message = {
                    "turn_complete": event.turn_complete,
                    "interrupted": event.interrupted,
                }
                await websocket.send_text(json.dumps(message))
                print(f"[AGENT TO CLIENT]: {message}")
                continue

            # Read the Content and its first Part
            part: Part = (
                event.content and event.content.parts and event.content.parts[0]
            )
            if not part:
                continue

            # If it's audio, send Base64 encoded audio data
            is_audio = getattr(part, "inline_data", None) and getattr(
                part.inline_data, "mime_type", ""
            ).startswith("audio/pcm")

            if is_audio:
                audio_data = part.inline_data and part.inline_data.data
                if audio_data:
                    message = {
                        "mime_type": "audio/pcm",
                        "data": base64.b64encode(audio_data).decode("ascii"),
                    }
                    await websocket.send_text(json.dumps(message))
                    print(f"[AGENT TO CLIENT]: audio/pcm: {len(audio_data)} bytes.")
                    continue

            # If it's text and a parial text, send it
            if part.text and event.partial:
                message = {"mime_type": "text/plain", "data": part.text}
                await websocket.send_text(json.dumps(message))
                print(f"[AGENT TO CLIENT]: text/plain: {message}")


async def client_to_agent_messaging(
    websocket: WebSocket, live_request_queue, interview_tools
):
    """Client to agent communication with elapsed time injection"""
    try:
        while True:
            # Decode JSON message
            message_json = await websocket.receive_text()
            message = json.loads(message_json)
            mime_type = message["mime_type"]
            data = message["data"]

            # Get elapsed time for logging
            elapsed_time = interview_tools.get_elapsed_time()

            # Send the message to the agent
            if mime_type == "text/plain":
                # Inject elapsed time into text messages
                text_with_timer = f"[ELAPSED TIME: {elapsed_time}]\n{data}"
                content = Content(
                    role="user", parts=[Part.from_text(text=text_with_timer)]
                )
                live_request_queue.send_content(content=content)
                print(f"[CLIENT TO AGENT]: [{elapsed_time}] {data}")
            elif mime_type == "audio/pcm":
                # For audio mode, we cannot inject text - just send the audio
                # The agent will receive timer info when user sends text messages
                decoded_data = base64.b64decode(data)
                live_request_queue.send_realtime(
                    Blob(data=decoded_data, mime_type=mime_type)
                )
                # Only log periodically to avoid spam (every ~1 second worth of audio)
            elif mime_type.startswith("image/"):
                decoded_data = base64.b64decode(data)
                live_request_queue.send_realtime(
                    Blob(data=decoded_data, mime_type=mime_type)
                )
                print(f"[CLIENT TO AGENT]: {mime_type}: {len(decoded_data)} bytes")
            else:
                raise ValueError(f"Mime type not supported: {mime_type}")
    except Exception as e:
        print(f"[CLIENT TO AGENT]: An unexpected error occurred: {e}")


#
# FastAPI web app
#

app = FastAPI()

STATIC_DIR = Path("static")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
async def root():
    """Serves the index.html"""
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))


@app.websocket("/ws/{user_id}")
async def websocket_endpoint(websocket: WebSocket, user_id: int, is_audio: str):
    """Client websocket endpoint with session resumption support"""

    # Wait for client connection
    await websocket.accept()
    print(f"Client #{user_id} connected, audio mode: {is_audio}")

    user_id_str = str(user_id)
    is_audio_mode = is_audio == "true"

    # Initialize tools outside the loop so they persist across restarts
    interview_tools = None
    session_count = 0
    max_sessions = 10  # Safety limit to prevent infinite loops

    while session_count < max_sessions:
        session_count += 1

        try:
            # Start or resume agent session
            if interview_tools is None:
                # First session - create new tools
                print(
                    f"[SESSION]: Starting new session #{session_count} for client #{user_id}"
                )
                (
                    live_events,
                    live_request_queue,
                    interview_tools,
                ) = await start_agent_session(user_id_str, is_audio_mode)
                # Start the interview timer on first session
                interview_tools.start_timer()
                print(f"[TIMER]: Started for client #{user_id}")
            else:
                # Resuming - pass existing tools and conversation history
                print(
                    f"[SESSION]: Resuming session #{session_count} for client #{user_id} with {len(interview_tools.conversation_log)} messages"
                )
                (
                    live_events,
                    live_request_queue,
                    interview_tools,
                ) = await start_agent_session(
                    user_id_str,
                    is_audio_mode,
                    existing_tools=interview_tools,
                    conversation_history=interview_tools.conversation_log,
                )

            # Start tasks
            agent_to_client_task = asyncio.create_task(
                agent_to_client_messaging(websocket, live_events)
            )
            client_to_agent_task = asyncio.create_task(
                client_to_agent_messaging(
                    websocket, live_request_queue, interview_tools
                )
            )

            # Periodic timer task - sends elapsed time to the agent every minute
            async def periodic_timer_update():
                """Sends elapsed time to the agent every 60 seconds"""
                last_minute = -1
                if interview_tools is None:
                    raise Exception("interview_tools is not defined!")

                while interview_tools.is_timer_running:
                    await asyncio.sleep(5)  # Check every 5 seconds

                    if not interview_tools.is_timer_running:
                        break

                    elapsed_time = interview_tools.get_elapsed_time()
                    # Parse minutes from elapsed time string (format: "Xm Ys")
                    try:
                        current_minute = int(elapsed_time.split("m")[0])
                    except (ValueError, IndexError):
                        continue

                    # Send update only when we cross a new minute
                    if current_minute > last_minute and current_minute > 0:
                        last_minute = current_minute
                        timer_message = f"[SYSTEM TIMER UPDATE: {elapsed_time} elapsed]"
                        timer_content = Content(
                            role="user", parts=[Part.from_text(text=timer_message)]
                        )
                        try:
                            live_request_queue.send_content(content=timer_content)
                            print(f"[TIMER UPDATE]: Sent to agent - {elapsed_time}")
                        except Exception as e:
                            print(f"[TIMER UPDATE]: Failed to send - {e}")
                            break

            timer_task = asyncio.create_task(periodic_timer_update())

            # Create a task to monitor the termination event
            async def wait_for_termination() -> None:
                assert interview_tools is not None
                await interview_tools.termination_event.wait()
                print(f"[TERMINATION]: Interview ended by agent for client #{user_id}")

            termination_task = asyncio.create_task(wait_for_termination())

            # Wait until the websocket is disconnected, an error occurs, or interview ends
            tasks = [agent_to_client_task, client_to_agent_task, termination_task]
            done, pending = await asyncio.wait(
                tasks, return_when=asyncio.FIRST_COMPLETED
            )

            # Cancel timer task
            timer_task.cancel()

            # Check what completed
            for task in done:
                exception = task.exception() if not task.cancelled() else None
                if exception:
                    error_str = str(exception)
                    # Check if this is a session timeout/error (Gemini closes with 1008 or 1011)
                    if (
                        "1008" in error_str
                        or "1011" in error_str
                        or "policy violation" in error_str.lower()
                        or "internal error" in error_str.lower()
                    ):
                        print(
                            f"[SESSION TIMEOUT]: Gemini session error for client #{user_id}, restarting..."
                        )
                        # Cancel pending tasks
                        for t in pending:
                            t.cancel()
                        live_request_queue.close()
                        # Continue the loop to restart session
                        continue
                    else:
                        # Some other error, raise it
                        raise exception

            # If termination event was set, interview ended normally
            if interview_tools.termination_event.is_set():
                print(f"[SESSION]: Interview completed normally for client #{user_id}")
                for task in pending:
                    task.cancel()
                live_request_queue.close()
                break

            # If we get here without exception, client probably disconnected
            for task in pending:
                task.cancel()
            live_request_queue.close()
            break

        except Exception as e:
            error_str = str(e)
            print(f"[SESSION ERROR]: {error_str}")

            # Check if this is a recoverable session error
            if (
                "1008" in error_str
                or "1011" in error_str
                or "policy violation" in error_str.lower()
                or "internal error" in error_str.lower()
                or "ConnectionClosed" in error_str
            ):
                print(f"[SESSION RESTART]: Attempting to resume for client #{user_id}")
                try:
                    live_request_queue.close()
                except asyncio.CancelledError:
                    raise
                except Exception:
                    pass
                # Small delay before restart
                await asyncio.sleep(0.5)
                continue
            else:
                # Non-recoverable error
                break

    # Stop the timer
    if interview_tools:
        interview_tools.stop_timer()

    # Close WebSocket gracefully
    try:
        await websocket.close()
    except Exception:
        pass  # Already closed

    # Disconnected
    print(f"Client #{user_id} disconnected after {session_count} session(s)")
