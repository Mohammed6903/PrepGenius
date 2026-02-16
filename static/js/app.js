/**
 * AI Interview Pro - Main Application
 * Handles WebSocket connection, audio/video streaming, and UI state management
 */

const sessionId = Math.random().toString().substring(10);
let websocket = null;
let is_audio = false;
let isInterviewActive = false;

// DOM Elements
const messageForm = document.getElementById("messageForm");
const messageInput = document.getElementById("message");
const messagesDiv = document.getElementById("messages");
const welcomeMessage = document.getElementById("welcomeMessage");
const startInterviewButton = document.getElementById("startInterviewButton");
const endInterviewButton = document.getElementById("endInterviewButton");
const startVideoButton = document.getElementById("startVideoButton");
const stopVideoButton = document.getElementById("stopVideoButton");
const statusDot = document.getElementById("statusDot");
const statusText = document.getElementById("statusText");
const videoPlaceholder = document.getElementById("videoPlaceholder");
const videoPreview = document.getElementById("videoPreview");
const recordingIndicator = document.getElementById("recordingIndicator");
const audioIndicator = document.getElementById("audioIndicator");
const connectingOverlay = document.getElementById("connectingOverlay");
const messageCount = document.getElementById("messageCount");
const sendButton = document.getElementById("sendButton");

let currentMessageId = null;
let messageCounter = 0;

// Video/Image streaming
let videoElement = null;
let stream = null;
let canvasElement = null;
let canvasContext = null;
let captureIntervalId = null;

// Audio handling
let audioPlayerNode;
let audioPlayerContext;
let audioRecorderNode;
let audioRecorderContext;
let micStream;
let audioBuffer = [];
let bufferTimer = null;

import { startAudioPlayerWorklet } from "./audio-player.js";
import { startAudioRecorderWorklet } from "./audio-recorder.js";

/**
 * UI State Management
 */
function updateConnectionStatus(connected) {
  if (connected) {
    statusDot.classList.add("connected");
    statusText.textContent = "Connected";
  } else {
    statusDot.classList.remove("connected");
    statusText.textContent = "Disconnected";
  }
}

function updateMessageCount() {
  messageCount.textContent = `${messageCounter} message${messageCounter !== 1 ? 's' : ''}`;
}

function showConnectingOverlay() {
  connectingOverlay.classList.remove("hidden");
}

function hideConnectingOverlay() {
  connectingOverlay.classList.add("hidden");
}

function enableInterviewUI() {
  // Hide welcome message
  if (welcomeMessage) {
    welcomeMessage.style.display = "none";
  }

  // Enable controls
  startVideoButton.disabled = false;
  messageInput.disabled = false;
  sendButton.disabled = false;

  // Toggle buttons
  startInterviewButton.classList.add("hidden");
  endInterviewButton.classList.remove("hidden");

  // Show audio indicator
  audioIndicator.classList.remove("hidden");
}

function disableInterviewUI() {
  // Show welcome message
  if (welcomeMessage) {
    welcomeMessage.style.display = "";
  }

  // Disable controls
  startVideoButton.disabled = true;
  messageInput.disabled = true;
  sendButton.disabled = true;

  // Toggle buttons
  startInterviewButton.classList.remove("hidden");
  endInterviewButton.classList.add("hidden");

  // Hide indicators
  audioIndicator.classList.add("hidden");
  recordingIndicator.classList.add("hidden");

  // Reset video UI
  hideVideo();
}

function showVideo() {
  videoPreview.classList.remove("hidden");
  videoPlaceholder.classList.add("hidden");
  startVideoButton.classList.add("hidden");
  stopVideoButton.classList.remove("hidden");
  recordingIndicator.classList.remove("hidden");
}

function hideVideo() {
  videoPreview.classList.add("hidden");
  videoPlaceholder.classList.remove("hidden");
  stopVideoButton.classList.add("hidden");
  startVideoButton.classList.remove("hidden");
  recordingIndicator.classList.add("hidden");
}

/**
 * WebSocket Connection
 */
function connectWebsocket() {
  if (websocket && websocket.readyState === WebSocket.OPEN) {
    console.warn("WebSocket already connected.");
    return;
  }

  // Construct WebSocket URL with proper protocol (wss for https, ws for http)
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const ws_url = `${protocol}//${window.location.host}/ws/${sessionId}`;
  
  websocket = new WebSocket(ws_url + "?is_audio=" + is_audio);

  websocket.onopen = function () {
    console.log("WebSocket connection opened.");
    updateConnectionStatus(true);
    hideConnectingOverlay();

    if (is_audio) {
      enableInterviewUI();
      isInterviewActive = true;
    }

    addSubmitHandler();
  };

  websocket.onmessage = function (event) {
    const message_from_server = JSON.parse(event.data);
    console.log("[AGENT TO CLIENT] ", message_from_server);

    // Check if turn is complete
    if (message_from_server.turn_complete === true) {
      currentMessageId = null;
      return;
    }

    // Check for interrupt
    if (message_from_server.interrupted === true) {
      if (audioPlayerNode) {
        audioPlayerNode.port.postMessage({ command: "endOfAudio" });
      }
      return;
    }

    // Handle audio
    if (message_from_server.mime_type === "audio/pcm" && audioPlayerNode) {
      audioPlayerNode.port.postMessage(base64ToArray(message_from_server.data));
    }

    // Handle text
    if (message_from_server.mime_type === "text/plain") {
      if (currentMessageId === null) {
        currentMessageId = Math.random().toString(36).substring(7);
        const message = document.createElement("div");
        message.id = currentMessageId;
        message.className = "message agent";
        messagesDiv.appendChild(message);
        messageCounter++;
        updateMessageCount();
      }

      const message = document.getElementById(currentMessageId);
      message.textContent += message_from_server.data;
      messagesDiv.scrollTop = messagesDiv.scrollHeight;
    }
  };

  websocket.onclose = function () {
    console.log("WebSocket connection closed.");
    updateConnectionStatus(false);

    if (isInterviewActive) {
      // Unexpected close - could reconnect here
    }
  };

  websocket.onerror = function (e) {
    console.log("WebSocket error: ", e);
    hideConnectingOverlay();
  };
}

function disconnectWebsocket() {
  if (websocket) {
    websocket.close();
    websocket = null;
  }
}

/**
 * Message Handling
 */
function addSubmitHandler() {
  messageForm.onsubmit = function (e) {
    e.preventDefault();
    const message = messageInput.value.trim();
    if (message) {
      // Add user message to transcript
      const userMsg = document.createElement("div");
      userMsg.className = "message user";
      userMsg.textContent = message;
      messagesDiv.appendChild(userMsg);

      messageCounter++;
      updateMessageCount();

      messageInput.value = "";
      sendMessage({
        mime_type: "text/plain",
        data: message,
      });
      console.log("[CLIENT TO AGENT] " + message);

      messagesDiv.scrollTop = messagesDiv.scrollHeight;
    }
    return false;
  };
}

function sendMessage(message) {
  if (websocket && websocket.readyState === WebSocket.OPEN) {
    const messageJson = JSON.stringify(message);
    websocket.send(messageJson);
  }
}

function base64ToArray(base64) {
  const binaryString = window.atob(base64);
  const len = binaryString.length;
  const bytes = new Uint8Array(len);
  for (let i = 0; i < len; i++) {
    bytes[i] = binaryString.charCodeAt(i);
  }
  return bytes.buffer;
}

function arrayBufferToBase64(buffer) {
  let binary = "";
  const bytes = new Uint8Array(buffer);
  const len = bytes.byteLength;
  for (let i = 0; i < len; i++) {
    binary += String.fromCharCode(bytes[i]);
  }
  return window.btoa(binary);
}

/**
 * Image Frame Streaming (Video)
 */
function captureFrame() {
  if (!videoElement || !canvasContext) {
    console.error("Video element or canvas context not ready.");
    return;
  }

  canvasElement.width = videoElement.videoWidth;
  canvasElement.height = videoElement.videoHeight;
  canvasContext.drawImage(videoElement, 0, 0, canvasElement.width, canvasElement.height);

  const imageDataURL = canvasElement.toDataURL('image/jpeg', 0.8);
  const base64Data = imageDataURL.split(',')[1];

  if (base64Data) {
    sendMessage({
      mime_type: "image/jpeg",
      data: base64Data
    });
    console.log("[CLIENT TO AGENT] sent image frame:", base64Data.length, "bytes");
  }
}

async function startImageFrameStreaming() {
  try {
    stream = await navigator.mediaDevices.getUserMedia({
      video: {
        width: { ideal: 640 },
        height: { ideal: 480 },
        frameRate: { ideal: 10 }
      },
      audio: false
    });

    videoElement = videoPreview;
    videoElement.srcObject = stream;

    canvasElement = document.createElement("canvas");
    canvasContext = canvasElement.getContext('2d');

    captureIntervalId = setInterval(captureFrame, 2000);
    console.log("Image frame streaming started");

    showVideo();
    return true;
  } catch (error) {
    console.error("Error starting image frame streaming:", error);
    return false;
  }
}

function stopImageFrameStreaming() {
  if (captureIntervalId) {
    clearInterval(captureIntervalId);
    captureIntervalId = null;
  }

  if (stream) {
    stream.getTracks().forEach(track => track.stop());
    stream = null;
  }

  if (videoElement) {
    videoElement.srcObject = null;
  }

  if (canvasElement) {
    canvasElement.remove();
    canvasElement = null;
    canvasContext = null;
  }

  hideVideo();
  console.log("Image frame streaming stopped");
}

/**
 * Audio Handling
 */
function startAudio() {
  startAudioPlayerWorklet().then(([node, ctx]) => {
    audioPlayerNode = node;
    audioPlayerContext = ctx;
  });

  startAudioRecorderWorklet(audioRecorderHandler).then(
    ([node, ctx, stream]) => {
      audioRecorderNode = node;
      audioRecorderContext = ctx;
      micStream = stream;
    }
  );
}

function audioRecorderHandler(pcmData) {
  audioBuffer.push(new Uint8Array(pcmData));

  if (!bufferTimer) {
    bufferTimer = setInterval(sendBufferedAudio, 1000);
  }
}

function sendBufferedAudio() {
  if (audioBuffer.length === 0) return;

  let totalLength = 0;
  for (const chunk of audioBuffer) {
    totalLength += chunk.length;
  }

  const combinedBuffer = new Uint8Array(totalLength);
  let offset = 0;
  for (const chunk of audioBuffer) {
    combinedBuffer.set(chunk, offset);
    offset += chunk.length;
  }

  sendMessage({
    mime_type: "audio/pcm",
    data: arrayBufferToBase64(combinedBuffer.buffer),
  });
  console.log("[CLIENT TO AGENT] sent %s bytes", combinedBuffer.byteLength);

  audioBuffer = [];
}

function stopAudioRecording() {
  if (bufferTimer) {
    clearInterval(bufferTimer);
    bufferTimer = null;
  }

  if (audioBuffer.length > 0) {
    sendBufferedAudio();
  }

  if (micStream) {
    micStream.getTracks().forEach(track => track.stop());
    micStream = null;
  }

  if (audioRecorderNode) {
    try {
      audioRecorderNode.disconnect();
    } catch (e) {
      console.warn("Error disconnecting audioRecorderNode:", e);
    }
    audioRecorderNode = null;
  }

  if (audioRecorderContext && audioRecorderContext.state !== "closed") {
    audioRecorderContext.close().catch((err) => console.error("Error closing recorder context:", err));
    audioRecorderContext = null;
  }

  audioBuffer = [];
  console.log("Audio recording stopped and cleaned up");
}

/**
 * Interview Flow Control
 */
function startInterview() {
  showConnectingOverlay();
  is_audio = true;
  startAudio();
  connectWebsocket();
}

function endInterview() {
  isInterviewActive = false;

  // Stop video if active
  stopImageFrameStreaming();

  // Stop audio
  stopAudioRecording();

  // Close connection
  disconnectWebsocket();

  // Reset UI
  disableInterviewUI();
  is_audio = false;

  // Clear messages
  messageCounter = 0;
  updateMessageCount();
  currentMessageId = null;

  // Clear transcript except welcome message
  const messages = messagesDiv.querySelectorAll('.message');
  messages.forEach(msg => msg.remove());
}

/**
 * Event Listeners
 */
startInterviewButton.addEventListener("click", () => {
  startInterview();
});

endInterviewButton.addEventListener("click", () => {
  endInterview();
});

startVideoButton.addEventListener("click", async () => {
  const success = await startImageFrameStreaming();
  if (!success) {
    alert("Could not access camera. Please check permissions.");
  }
});

stopVideoButton.addEventListener("click", () => {
  stopImageFrameStreaming();
});

// Initialize UI state
disableInterviewUI();
console.log("AI Interview Pro initialized. Click 'Start Interview' to begin.");
