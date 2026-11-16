class AgentUnavailable(RuntimeError):
    """The agent can't be built in this environment (an API key or path isn't configured).

    The message is shown to the user as-is, so say what's missing and which setting fixes it.
    """
