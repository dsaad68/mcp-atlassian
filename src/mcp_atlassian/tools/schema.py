"""Tool definitions for Atlassian tools.

This module defines the structure and behavior of tools used in the Atlassian ecosystem.
"""

from contextlib import suppress
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

    def extract_arguments(
        self,
        raw_arguments: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Extract and process arguments based on the input schema.

        This method extracts arguments from the raw input, applies defaults,
        and performs basic type conversions based on the schema definition.

        Args:
            raw_arguments: The raw arguments dictionary passed to the tool.

        Returns:
            A processed dictionary with all arguments properly formatted.

        """
        if raw_arguments is None:
            return {}

        processed_args = {}
        properties = self.input_schema.get("properties", {})

        for prop_name, prop_schema in properties.items():
            # Check if the argument is provided
            if prop_name in raw_arguments:
                value = raw_arguments.get(prop_name)
                prop_type = prop_schema.get("type")

                # Process value based on the schema type
                match prop_type:
                    case "integer" | "number":
                        value = self._process_numeric_value(value, prop_schema)
                    case "boolean":
                        value = self._process_boolean_value(value)

                processed_args[prop_name] = value
            # If not provided, use the default if available
            elif "default" in prop_schema:
                processed_args[prop_name] = prop_schema["default"]

        return processed_args

    def _process_numeric_value(self, value: Any, schema: dict) -> int | float:
        """Process numeric values according to schema rules.

        This method processes numeric values based on the schema rules,
        including type conversion and applying min/max bounds.

        Args:
            value: The value to process.
            schema: The schema definition for the property.

        Returns:
            The processed numeric value, either int or float.
        """
        # Convert string numbers to int or float
        if isinstance(value, str) and value.strip():
            with suppress(ValueError, TypeError):
                value = int(value) if schema.get("type") == "integer" else float(value)

        # Apply min/max bounds if specified
        if isinstance(value, int | float):
            min_val = schema.get("minimum")
            max_val = schema.get("maximum")

            if min_val is not None and value < min_val:
                value = min_val
            if max_val is not None and value > max_val:
                value = max_val

        return value

    def _process_boolean_value(self, value: Any) -> bool:
        """Convert various values to boolean.

        This method converts different types of values to boolean.

        Args:
            value: The value to convert.

        Returns:
            A boolean value.
        """
        if isinstance(value, bool):
            return value

        if isinstance(value, str):
            return value.lower() in {"true", "yes", "1", "t", "y"}

        return bool(value)


@dataclass
class Toolbox:
    """Collection of tools."""

    tool_definitions: list[ToolDefinition]
    _tool_cache: dict[str, ToolDefinition] = field(init=False)

    def __post_init__(self) -> None:
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
            ToolDefinition: The tool definition if found, otherwise None.

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
