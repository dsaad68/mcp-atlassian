import json
import logging
import os
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from atlassian.errors import ApiError
from mcp.server import Server
from mcp.types import Resource, TextContent, Tool
from pydantic import AnyUrl
from requests.exceptions import RequestException

from .confluence import ConfluenceFetcher
from .confluence.utils import quote_cql_identifier_if_needed
from .exceptions import (
    ConfluenceNotConfiguredError,
    InvalidJSONError,
    JiraNotConfiguredError,
)
from .jira import JiraFetcher
from .jira.utils import escape_jql_string
from .tools.confluence import CONFLUENCE_TOOLBOX
from .tools.jira import JIRA_TOOLBOX
from .utils.io import is_read_only_mode
from .utils.urls import is_atlassian_cloud_url

# Configure logging
logger = logging.getLogger("mcp-atlassian")


def get_read_only_response(operation_name: str) -> list[TextContent]:
    """Generate a response for when an operation is not available in read-only mode.

    Args:
        operation_name: Name of the operation being attempted

    Returns:
        List containing a TextContent response

    """
    return [
        TextContent(
            type="text",
            text=f"Operation '{operation_name}' is not available in read-only mode.",
        ),
    ]


@dataclass
class AppContext:
    """Application context for MCP Atlassian."""

    confluence: ConfluenceFetcher | None = None
    jira: JiraFetcher | None = None


def get_available_services() -> dict[str, bool | None]:
    """Determine which services are available based on environment variables.

    Returns:
        Dictionary indicating whether Confluence and Jira are configured.

    """
    # Check for either cloud authentication (URL + username + API token)
    # or server/data center authentication (URL + ( personal token or username + API token ))
    confluence_url = os.getenv("CONFLUENCE_URL")
    if confluence_url:
        is_cloud = is_atlassian_cloud_url(confluence_url)

        if is_cloud:
            confluence_is_setup = all(
                [
                    confluence_url,
                    os.getenv("CONFLUENCE_USERNAME"),
                    os.getenv("CONFLUENCE_API_TOKEN"),
                ],
            )
            logger.info("Using Confluence Cloud authentication method")
        else:
            confluence_is_setup = all(
                [
                    confluence_url,
                    os.getenv("CONFLUENCE_PERSONAL_TOKEN")
                    # Some on prem/data center use username and api token too.
                    or (
                        os.getenv("CONFLUENCE_USERNAME")
                        and os.getenv("CONFLUENCE_API_TOKEN")
                    ),
                ],
            )
            logger.info("Using Confluence Server/Data Center authentication method")
    else:
        confluence_is_setup = False

    # Check for either cloud authentication (URL + username + API token)
    # or server/data center authentication (URL + personal token)
    jira_url = os.getenv("JIRA_URL")
    if jira_url:
        is_cloud = is_atlassian_cloud_url(jira_url)

        if is_cloud:
            jira_is_setup = all(
                [jira_url, os.getenv("JIRA_USERNAME"), os.getenv("JIRA_API_TOKEN")],
            )
            logger.info("Using Jira Cloud authentication method")
        else:
            jira_is_setup = all([jira_url, os.getenv("JIRA_PERSONAL_TOKEN")])
            logger.info("Using Jira Server/Data Center authentication method")
    else:
        jira_is_setup = False

    return {"confluence": confluence_is_setup, "jira": jira_is_setup}


@asynccontextmanager
async def server_lifespan(server: Server) -> AsyncIterator[AppContext]:
    """Initialize and clean up application resources.

    Yields:
        AppContext: The application context containing initialized services.
    """
    # Get available services
    services = get_available_services()

    try:
        # Initialize services
        confluence = ConfluenceFetcher() if services["confluence"] else None
        jira = JiraFetcher() if services["jira"] else None

        # Log the startup information
        logger.info("Starting MCP Atlassian server")

        # Log read-only mode status
        read_only = is_read_only_mode()
        logger.info("Read-only mode: %s", "ENABLED" if read_only else "DISABLED")

        if confluence:
            confluence_url = confluence.config.url
            logger.info("Confluence URL: %s", confluence_url)
        if jira:
            jira_url = jira.config.url
            logger.info("Jira URL: %s", jira_url)

        # Provide context to the application
        yield AppContext(confluence=confluence, jira=jira)
    finally:
        # Cleanup resources if needed
        pass


# Create server instance
app = Server("mcp-atlassian", lifespan=server_lifespan)


# Implement server handlers
@app.list_resources()
async def list_resources() -> list[Resource]:
    """List Confluence spaces and Jira projects the user is actively interacting with.

    Returns:
        List of Resource objects representing Confluence spaces and Jira projects.

    """
    resources = []

    ctx = app.request_context.lifespan_context

    # Add Confluence spaces the user has contributed to
    if ctx and ctx.confluence:
        try:
            # Get spaces the user has contributed to
            spaces = ctx.confluence.get_user_contributed_spaces(limit=250)

            # Add spaces to resources
            resources.extend(
                [
                    Resource(
                        uri=f"confluence://{space['key']}",
                        name=f"Confluence Space: {space['name']}",
                        mimeType="text/plain",
                        description=(
                            f"A Confluence space containing documentation and knowledge base articles. "
                            f"Space Key: {space['key']}. "
                            f"{space.get('description', '')} "
                            f"Access content using: confluence://{space['key']}/pages/PAGE_TITLE"
                        ).strip(),
                    )
                    for space in spaces.values()
                ],
            )
        except Exception as e:
            logger.exception(
                "Error fetching Confluence spaces",
                extra={"error": str(e)},
            )

    # Add Jira projects the user is involved with
    if ctx and ctx.jira:
        try:
            # Get current user's account ID
            account_id = ctx.jira.get_current_user_account_id()

            # Escape the account ID for safe JQL insertion
            escaped_account_id = escape_jql_string(account_id)

            # Use JQL to find issues the user is assigned to or reported, using the escaped ID
            # Note: We use the escaped_account_id directly, as it already includes the necessary quotes.
            jql = f"assignee = {escaped_account_id} OR reporter = {escaped_account_id} ORDER BY updated DESC"
            logger.debug("Executing JQL for list_resources: %s", jql)
            issues = ctx.jira.jira.jql(jql, limit=250, fields=["project"])

            # Extract and deduplicate projects
            projects = {}
            for issue in issues.get("issues", []):
                project = issue.get("fields", {}).get("project", {})
                project_key = project.get("key")
                if project_key and project_key not in projects:
                    projects[project_key] = {
                        "key": project_key,
                        "name": project.get("name", project_key),
                        "description": project.get("description", ""),
                    }

            # Add projects to resources
            resources.extend(
                [
                    Resource(
                        uri=f"jira://{project['key']}",
                        name=f"Jira Project: {project['name']}",
                        mimeType="text/plain",
                        description=(
                            f"A Jira project tracking issues and tasks. Project Key: {project['key']}. "
                        ).strip(),
                    )
                    for project in projects.values()
                ],
            )
        except Exception:
            logger.exception("Error fetching Jira projects:")

    return resources


@app.read_resource()
async def read_resource(uri: AnyUrl) -> str:
    """Read content from Confluence based on the resource URI.

    Args:
        uri: The URI of the resource to read.

    Returns:
        The content of the resource as a string.

    Raises:
        ValueError: If the URI is invalid or the resource cannot be read.
        ConfluenceNotConfiguredError: If Confluence is not configured.
        JiraNotConfiguredError: If Jira is not configured.

    """
    # Get application context
    ctx = app.request_context.lifespan_context

    # Handle Confluence resources
    if str(uri).startswith("confluence://"):
        if not ctx or not ctx.confluence:
            raise ConfluenceNotConfiguredError
        parts = str(uri).replace("confluence://", "").split("/")

        # Handle space listing
        if len(parts) == 1:
            space_key = parts[0]

            # Apply the fix here - properly quote the space key
            quoted_space_key = quote_cql_identifier_if_needed(space_key)

            # Use CQL to find recently updated pages in this space
            cql = f"space = {quoted_space_key} AND contributor = currentUser() ORDER BY lastmodified DESC"
            pages = ctx.confluence.search(cql=cql, limit=20)

            if not pages:
                # Fallback to regular space pages if no user-contributed pages found
                pages = ctx.confluence.get_space_pages(space_key, limit=10)

            content = []
            for page in pages:
                page_dict = page.to_simplified_dict()
                title = page_dict.get("title", "Untitled")
                url = page_dict.get("url", "")

                content.append(f"# [{title}]({url})\n\n{page.page_content}\n\n---")

            return "\n\n".join(content)

        # Handle specific page
        elif len(parts) >= 3 and parts[1] == "pages":
            space_key = parts[0]
            title = parts[2]
            page = ctx.confluence.get_page_by_title(space_key, title)

            if not page:
                msg = f"Page not found: {title}"
                raise ValueError(msg, title)

            return page.page_content

    # Handle Jira resources
    elif str(uri).startswith("jira://"):
        if not ctx or not ctx.jira:
            raise JiraNotConfiguredError
        parts = str(uri).replace("jira://", "").split("/")

        # Handle project listing
        if len(parts) == 1:
            project_key = parts[0]

            # Get current user's account ID
            account_id = ctx.jira.get_current_user_account_id()

            # Use JQL to find issues in this project that the user is involved with
            jql = f"project = {project_key} AND (assignee = {account_id} OR reporter = {account_id}) ORDER BY updated DESC"
            issues = ctx.jira.search_issues(jql=jql, limit=20)

            if not issues:
                # Fallback to recent issues if no user-related issues found
                issues = ctx.jira.get_project_issues(project_key, limit=10)

            content = []
            for issue in issues:
                issue_dict = issue.to_simplified_dict()
                key = issue_dict.get("key", "")
                summary = issue_dict.get("summary", "Untitled")
                url = issue_dict.get("url", "")
                status = issue_dict.get("status", {})
                status_name = status.get("name", "Unknown") if status else "Unknown"

                # Create a markdown representation of the issue
                issue_content = (
                    f"# [{key}: {summary}]({url})\nStatus: {status_name}\n\n"
                )
                if issue_dict.get("description"):
                    issue_content += f"{issue_dict.get('description')}\n\n"

                content.append(f"{issue_content}---")

            return "\n\n".join(content)

        # Handle specific issue
        elif len(parts) >= 2:
            issue_key = parts[1] if len(parts) > 1 else parts[0]
            issue = ctx.jira.get_issue(issue_key)

            if not issue:
                msg = f"Issue not found: {issue_key}"
                raise ValueError(msg)

            issue_dict = issue.to_simplified_dict()
            markdown = f"# {issue_dict.get('key')}: {issue_dict.get('summary')}\n\n"

            if issue_dict.get("status"):
                status_name = issue_dict.get("status", {}).get("name", "Unknown")
                markdown += f"**Status:** {status_name}\n\n"

            if issue_dict.get("description"):
                markdown += f"{issue_dict.get('description')}\n\n"

            return markdown

    msg = f"Invalid resource URI: {uri}"
    raise ValueError(msg)


@app.list_tools()
async def list_tools() -> list[Tool]:
    """List available Confluence and Jira tools.

    Returns:
        List of Tool objects representing available tools.

    """
    tools = []
    ctx = app.request_context.lifespan_context

    # Check if we're in read-only mode
    read_only = is_read_only_mode()

    # Add Confluence tools if Confluence is configured
    if ctx and ctx.confluence:
        # Get Confluence tools based on read-only mode
        confluence_tools = CONFLUENCE_TOOLBOX.get_mcp_tools(read_only)
        tools.extend(confluence_tools)

    # Add Jira tools if Jira is configured
    if ctx and ctx.jira:
        # Get Jira tools based on read-only mode
        jira_tools = JIRA_TOOLBOX.get_mcp_tools(read_only)
        tools.extend(jira_tools)

    return tools


@app.call_tool()
async def call_tool(name: str, arguments: Any) -> Sequence[TextContent]:
    """Handle tool calls for Confluence and Jira operations.

    Args:
        name: The name of the tool to call.
        arguments: The arguments to pass to the tool.

    Returns:
        A list of TextContent objects containing the results of the tool call.

    Raises:
            ValueError: If the tool name is unknown.
            ConfluenceNotConfiguredError: If Confluence is not configured.
            JiraNotConfiguredError: If Jira is not configured.
            InvalidJSONError: If the provided JSON is invalid.

    """
    ctx = app.request_context.lifespan_context

    # Check if we're in read-only mode for write operations
    read_only = is_read_only_mode()

    tool = JIRA_TOOLBOX.get_tool(name) or CONFLUENCE_TOOLBOX.get_tool(name)

    if not tool:
        msg = f"Unknown tool: {name}"
        raise ValueError(msg)

    try:
        # Helper functions for formatting results
        def format_comment(comment: Any) -> dict[str, Any]:
            if hasattr(comment, "to_simplified_dict"):
                # Cast the return value to dict[str, Any] to satisfy the type checker
                return cast("dict[str, Any]", comment.to_simplified_dict())
            return {
                "id": comment.get("id"),
                "author": comment.get("author", {}).get("displayName", "Unknown"),
                "created": comment.get("created"),
                "body": comment.get("body"),
            }

        # Use match-case to handle different tool calls
        match tool.name:
            # Confluence operations
            case "confluence_search":
                if not ctx or not ctx.confluence:
                    raise ConfluenceNotConfiguredError

                query = arguments.get("query", "")
                limit = min(int(arguments.get("limit", 10)), 50)
                spaces_filter = arguments.get("spaces_filter")

                # Check if the query is a simple search term or already a CQL query
                if query and not any(
                    x in query
                    for x in ["=", "~", ">", "<", " AND ", " OR ", "currentUser()"]
                ):
                    # Convert simple search term to CQL text search
                    # This will search in all content (title, body, etc.)
                    query = f'text ~ "{query}"'
                    logger.info("Converting simple search term to CQL: %s", query)

                pages = ctx.confluence.search(
                    query,
                    limit=limit,
                    spaces_filter=spaces_filter,
                )

                # Format results using the to_simplified_dict method
                search_results = [page.to_simplified_dict() for page in pages]

                return [
                    TextContent(
                        type="text",
                        text=json.dumps(search_results, indent=2, ensure_ascii=False),
                    ),
                ]

            case "confluence_get_page":
                if not ctx or not ctx.confluence:
                    raise ConfluenceNotConfiguredError

                page_id = arguments.get("page_id")
                include_metadata = arguments.get("include_metadata", True)
                convert_to_markdown = arguments.get("convert_to_markdown", True)

                page = ctx.confluence.get_page_content(
                    page_id,
                    convert_to_markdown=convert_to_markdown,
                )

                if include_metadata:
                    # The to_simplified_dict method already includes the content,
                    # so we don't need to include it separately at the root level
                    result = {
                        "metadata": page.to_simplified_dict(),
                    }
                else:
                    # For backward compatibility, keep returning content directly
                    result = {"content": page.content}

                return [
                    TextContent(
                        type="text",
                        text=json.dumps(result, indent=2, ensure_ascii=False),
                    ),
                ]

            case "confluence_get_page_children":
                if not ctx or not ctx.confluence:
                    raise ConfluenceNotConfiguredError

                parent_id = arguments.get("parent_id")
                expand = arguments.get("expand", "version")
                limit = min(int(arguments.get("limit", 25)), 50)
                include_content = arguments.get("include_content", False)
                convert_to_markdown = arguments.get("convert_to_markdown", True)
                start = arguments.get("start", 0)

                # Add body.storage to expand if content is requested
                if include_content and "body" not in expand:
                    expand = f"{expand},body.storage" if expand else "body.storage"

                pages = None  # Initialize pages to None before try block

                try:
                    pages = ctx.confluence.get_page_children(
                        page_id=parent_id,
                        start=start,
                        limit=limit,
                        expand=expand,
                        convert_to_markdown=convert_to_markdown,
                    )

                    child_pages = [page.to_simplified_dict() for page in pages]

                    result = {
                        "parent_id": parent_id,
                        "total": len(child_pages),
                        "limit": limit,
                        "results": child_pages,
                    }

                except Exception as e:
                    # --- Error Handling ---
                    msg = f"Error getting/processing children for page ID {parent_id}"
                    logger.exception(msg)
                    result = {"error": f"Failed to get child pages: {e}"}

                return [
                    TextContent(
                        type="text",
                        text=json.dumps(
                            result,
                            indent=2,
                            ensure_ascii=False,
                        ),
                    ),
                ]

            case "confluence_get_page_ancestors":
                if not ctx or not ctx.confluence:
                    raise ConfluenceNotConfiguredError

                page_id = arguments.get("page_id")

                # Get the ancestor pages
                ancestors = ctx.confluence.get_page_ancestors(page_id)

                # Format results
                ancestor_pages = [page.to_simplified_dict() for page in ancestors]

                return [
                    TextContent(
                        type="text",
                        text=json.dumps(ancestor_pages, indent=2, ensure_ascii=False),
                    ),
                ]

            case "confluence_get_comments":
                if not ctx or not ctx.confluence:
                    raise ConfluenceNotConfiguredError

                page_id = arguments.get("page_id")
                comments = ctx.confluence.get_page_comments(page_id)

                # Format comments using their to_simplified_dict method if available
                formatted_comments = [format_comment(comment) for comment in comments]

                return [
                    TextContent(
                        type="text",
                        text=json.dumps(
                            formatted_comments,
                            indent=2,
                            ensure_ascii=False,
                        ),
                    ),
                ]

            case "confluence_create_page":
                if not ctx or not ctx.confluence:
                    raise ConfluenceNotConfiguredError

                # Write operation - check read-only mode
                if read_only:
                    return get_read_only_response("confluence_create_page")

                # Extract arguments
                space_key = arguments.get("space_key")
                title = arguments.get("title")
                content = arguments.get("content")
                parent_id = arguments.get("parent_id")

                # Create the page (with automatic markdown conversion)
                page = ctx.confluence.create_page(
                    space_key=space_key,
                    title=title,
                    body=content,
                    parent_id=parent_id,
                    is_markdown=True,
                )

                # Format the result
                result = page.to_simplified_dict()

                return [
                    TextContent(
                        type="text",
                        text=f"Page created successfully:\n{json.dumps(result, indent=2, ensure_ascii=False)}",
                    ),
                ]

            case "confluence_update_page":
                if not ctx or not ctx.confluence:
                    raise ConfluenceNotConfiguredError

                # Write operation - check read-only mode
                if read_only:
                    return get_read_only_response("confluence_update_page")

                page_id = arguments.get("page_id")
                title = arguments.get("title")
                content = arguments.get("content")
                is_minor_edit = arguments.get("is_minor_edit", False)
                version_comment = arguments.get("version_comment", "")

                if not page_id or not title or not content:
                    msg = "Missing required parameters: page_id, title, and content are required."
                    raise ValueError(
                        msg,
                    )

                # Update the page (with automatic markdown conversion)
                updated_page = ctx.confluence.update_page(
                    page_id=page_id,
                    title=title,
                    body=content,
                    is_minor_edit=is_minor_edit,
                    version_comment=version_comment,
                    is_markdown=True,
                )

                # Format results
                page_data = updated_page.to_simplified_dict()

                return [TextContent(type="text", text=json.dumps({"page": page_data}))]

            case "confluence_delete_page":
                if not ctx or not ctx.confluence:
                    raise ConfluenceNotConfiguredError

                # Write operation - check read-only mode
                if read_only:
                    return get_read_only_response("confluence_delete_page")

                page_id = arguments.get("page_id")

                if not page_id:
                    msg = "Missing required parameter: page_id is required."
                    raise ValueError(msg)

                try:
                    # Delete the page
                    result = ctx.confluence.delete_page(page_id=page_id)

                    # Format results - our fixed implementation now correctly returns True on success
                    if result:
                        response = {
                            "success": True,
                            "message": f"Page {page_id} deleted successfully",
                        }
                    else:
                        # This branch should rarely be hit with our updated implementation
                        # but we keep it for safety
                        response = {
                            "success": False,
                            "message": f"Unable to delete page {page_id}. The API request completed but deletion was unsuccessful.",
                        }

                    return [
                        TextContent(
                            type="text",
                            text=json.dumps(response, indent=2, ensure_ascii=False),
                        ),
                    ]
                except Exception as e:
                    # API call failed with an exception
                    logger.exception(
                        "Error deleting Confluence page %s:",
                        page_id,
                    )
                    return [
                        TextContent(
                            type="text",
                            text=json.dumps(
                                {
                                    "success": False,
                                    "message": f"Error deleting page {page_id}",
                                    "error": str(e),
                                },
                                indent=2,
                                ensure_ascii=False,
                            ),
                        ),
                    ]

            case "confluence_attach_content":
                if not ctx or not ctx.confluence:
                    raise ConfluenceNotConfiguredError

                # Write operation - check read-only mode
                if read_only:
                    return get_read_only_response("confluence_attach_content")

                content = arguments.get("content")
                name = arguments.get("name")
                page_id = arguments.get("page_id")

                if not content or not name or not page_id:
                    return [
                        TextContent(
                            type="text",
                            text="Error: Missing required parameters: content, name, and page_id are required.",
                        ),
                    ]

                try:
                    page = ctx.confluence.attach_content(
                        content=content,
                        name=name,
                        page_id=page_id,
                    )
                    page_data = page.to_simplified_dict()
                    return [
                        TextContent(
                            type="text",
                            text=json.dumps(
                                page_data,
                                indent=2,
                                ensure_ascii=False,
                            ),
                        ),
                    ]
                except ApiError as e:
                    return [
                        TextContent(
                            type="text",
                            text=f"Confluence API Error when trying to attach content {name} to page {page_id}: {e!s}",
                        ),
                    ]
                except RequestException as e:
                    return [
                        TextContent(
                            type="text",
                            text=f"Network error when trying to attach content {name} to page {page_id}: {e!s}",
                        ),
                    ]

            # Jira operations
            case "jira_get_issue":
                if not ctx or not ctx.jira:
                    raise JiraNotConfiguredError

                issue_key = arguments.get("issue_key")
                fields = arguments.get(
                    "fields",
                    "summary,description,status,assignee,reporter,labels,priority,created,updated,issuetype",
                )
                expand = arguments.get("expand")
                comment_limit = arguments.get("comment_limit", 10)
                properties = arguments.get("properties")
                update_history = arguments.get("update_history", True)

                issue = ctx.jira.get_issue(
                    issue_key,
                    fields=fields,
                    expand=expand,
                    comment_limit=comment_limit,
                    properties=properties,
                    update_history=update_history,
                )

                result = {"content": issue.to_simplified_dict()}

                return [
                    TextContent(
                        type="text",
                        text=json.dumps(result, indent=2, ensure_ascii=False),
                    ),
                ]

            case "jira_search":
                if not ctx or not ctx.jira:
                    raise JiraNotConfiguredError

                jql = arguments.get("jql")
                fields = arguments.get(
                    "fields",
                    "summary,description,status,assignee,reporter,labels,priority,created,updated,issuetype",
                )
                limit = min(int(arguments.get("limit", 10)), 50)
                projects_filter = arguments.get("projects_filter")
                start_at = int(arguments.get("startAt", 0))  # Get startAt

                search_result = ctx.jira.search_issues(
                    jql,
                    fields=fields,
                    limit=limit,
                    start=start_at,  # Pass start_at here
                    projects_filter=projects_filter,
                )

                # Format results using the to_simplified_dict method
                issues = [issue.to_simplified_dict() for issue in search_result.issues]

                # Include metadata in the response
                response = {
                    "total": search_result.total,
                    "start_at": search_result.start_at,
                    "max_results": search_result.max_results,
                    "issues": issues,
                }

                return [
                    TextContent(
                        type="text",
                        text=json.dumps(response, indent=2, ensure_ascii=False),
                    ),
                ]

            case "jira_get_project_issues":
                if not ctx or not ctx.jira:
                    raise JiraNotConfiguredError

                project_key = arguments.get("project_key")
                limit = min(int(arguments.get("limit", 10)), 50)
                start_at = int(arguments.get("startAt", 0))  # Get startAt

                search_result = ctx.jira.get_project_issues(
                    project_key,
                    start=start_at,
                    limit=limit,
                )

                # Format results
                issues = [issue.to_simplified_dict() for issue in search_result.issues]

                # Include metadata in the response
                response = {
                    "total": search_result.total,
                    "start_at": search_result.start_at,
                    "max_results": search_result.max_results,
                    "issues": issues,
                }

                return [
                    TextContent(
                        type="text",
                        text=json.dumps(response, indent=2, ensure_ascii=False),
                    ),
                ]

            case "jira_get_epic_issues":
                if not ctx or not ctx.jira:
                    raise JiraNotConfiguredError

                epic_key = arguments.get("epic_key")
                limit = min(int(arguments.get("limit", 10)), 50)
                start_at = int(arguments.get("startAt", 0))  # Get startAt

                # Get issues linked to the epic
                search_result = ctx.jira.get_epic_issues(
                    epic_key,
                    start=start_at,
                    limit=limit,
                )

                # Format results
                issues = [issue.to_simplified_dict() for issue in search_result.issues]

                # Include metadata in the response
                response = {
                    "total": search_result.total,
                    "start_at": search_result.start_at,
                    "max_results": search_result.max_results,
                    "issues": issues,
                }

                return [
                    TextContent(
                        type="text",
                        text=json.dumps(response, indent=2, ensure_ascii=False),
                    ),
                ]

            case "jira_get_transitions":
                if not ctx or not ctx.jira:
                    raise JiraNotConfiguredError

                issue_key = arguments.get("issue_key")

                # Get available transitions
                transitions = ctx.jira.get_available_transitions(issue_key)

                # Format transitions
                formatted_transitions = [
                    {
                        "id": transition.get("id"),
                        "name": transition.get("name"),
                        "to_status": transition.get("to", {}).get("name"),
                    }
                    for transition in transitions
                ]

                return [
                    TextContent(
                        type="text",
                        text=json.dumps(
                            formatted_transitions,
                            indent=2,
                            ensure_ascii=False,
                        ),
                    ),
                ]

            case "jira_get_worklog":
                if not ctx or not ctx.jira:
                    raise JiraNotConfiguredError

                issue_key = arguments.get("issue_key")

                # Get worklogs
                worklogs = ctx.jira.get_worklogs(issue_key)

                result = {"worklogs": worklogs}

                return [
                    TextContent(
                        type="text",
                        text=json.dumps(result, indent=2, ensure_ascii=False),
                    ),
                ]

            case "jira_download_attachments":
                if not ctx or not ctx.jira:
                    raise JiraNotConfiguredError

                issue_key = arguments.get("issue_key")
                target_dir = arguments.get("target_dir")

                if not issue_key:
                    msg = "Missing required parameter: issue_key"
                    raise ValueError(msg)
                if not target_dir:
                    msg = "Missing required parameter: target_dir"
                    raise ValueError(msg)

                # Download the attachments
                result = ctx.jira.download_issue_attachments(
                    issue_key=issue_key,
                    target_dir=target_dir,
                )

                return [
                    TextContent(
                        type="text",
                        text=json.dumps(result, indent=2, ensure_ascii=False),
                    ),
                ]

            case "jira_get_agile_boards":
                if not ctx or not ctx.jira:
                    raise JiraNotConfiguredError

                board_name = arguments.get("board_name")
                project_key = arguments.get("project_key")
                board_type = arguments.get("board_type")
                start_at = int(arguments.get("startAt", 0))
                limit = min(int(arguments.get("limit", 10)), 50)

                boards = ctx.jira.get_all_agile_boards_model(
                    board_name=board_name,
                    project_key=project_key,
                    board_type=board_type,
                    start=start_at,
                    limit=limit,
                )

                return [
                    TextContent(
                        type="text",
                        text=json.dumps(
                            [board.to_simplified_dict() for board in boards],
                            indent=2,
                            ensure_ascii=False,
                        ),
                    ),
                ]

            case "jira_get_board_issues":
                if not ctx or not ctx.jira:
                    raise JiraNotConfiguredError

                board_id = arguments.get("board_id")
                jql = arguments.get("jql")
                fields = arguments.get("fields", "*all")

                start_at = int(arguments.get("startAt", 0))
                limit = min(int(arguments.get("limit", 10)), 50)
                expand = arguments.get("expand", "version")

                search_result = ctx.jira.get_board_issues(
                    board_id=board_id,
                    jql=jql,
                    fields=fields,
                    start=start_at,
                    limit=limit,
                    expand=expand,
                )

                # Format results
                issues = [issue.to_simplified_dict() for issue in search_result.issues]

                # Include metadata in the response
                response = {
                    "total": search_result.total,
                    "start_at": search_result.start_at,
                    "max_results": search_result.max_results,
                    "issues": issues,
                }

                return [
                    TextContent(
                        type="text",
                        text=json.dumps(response, indent=2, ensure_ascii=False),
                    ),
                ]

            case "jira_get_sprints_from_board":
                if not ctx or not ctx.jira:
                    raise JiraNotConfiguredError

                board_id = arguments.get("board_id")
                state = arguments.get("state", "active")
                start_at = int(arguments.get("startAt", 0))
                limit = min(int(arguments.get("limit", 10)), 50)

                sprints = ctx.jira.get_all_sprints_from_board_model(
                    board_id=board_id,
                    state=state,
                    start=start_at,
                    limit=limit,
                )

                return [
                    TextContent(
                        type="text",
                        text=json.dumps(
                            [sprint.to_simplified_dict() for sprint in sprints],
                            indent=2,
                            ensure_ascii=False,
                        ),
                    ),
                ]

            case "jira_get_sprint_issues":
                if not ctx or not ctx.jira:
                    raise JiraNotConfiguredError

                sprint_id = arguments.get("sprint_id")
                fields = arguments.get("fields", "*all")
                start_at = int(arguments.get("startAt", 0))
                limit = min(int(arguments.get("limit", 10)), 50)

                search_result = ctx.jira.get_sprint_issues(
                    sprint_id=sprint_id,
                    fields=fields,
                    start=start_at,
                    limit=limit,
                )

                # Format results
                issues = [issue.to_simplified_dict() for issue in search_result.issues]

                # Include metadata in the response
                response = {
                    "total": search_result.total,
                    "start_at": search_result.start_at,
                    "max_results": search_result.max_results,
                    "issues": issues,
                }

                return [
                    TextContent(
                        type="text",
                        text=json.dumps(response, indent=2, ensure_ascii=False),
                    ),
                ]

            case "jira_create_issue":
                if not ctx or not ctx.jira:
                    raise JiraNotConfiguredError

                # Write operation - check read-only mode
                if read_only:
                    return get_read_only_response("jira_create_issue")

                # Extract required arguments
                project_key = arguments.get("project_key")
                summary = arguments.get("summary")
                issue_type = arguments.get("issue_type")

                # Extract optional arguments
                description = arguments.get("description", "")
                assignee = arguments.get("assignee")
                components = arguments.get("components")

                # Parse components from comma-separated string to list
                if components and isinstance(components, str):
                    # Split by comma and strip whitespace, removing empty entries
                    components = [
                        comp.strip() for comp in components.split(",") if comp.strip()
                    ]

                # Parse additional fields
                additional_fields = {}
                if arguments.get("additional_fields"):
                    try:
                        additional_fields = json.loads(
                            arguments.get("additional_fields"),
                        )
                    except json.JSONDecodeError:
                        raise InvalidJSONError(
                            field_name="additional_fields",
                        ) from json.JSONDecodeError

                # Create the issue
                issue = ctx.jira.create_issue(
                    project_key=project_key,
                    summary=summary,
                    issue_type=issue_type,
                    description=description,
                    assignee=assignee,
                    components=components,
                    **additional_fields,
                )

                result = issue.to_simplified_dict()

                return [
                    TextContent(
                        type="text",
                        text=f"Issue created successfully:\n{json.dumps(result, indent=2, ensure_ascii=False)}",
                    ),
                ]

            case "jira_update_issue":
                if not ctx or not ctx.jira:
                    raise JiraNotConfiguredError

                # Write operation - check read-only mode
                if read_only:
                    return get_read_only_response("jira_update_issue")

                # Extract arguments
                issue_key = arguments.get("issue_key")

                # Parse fields JSON
                fields = {}
                if arguments.get("fields"):
                    try:
                        fields = json.loads(arguments.get("fields"))
                    except json.JSONDecodeError:
                        raise InvalidJSONError(
                            field_name="fields",
                        ) from json.JSONDecodeError

                # Parse additional fields JSON
                additional_fields = {}
                if arguments.get("additional_fields"):
                    try:
                        additional_fields = json.loads(
                            arguments.get("additional_fields"),
                        )
                    except json.JSONDecodeError:
                        raise InvalidJSONError(
                            field_name="additional_fields",
                        ) from json.JSONDecodeError

                # Handle attachments if provided
                attachments = []
                if arguments.get("attachments"):
                    # Parse attachments - can be a single string or a list of strings
                    if isinstance(arguments.get("attachments"), str):
                        try:
                            # Try to parse as JSON array
                            parsed_attachments = json.loads(
                                arguments.get("attachments"),
                            )
                            if isinstance(parsed_attachments, list):
                                attachments = parsed_attachments
                            else:
                                # Single file path as a JSON string
                                attachments = [parsed_attachments]
                        except json.JSONDecodeError:
                            # Handle non-JSON string formats
                            if "," in arguments.get("attachments"):
                                # Split by comma and strip whitespace (supporting comma-separated list format)
                                attachments = [
                                    path.strip()
                                    for path in arguments.get("attachments").split(",")
                                ]
                            else:
                                # Plain string - single file path
                                attachments = [arguments.get("attachments")]
                    elif isinstance(arguments.get("attachments"), list):
                        # Already a list
                        attachments = arguments.get("attachments")

                    # Validate all paths exist
                    for path in attachments[:]:
                        if not Path(path).exists():
                            msg = f"Attachment file not found: {path}"
                            logger.warning(msg)
                            attachments.remove(path)

                try:
                    # Add attachments to additional_fields if any valid paths were found
                    if attachments:
                        additional_fields["attachments"] = attachments

                    # Update the issue - directly pass fields to JiraFetcher.update_issue
                    # instead of using fields as a parameter name
                    issue = ctx.jira.update_issue(
                        issue_key=issue_key,
                        **fields,
                        **additional_fields,
                    )

                    result = issue.to_simplified_dict()

                    # Include attachment results if available
                    if (
                        hasattr(issue, "custom_fields")
                        and "attachment_results" in issue.custom_fields
                    ):
                        result["attachment_results"] = issue.custom_fields[
                            "attachment_results"
                        ]

                    return [
                        TextContent(
                            type="text",
                            text=f"Issue updated successfully:\n{json.dumps(result, indent=2, ensure_ascii=False)}",
                        ),
                    ]
                except Exception as e:
                    return [
                        TextContent(
                            type="text",
                            text=f"Error updating issue {issue_key}: {e!s}",
                        ),
                    ]

            case "jira_delete_issue":
                if not ctx or not ctx.jira:
                    raise JiraNotConfiguredError

                # Write operation - check read-only mode
                if read_only:
                    return get_read_only_response("jira_delete_issue")

                issue_key = arguments.get("issue_key")

                # Delete the issue
                _ = ctx.jira.delete_issue(issue_key)

                result = {
                    "message": f"Issue {issue_key} has been deleted successfully.",
                }

                return [
                    TextContent(
                        type="text",
                        text=json.dumps(result, indent=2, ensure_ascii=False),
                    ),
                ]

            case "jira_add_comment":
                if not ctx or not ctx.jira:
                    raise JiraNotConfiguredError

                # Write operation - check read-only mode
                if read_only:
                    return get_read_only_response("jira_add_comment")

                issue_key = arguments.get("issue_key")
                comment = arguments.get("comment")

                # Add the comment
                result = ctx.jira.add_comment(issue_key, comment)

                return [
                    TextContent(
                        type="text",
                        text=json.dumps(result, indent=2, ensure_ascii=False),
                    ),
                ]

            case "jira_add_worklog":
                if not ctx or not ctx.jira:
                    raise JiraNotConfiguredError

                # Write operation - check read-only mode
                if read_only:
                    return get_read_only_response("jira_add_worklog")

                # Extract arguments
                issue_key = arguments.get("issue_key")
                time_spent = arguments.get("time_spent")
                comment = arguments.get("comment")
                started = arguments.get("started")

                # Add the worklog
                worklog = ctx.jira.add_worklog(
                    issue_key=issue_key,
                    time_spent=time_spent,
                    comment=comment,
                    started=started,
                )

                result = {"message": "Worklog added successfully", "worklog": worklog}

                return [
                    TextContent(
                        type="text",
                        text=json.dumps(result, indent=2, ensure_ascii=False),
                    ),
                ]

            case "jira_link_to_epic":
                if not ctx or not ctx.jira:
                    raise JiraNotConfiguredError

                # Write operation - check read-only mode
                if read_only:
                    return get_read_only_response("jira_link_to_epic")

                issue_key = arguments.get("issue_key")
                epic_key = arguments.get("epic_key")

                # Link the issue to the epic
                issue = ctx.jira.link_issue_to_epic(issue_key, epic_key)

                result = {
                    "message": f"Issue {issue_key} has been linked to epic {epic_key}.",
                    "issue": issue.to_simplified_dict(),
                }

                return [
                    TextContent(
                        type="text",
                        text=json.dumps(result, indent=2, ensure_ascii=False),
                    ),
                ]

            case "jira_transition_issue":
                if not ctx or not ctx.jira:
                    raise JiraNotConfiguredError

                # Write operation - check read-only mode
                if read_only:
                    return get_read_only_response("jira_transition_issue")

                # Extract arguments
                issue_key = arguments.get("issue_key")
                transition_id = arguments.get("transition_id")
                comment = arguments.get("comment")

                # Validate required parameters
                if not issue_key:
                    msg = "issue_key is required"
                    raise ValueError(msg)
                if not transition_id:
                    msg = "transition_id is required"
                    raise ValueError(msg)

                # Convert transition_id to integer if it's a numeric string
                # This ensures compatibility with the Jira API which expects integers
                if isinstance(transition_id, str) and transition_id.isdigit():
                    transition_id = int(transition_id)
                    logger.debug(
                        "Converted string transition_id to integer: %s",
                        transition_id,
                    )

                # Parse fields JSON
                fields = {}
                if arguments.get("fields"):
                    try:
                        fields = json.loads(arguments.get("fields"))
                    except json.JSONDecodeError:
                        raise InvalidJSONError(
                            field_name="fields",
                        ) from json.JSONDecodeError

                try:
                    # Transition the issue
                    issue = ctx.jira.transition_issue(
                        issue_key=issue_key,
                        transition_id=transition_id,
                        fields=fields,
                        comment=comment,
                    )

                    result = {
                        "message": f"Issue {issue_key} transitioned successfully",
                        "issue": issue.to_simplified_dict() if issue else None,
                    }

                    return [
                        TextContent(
                            type="text",
                            text=json.dumps(result, indent=2, ensure_ascii=False),
                        ),
                    ]
                except Exception as e:
                    # Provide a clear error message, especially for transition ID type issues
                    error_msg = str(e)
                    if "'transition' identifier must be an integer" in error_msg:
                        error_msg = (
                            f"Error transitioning issue {issue_key}: The Jira API requires transition IDs to be integers. "
                            f"Received transition ID '{transition_id}' of type {type(transition_id).__name__}. "
                            f"Please use the numeric ID value from jira_get_transitions."
                        )
                    else:
                        error_msg = f"Error transitioning issue {issue_key} with transition ID {transition_id}: {error_msg}"

                    logger.exception(error_msg)
                    return [
                        TextContent(
                            type="text",
                            text=error_msg,
                        ),
                    ]

            case _:
                msg = f"Unknown tool: {name}"
                raise ValueError(msg)

    except Exception as e:
        logger.exception("Tool execution error: %s", e)
        return [TextContent(type="text", text=f"Error: {e!s}")]


async def run_server(transport: str = "stdio", port: int = 8000) -> None:
    """Run the MCP Atlassian server with the specified transport."""
    if transport == "sse":
        from mcp.server.sse import SseServerTransport
        from starlette.applications import Starlette
        from starlette.requests import Request
        from starlette.routing import Mount, Route

        sse = SseServerTransport("/messages/")

        async def handle_sse(request: Request) -> None:
            async with sse.connect_sse(
                request.scope,
                request.receive,
                request._send,
            ) as streams:
                await app.run(
                    streams[0],
                    streams[1],
                    app.create_initialization_options(),
                )

        starlette_app = Starlette(
            debug=True,
            routes=[
                Route("/sse", endpoint=handle_sse),
                Mount("/messages/", app=sse.handle_post_message),
            ],
        )

        import uvicorn

        # Set up uvicorn config
        config = uvicorn.Config(starlette_app, host="0.0.0.0", port=port)  # noqa: S104
        server = uvicorn.Server(config)
        # Use server.serve() instead of run() to stay in the same event loop
        await server.serve()
    else:
        from mcp.server.stdio import stdio_server

        async with stdio_server() as (read_stream, write_stream):
            await app.run(
                read_stream,
                write_stream,
                app.create_initialization_options(),
            )
