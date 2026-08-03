"""Domain errors shared by the AI service and its HTTP routes."""


class AIProcessingCapacityError(RuntimeError):
    """Raised when bounded AI document-processing capacity is exhausted."""


class InvalidStructuredAIResponse(ValueError):
    """Raised when the AI provider does not return a JSON object."""
