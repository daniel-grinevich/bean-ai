class AgentUnavailable(RuntimeError):
    """The agent can't run: an API key isn't configured, or the run lacks what it needs (a repository).

    The message is shown to the user as-is, so say what's missing and how to fix it.
    """
