from core.settings import LLM_PROVIDER
from services.llm_client import llm_client

# Map provider to corresponding method
llm_ask_functions = {
    "claude": llm_client.ask_claude,
    "openai": llm_client.ask_gpt
}

async def get_llm_response(user_message: str, conversation: list) -> str:
    """Get response from the configured LLM provider."""
    ask_function = llm_ask_functions.get(LLM_PROVIDER)

    if not ask_function:
        raise ValueError(f"Unknown LLM Provider: {LLM_PROVIDER}")

    # Call the corresponding function
    return await ask_function(user_message, conversation)