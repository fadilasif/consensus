"""Project-specific exception types.

Keeping these separate makes it easy for the CLI to report safe, useful
messages without printing raw provider responses or credentials.
"""


class ConsensusError(Exception):
    """Base class for expected application errors."""


class ConfigurationError(ConsensusError):
    """Required configuration (for example an API key) is missing."""


class ValidationError(ConsensusError):
    """User-provided or persisted data failed validation."""


class DataError(ConsensusError):
    """Stored data is missing, unreadable or malformed."""


class DataNotFoundError(DataError):
    """A required data file does not exist."""


class NoUsableCommentsError(DataError):
    """A video has no comments that can be classified."""


class APIError(ConsensusError):
    """A remote provider returned an error."""


class YouTubeAPIError(APIError):
    """YouTube Data API request failed."""


class SubQError(APIError):
    """SubQ request failed."""


class ClassificationResponseError(APIError):
    """A model response could not be interpreted safely."""


class ClassificationIncompleteError(ConsensusError):
    """Some batches failed, but successful results were checkpointed."""


class ConcurrentRunError(ConsensusError):
    """Another process is already writing this run's checkpoints."""
