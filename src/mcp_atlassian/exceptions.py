# Custom exceptions for configuration errors
class JiraNotConfiguredError(Exception):
    """Exception raised when Jira is not configured properly."""

    def __init__(self, message: str = "Jira is not configured.") -> None:
        self.message = message
        super().__init__(self.message)


class ConfluenceNotConfiguredError(Exception):
    """Exception raised when Confluence is not configured properly."""

    def __init__(self, message: str = "Confluence is not configured.") -> None:
        self.message = message
        super().__init__(self.message)


class MCPAtlassianAuthenticationError(Exception):
    """Raised when Atlassian API authentication fails (401/403)."""

    pass


class InvalidJSONError(Exception):
    """Exception raised when JSON parsing fails."""

    def __init__(
        self,
        message: str = "Invalid JSON format",
        field_name: str | None = None,
    ) -> None:
        self.field_name = field_name
        if field_name:
            message = f"Invalid JSON in {field_name}: {message}"
        self.message = message
        super().__init__(self.message)
