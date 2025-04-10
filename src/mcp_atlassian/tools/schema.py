"""Tool definitions for Atlassian tools.

This module defines the structure and behavior of tools used in the Atlassian ecosystem.
"""

from dataclasses import dataclass, field
from typing import Any

from mcp.types import Tool


@dataclass
class ToolDefinition:
    """Common definition for Atlassian tools."""

    name: str
    description: str
    input_schema: dict[str, Any]
    is_write_operation: bool = False

    def to_tool(self) -> Tool:
        """Convert to mcp.types.Tool.

        This method converts the ToolDefinition instance to a Tool instance.

        Returns:
            Tool: An instance of the Tool class with the same name, description, and input schema.
        """
        return Tool(
            name=self.name,
            description=self.description,
            inputSchema=self.input_schema,
        )


@dataclass
class Toolbox:
    """Collection of tools."""

    tool_definitions: list[ToolDefinition]
    _tool_cache: dict[str, ToolDefinition] = field(init=False)

    def __post_init__(self):
        """Initialize the toolbox with a cache of tool definitions."""
        # Create a cache for quick lookup of tools by name
        # This is a dictionary comprehension that iterates over the list of tool definitions
        # and creates a dictionary where the keys are the tool names and the values are the tool definitions.
        self._tool_cache = {tool.name: tool for tool in self.tool_definitions}

    def get_tools(self, read_only: bool) -> list[ToolDefinition]:
        """Retrieve all tools, filtering based on read-only mode.

        This method returns a list of tool definitions. If the system is in read-only mode,
        it will exclude tools that are write operations. Otherwise, it will include all tools.

        Args:
            read_only: A boolean indicating whether the system is in read-only mode.

        Returns:
            A list of ToolDefinition objects that are either read operations or,
            if not in read-only mode, all operations.

        """
        return [
            tool
            for tool in self.tool_definitions
            if not tool.is_write_operation or not read_only
        ]

    def get_tool(self, name: str) -> ToolDefinition | None:
        """Get a tool by name.

        Args:
            name: The name of the tool to retrieve.

        Returns:
            The ToolDefinition object if found, otherwise None.
        """
        return self._tool_cache.get(name, None)

    def get_mcp_tools(self, read_only: bool) -> list[Tool]:
        """Get all MCP tools, filtering based on read-only mode.

        This method converts the tool definitions to MCP tools,
        filtering based on read-only mode.

        Args:
            read_only: A boolean indicating whether the system is in read-only mode.

        Returns:
            A list of Tool objects that are either read operations or,
            if not in read-only mode, all operations.
        """
        return [tool.to_tool() for tool in self.get_tools(read_only)]
