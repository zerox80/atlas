"""Domain errors shared by the AI service and its HTTP routes."""


class InvalidStructuredAIResponse(ValueError):
    """Raised when the AI provider does not return a JSON object."""
