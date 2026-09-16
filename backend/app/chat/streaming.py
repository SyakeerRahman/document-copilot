from pydantic_ai.ui.vercel_ai.response_types import BaseChunk

# AI SDK UI message stream protocol. v7 of the AI SDK uses the same wire format as v6.
# https://ai-sdk.dev/docs/ai-sdk-ui/stream-protocol
SDK_VERSION = 7
STREAM_HEADERS = {"x-vercel-ai-ui-message-stream": "v1"}
STREAM_MEDIA_TYPE = "text/event-stream"
DONE = "data: [DONE]\n\n"


def encode(chunk: BaseChunk) -> str:
    return f"data: {chunk.encode(SDK_VERSION)}\n\n"
