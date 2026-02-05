# SETUP REQUIRED: Before running this code, you must replace the following placeholders:
#
#   1. _AGENT_ENGINE_NAME (below): Replace YOUR_PROJECT_NUMBER and YOUR_REASONING_ENGINE_ID
#      with the values from your deployed Vertex AI Agent Engine instance.
#      Run `python agent.py deploy` to create one and get the resource name.
#
#   2. GOOGLE_CLOUD_PROJECT environment variable: Set this to your GCP project ID.
#      e.g. export GOOGLE_CLOUD_PROJECT="your-gcp-project-id"
#
# Without these, the server will fail to start.

import logging
import os

import vertexai
from vertexai.generative_models import Content, GenerativeModel, Part

logger = logging.getLogger(__name__)

# Default Vertex AI model
_MODEL_NAME = "gemini-2.5-flash"

# System prompt template for personalized responses
_SYSTEM_PROMPT = (
    "You are a friendly, helpful AI assistant. "
    "You are chatting with {name}. "
    "{memory_context}"
    "Remember context from the conversation and provide personalized responses. "
    "Keep responses concise but helpful."
)

_AGENT_ENGINE_NAME = "projects/YOUR_PROJECT_NUMBER/locations/us-central1/reasoningEngines/YOUR_REASONING_ENGINE_ID"


def _format_memories(retrieved_memories: list) -> str:
    """Format retrieved Memory Bank memories into a prompt fragment."""
    if not retrieved_memories:
        return ""
    facts = "\n".join(f"- {m.memory.fact}" for m in retrieved_memories)
    return (
        "Here is what you remember about this user from previous conversations:\n"
        f"{facts}\n"
        "Use this information to personalize your responses.\n\n"
    )


class ChatAgent:
    """Personalized chat agent backed by Vertex AI with native Memory Bank.

    Short-term memory: in-process conversation history for the current session.
    Long-term memory:  Vertex AI Agent Engine Memory Bank (persisted across
                       sessions and server restarts).
    """

    def __init__(
        self,
        project_id: str | None = None,
        location: str = "us-central1",
        model_name: str = _MODEL_NAME,
        agent_engine_name: str | None = None,
    ):
        self._project_id = project_id or os.environ.get("GOOGLE_CLOUD_PROJECT")
        self._location = location
        self._model_name = model_name

        # Legacy init (needed for GenerativeModel)
        vertexai.init(project=self._project_id, location=location)

        # New Vertex AI client for Agent Engine Memory Bank
        self._client = vertexai.Client(
            project=self._project_id, location=location
        )

        # Resolve the Agent Engine instance
        self._agent_engine_name = (
            agent_engine_name
            or os.environ.get("AGENT_ENGINE_NAME")
            or _AGENT_ENGINE_NAME
        )

        # In-process session history: user_id -> [{"role": ..., "text": ...}]
        self._session_history: dict[str, list[dict[str, str]]] = {}

    # ------------------------------------------------------------------
    # Memory Bank helpers
    # ------------------------------------------------------------------

    def _retrieve_memories(self, user_id: str) -> str:
        """Retrieve long-term memories for a user from Memory Bank."""
        try:
            results = list(
                self._client.agent_engines.memories.retrieve(
                    name=self._agent_engine_name,
                    scope={"user_id": user_id},
                )
            )
            return _format_memories(results)
        except Exception as e:
            logger.warning("Failed to retrieve memories: %s", e)
            return ""

    def _generate_memories(
        self, user_id: str, user_text: str, model_text: str
    ) -> None:
        """Trigger background memory generation from the latest exchange."""
        try:
            self._client.agent_engines.memories.generate(
                name=self._agent_engine_name,
                direct_contents_source={
                    "events": [
                        {
                            "content": {
                                "role": "user",
                                "parts": [{"text": user_text}],
                            }
                        },
                        {
                            "content": {
                                "role": "model",
                                "parts": [{"text": model_text}],
                            }
                        },
                    ]
                },
                scope={"user_id": user_id},
                # Run in the background so the user isn't blocked
                config={"wait_for_completion": False},
            )
        except Exception as e:
            logger.warning("Failed to generate memories: %s", e)

    # ------------------------------------------------------------------
    # Session history helpers
    # ------------------------------------------------------------------

    def _build_session_history(self, user_id: str) -> list[Content]:
        """Convert the in-process session history into Content objects."""
        return [
            Content(role=entry["role"], parts=[Part.from_text(entry["text"])])
            for entry in self._session_history.get(user_id, [])
        ]

    def get_history(self, user_id: str) -> list[dict[str, str]]:
        """Return the current session's conversation history."""
        return list(self._session_history.get(user_id, []))

    def clear_history(self, user_id: str) -> None:
        """Clear the current session's conversation history."""
        self._session_history.pop(user_id, None)

    # ------------------------------------------------------------------
    # Chat
    # ------------------------------------------------------------------

    def chat(self, user_id: str, message: str, user_display_name: str = "") -> str:
        """Send a message and get a response.

        1. Retrieve long-term memories from Memory Bank.
        2. Build a system prompt that includes those memories.
        3. Send the message with the current session history to Gemini.
        4. Persist the exchange in session history.
        5. Trigger background memory generation for long-term storage.

        Args:
            user_id: Unique identifier for the user (e.g. Firebase UID).
            message: The user's message text.
            user_display_name: Friendly name shown in the system prompt.

        Returns:
            The model's reply as a string.
        """
        if user_id not in self._session_history:
            self._session_history[user_id] = []

        # 1. Retrieve long-term memories
        memory_context = self._retrieve_memories(user_id)

        # 2. Build personalized system prompt
        system_instruction = _SYSTEM_PROMPT.format(
            name=user_display_name or "a user",
            memory_context=memory_context,
        )

        # 3. Chat with Gemini
        model = GenerativeModel(
            self._model_name,
            system_instruction=system_instruction,
        )
        chat_session = model.start_chat(
            history=self._build_session_history(user_id)
        )
        response = chat_session.send_message(message)
        reply = response.text

        # 4. Persist in session history
        self._session_history[user_id].append({"role": "user", "text": message})
        self._session_history[user_id].append({"role": "model", "text": reply})

        # 5. Trigger background memory generation
        self._generate_memories(user_id, message, reply)

        return reply


# ------------------------------------------------------------------
# CLI: deploy / tear-down Agent Engine
# ------------------------------------------------------------------

def _deploy(project_id: str | None, location: str) -> str:
    """Create a new Agent Engine instance and return its resource name."""
    client = vertexai.Client(project=project_id, location=location)
    print("Creating Agent Engine instance...")
    engine = client.agent_engines.create()
    name = engine.api_resource.name
    print(f"\nAgent Engine deployed successfully!\n\n  {name}\n")
    print("Export it so the server can find it:\n")
    print(f'  export AGENT_ENGINE_NAME="{name}"\n')
    return name


def _teardown(agent_engine_name: str, project_id: str | None, location: str) -> None:
    """Delete an existing Agent Engine instance."""
    client = vertexai.Client(project=project_id, location=location)
    print(f"Deleting Agent Engine: {agent_engine_name} ...")
    client.agent_engines.delete(name=agent_engine_name, force=True)
    print("Deleted.")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Deploy or tear down a Vertex AI Agent Engine instance."
    )
    parser.add_argument(
        "action",
        choices=["deploy", "teardown"],
        help="'deploy' creates a new instance; 'teardown' deletes one.",
    )
    parser.add_argument(
        "--project",
        default=os.environ.get("GOOGLE_CLOUD_PROJECT", "your-gcp-project-id"),
        help="GCP project ID (default: gcp-training-486505).",
    )
    parser.add_argument(
        "--location",
        default="us-central1",
        help="GCP region (default: us-central1).",
    )
    parser.add_argument(
        "--name",
        default=os.environ.get("AGENT_ENGINE_NAME", _AGENT_ENGINE_NAME),
        help="Agent Engine resource name (default: the deployed instance).",
    )
    args = parser.parse_args()

    if args.action == "deploy":
        _deploy(args.project, args.location)
    elif args.action == "teardown":
        if not args.name:
            parser.error("--name is required for teardown")
        _teardown(args.name, args.project, args.location)
