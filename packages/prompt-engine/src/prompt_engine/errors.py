"""Domain errors for structured prompt-intent analysis."""


class IntentAnalysisError(Exception):
    """Base error for intent analysis failures that are safe to surface upstream."""


class InvalidAnalysisInputError(IntentAnalysisError):
    """Raised when the requested analysis input is not valid."""


class EmptyRawRequestError(InvalidAnalysisInputError):
    """Raised when analysis is requested without a user request."""


class StructuredAnalysisBackendError(IntentAnalysisError):
    """Raised when the structured analysis backend cannot produce a result."""


class InvalidStructuredAnalysisOutputError(IntentAnalysisError):
    """Raised when backend output does not validate as the requested PromptSpec."""


class IncompletePromptSpecificationError(Exception):
    """Raised when required missing information prevents prompt compilation."""


class UnknownTaskPresetError(Exception):
    """Raised when a requested built-in preset cannot be found."""


class ExecutionError(Exception):
    """Base error for provider-independent compiled-prompt execution."""


class InvalidExecutionRequestError(ExecutionError):
    """Raised when compiled prompt text cannot safely be executed."""


class ExecutionBackendError(ExecutionError):
    """Raised when an execution backend cannot produce a response."""


class InvalidExecutionOutputError(ExecutionError):
    """Raised when an execution backend returns no usable text."""
