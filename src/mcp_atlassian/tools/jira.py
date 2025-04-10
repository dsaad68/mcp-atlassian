from typing import List

from .schema import ToolDefinition, Toolbox

# Define Jira tools
JIRA_TOOLS = [
    ToolDefinition(
        name="jira_get_issue",
        description="Get details of a specific Jira issue including its Epic links and relationship information",
        input_schema={
            "type": "object",
            "properties": {
                "issue_key": {
                    "type": "string",
                    "description": "Jira issue key (e.g., 'PROJ-123')",
                },
                "fields": {
                    "type": "string",
                    "description": "Fields to return. Can be a comma-separated list (e.g., 'summary,status,customfield_10010'), '*all' for all fields (including custom fields), or omitted for essential fields only",
                    "default": "summary,description,status,assignee,reporter,labels,priority,created,updated,issuetype",
                },
                "expand": {
                    "type": "string",
                    "description": (
                        "Optional fields to expand. Examples: 'renderedFields' "
                        "(for rendered content), 'transitions' (for available "
                        "status transitions), 'changelog' (for history)"
                    ),
                    "default": None,
                },
                "comment_limit": {
                    "type": "integer",
                    "description": (
                        "Maximum number of comments to include "
                        "(0 or null for no comments)"
                    ),
                    "minimum": 0,
                    "maximum": 100,
                    "default": 10,
                },
                "properties": {
                    "type": "string",
                    "description": "A comma-separated list of issue properties to return",
                    "default": None,
                },
                "update_history": {
                    "type": "boolean",
                    "description": "Whether to update the issue view history for the requesting user",
                    "default": True,
                },
            },
            "required": ["issue_key"],
        },
    ),
    ToolDefinition(
        name="jira_search",
        description="Search Jira issues using JQL (Jira Query Language)",
        input_schema={
            "type": "object",
            "properties": {
                "jql": {
                    "type": "string",
                    "description": "JQL query string (Jira Query Language). Examples:\n"
                    '- Find Epics: "issuetype = Epic AND project = PROJ"\n'
                    '- Find issues in Epic: "parent = PROJ-123"\n'
                    "- Find by status: \"status = 'In Progress' AND project = PROJ\"\n"
                    '- Find by assignee: "assignee = currentUser()"\n'
                    '- Find recently updated: "updated >= -7d AND project = PROJ"\n'
                    '- Find by label: "labels = frontend AND project = PROJ"\n'
                    '- Find by priority: "priority = High AND project = PROJ"',
                },
                "fields": {
                    "type": "string",
                    "description": (
                        "Comma-separated fields to return in the results. "
                        "Use '*all' for all fields, or specify individual "
                        "fields like 'summary,status,assignee,priority'"
                    ),
                    "default": "summary,description,status,assignee,reporter,labels,priority,created,updated,issuetype",
                },
                "limit": {
                    "type": "number",
                    "description": "Maximum number of results (1-50)",
                    "default": 10,
                    "minimum": 1,
                    "maximum": 50,
                },
                "startAt": {
                    "type": "number",
                    "description": "Starting index for pagination (0-based)",
                    "default": 0,
                    "minimum": 0,
                },
                "projects_filter": {
                    "type": "string",
                    "description": "Comma-separated list of project keys to filter results by. Overrides the environment variable JIRA_PROJECTS_FILTER if provided.",
                },
            },
            "required": ["jql"],
        },
    ),
    ToolDefinition(
        name="jira_get_project_issues",
        description="Get all issues for a specific Jira project",
        input_schema={
            "type": "object",
            "properties": {
                "project_key": {
                    "type": "string",
                    "description": "The project key",
                },
                "limit": {
                    "type": "number",
                    "description": "Maximum number of results (1-50)",
                    "default": 10,
                    "minimum": 1,
                    "maximum": 50,
                },
                "startAt": {
                    "type": "number",
                    "description": "Starting index for pagination (0-based)",
                    "default": 0,
                    "minimum": 0,
                },
            },
            "required": ["project_key"],
        },
    ),
    ToolDefinition(
        name="jira_get_epic_issues",
        description="Get all issues linked to a specific epic",
        input_schema={
            "type": "object",
            "properties": {
                "epic_key": {
                    "type": "string",
                    "description": "The key of the epic (e.g., 'PROJ-123')",
                },
                "limit": {
                    "type": "number",
                    "description": "Maximum number of issues to return (1-50)",
                    "default": 10,
                    "minimum": 1,
                    "maximum": 50,
                },
                "startAt": {
                    "type": "number",
                    "description": "Starting index for pagination (0-based)",
                    "default": 0,
                    "minimum": 0,
                },
            },
            "required": ["epic_key"],
        },
    ),
    ToolDefinition(
        name="jira_get_transitions",
        description="Get available status transitions for a Jira issue",
        input_schema={
            "type": "object",
            "properties": {
                "issue_key": {
                    "type": "string",
                    "description": "Jira issue key (e.g., 'PROJ-123')",
                },
            },
            "required": ["issue_key"],
        },
    ),
    ToolDefinition(
        name="jira_get_worklog",
        description="Get worklog entries for a Jira issue",
        input_schema={
            "type": "object",
            "properties": {
                "issue_key": {
                    "type": "string",
                    "description": "Jira issue key (e.g., 'PROJ-123')",
                },
            },
            "required": ["issue_key"],
        },
    ),
    ToolDefinition(
        name="jira_download_attachments",
        description="Download attachments from a Jira issue",
        input_schema={
            "type": "object",
            "properties": {
                "issue_key": {
                    "type": "string",
                    "description": "Jira issue key (e.g., 'PROJ-123')",
                },
                "target_dir": {
                    "type": "string",
                    "description": "Directory where attachments should be saved",
                },
            },
            "required": ["issue_key", "target_dir"],
        },
    ),
    ToolDefinition(
        name="jira_get_agile_boards",
        description="Get jira agile boards by name, project key, or type",
        input_schema={
            "type": "object",
            "properties": {
                "board_name": {
                    "type": "string",
                    "description": "The name of board, support fuzzy search",
                },
                "project_key": {
                    "type": "string",
                    "description": "Jira project key (e.g., 'PROJ-123')",
                },
                "board_type": {
                    "type": "string",
                    "description": "The type of jira board (e.g., 'scrum', 'kanban')",
                },
                "startAt": {
                    "type": "number",
                    "description": "Starting index for pagination (0-based)",
                    "default": 0,
                },
                "limit": {
                    "type": "number",
                    "description": "Maximum number of results (1-50)",
                    "default": 10,
                    "minimum": 1,
                    "maximum": 50,
                },
            },
        },
    ),
    ToolDefinition(
        name="jira_get_board_issues",
        description="Get all issues linked to a specific board",
        input_schema={
            "type": "object",
            "properties": {
                "board_id": {
                    "type": "string",
                    "description": "The id of the board (e.g., '1001')",
                },
                "jql": {
                    "type": "string",
                    "description": "JQL query string (Jira Query Language). Examples:\n"
                    '- Find Epics: "issuetype = Epic AND project = PROJ"\n'
                    '- Find issues in Epic: "parent = PROJ-123"\n'
                    "- Find by status: \"status = 'In Progress' AND project = PROJ\"\n"
                    '- Find by assignee: "assignee = currentUser()"\n'
                    '- Find recently updated: "updated >= -7d AND project = PROJ"\n'
                    '- Find by label: "labels = frontend AND project = PROJ"\n'
                    '- Find by priority: "priority = High AND project = PROJ"',
                },
                "fields": {
                    "type": "string",
                    "description": (
                        "Comma-separated fields to return in the results. "
                        "Use '*all' for all fields, or specify individual "
                        "fields like 'summary,status,assignee,priority'"
                    ),
                    "default": "*all",
                },
                "startAt": {
                    "type": "number",
                    "description": "Starting index for pagination (0-based)",
                    "default": 0,
                },
                "limit": {
                    "type": "number",
                    "description": "Maximum number of results (1-50)",
                    "default": 10,
                    "minimum": 1,
                    "maximum": 50,
                },
                "expand": {
                    "type": "string",
                    "description": "Fields to expand in the response (e.g., 'version', 'body.storage')",
                    "default": "version",
                },
            },
            "required": ["board_id", "jql"],
        },
    ),
    ToolDefinition(
        name="jira_get_sprints_from_board",
        description="Get jira sprints from board by state",
        input_schema={
            "type": "object",
            "properties": {
                "board_id": {
                    "type": "string",
                    "description": "The id of board (e.g., '1000')",
                },
                "state": {
                    "type": "string",
                    "description": "Sprint state (e.g., 'active', 'future', 'closed')",
                },
                "startAt": {
                    "type": "number",
                    "description": "Starting index for pagination (0-based)",
                    "default": 0,
                },
                "limit": {
                    "type": "number",
                    "description": "Maximum number of results (1-50)",
                    "default": 10,
                    "minimum": 1,
                    "maximum": 50,
                },
            },
        },
    ),
    ToolDefinition(
        name="jira_get_sprint_issues",
        description="Get jira issues from sprint",
        input_schema={
            "type": "object",
            "properties": {
                "sprint_id": {
                    "type": "string",
                    "description": "The id of sprint (e.g., '10001')",
                },
                "fields": {
                    "type": "string",
                    "description": (
                        "Comma-separated fields to return in the results. "
                        "Use '*all' for all fields, or specify individual "
                        "fields like 'summary,status,assignee,priority'"
                    ),
                    "default": "*all",
                },
                "startAt": {
                    "type": "number",
                    "description": "Starting index for pagination (0-based)",
                    "default": 0,
                },
                "limit": {
                    "type": "number",
                    "description": "Maximum number of results (1-50)",
                    "default": 10,
                    "minimum": 1,
                    "maximum": 50,
                },
            },
            "required": ["sprint_id"],
        },
    ),
    # Write operations
    ToolDefinition(
        name="jira_create_issue",
        description="Create a new Jira issue with optional Epic link or parent for subtasks",
        input_schema={
            "type": "object",
            "properties": {
                "project_key": {
                    "type": "string",
                    "description": (
                        "The JIRA project key (e.g. 'PROJ', 'DEV', 'SUPPORT'). "
                        "This is the prefix of issue keys in your project. "
                        "Never assume what it might be, always ask the user."
                    ),
                },
                "summary": {
                    "type": "string",
                    "description": "Summary/title of the issue",
                },
                "issue_type": {
                    "type": "string",
                    "description": (
                        "Issue type (e.g. 'Task', 'Bug', 'Story', 'Epic', 'Subtask'). "
                        "The available types depend on your project configuration. "
                        "For subtasks, use 'Subtask' (not 'Sub-task') and include parent in additional_fields."
                    ),
                },
                "assignee": {
                    "type": "string",
                    "description": "Assignee of the ticket (accountID, full name or e-mail)",
                    "default": None,
                },
                "description": {
                    "type": "string",
                    "description": "Issue description",
                    "default": "",
                },
                "components": {
                    "type": "string",
                    "description": "Comma-separated list of component names to assign (e.g., 'Frontend,API')",
                    "default": "",
                },
                "additional_fields": {
                    "type": "string",
                    "description": (
                        "Optional JSON string of additional fields to set. "
                        "Examples:\n"
                        '- Set priority: {"priority": {"name": "High"}}\n'
                        '- Add labels: {"labels": ["frontend", "urgent"]}\n'
                        '- Link to parent (for any issue type): {"parent": "PROJ-123"}\n'
                        '- Set Fix Version/s: {"fixVersions": [{"id": "10020"}]}\n'
                        '- Custom fields: {"customfield_10010": "value"}'
                    ),
                    "default": "{}",
                },
            },
            "required": ["project_key", "summary", "issue_type"],
        },
        is_write_operation=True,
    ),
    ToolDefinition(
        name="jira_update_issue",
        description="Update an existing Jira issue including changing status, adding Epic links, updating fields, etc.",
        input_schema={
            "type": "object",
            "properties": {
                "issue_key": {
                    "type": "string",
                    "description": "Jira issue key (e.g., 'PROJ-123')",
                },
                "fields": {
                    "type": "string",
                    "description": (
                        "A valid JSON object of fields to update as a string. "
                        'Example: \'{"summary": "New title", "description": "Updated description", '
                        '"priority": {"name": "High"}, "assignee": {"name": "john.doe"}}\''
                    ),
                },
                "additional_fields": {
                    "type": "string",
                    "description": "Optional JSON string of additional fields to update. Use this for custom fields or more complex updates.",
                    "default": "{}",
                },
                "attachments": {
                    "type": "string",
                    "description": "Optional JSON string or comma-separated list of file paths to attach to the issue. "
                    'Example: "/path/to/file1.txt,/path/to/file2.txt" or "["/path/to/file1.txt","/path/to/file2.txt"]"',
                },
            },
            "required": ["issue_key", "fields"],
        },
        is_write_operation=True,
    ),
    ToolDefinition(
        name="jira_delete_issue",
        description="Delete an existing Jira issue",
        input_schema={
            "type": "object",
            "properties": {
                "issue_key": {
                    "type": "string",
                    "description": "Jira issue key (e.g. PROJ-123)",
                },
            },
            "required": ["issue_key"],
        },
        is_write_operation=True,
    ),
    ToolDefinition(
        name="jira_add_comment",
        description="Add a comment to a Jira issue",
        input_schema={
            "type": "object",
            "properties": {
                "issue_key": {
                    "type": "string",
                    "description": "Jira issue key (e.g., 'PROJ-123')",
                },
                "comment": {
                    "type": "string",
                    "description": "Comment text in Markdown format",
                },
            },
            "required": ["issue_key", "comment"],
        },
        is_write_operation=True,
    ),
    ToolDefinition(
        name="jira_add_worklog",
        description="Add a worklog entry to a Jira issue",
        input_schema={
            "type": "object",
            "properties": {
                "issue_key": {
                    "type": "string",
                    "description": "Jira issue key (e.g., 'PROJ-123')",
                },
                "time_spent": {
                    "type": "string",
                    "description": (
                        "Time spent in Jira format. Examples: "
                        "'1h 30m' (1 hour and 30 minutes), "
                        "'1d' (1 day), '30m' (30 minutes), "
                        "'4h' (4 hours)"
                    ),
                },
                "comment": {
                    "type": "string",
                    "description": "Optional comment for the worklog in Markdown format",
                },
                "started": {
                    "type": "string",
                    "description": (
                        "Optional start time in ISO format. "
                        "If not provided, the current time will be used. "
                        "Example: '2023-08-01T12:00:00.000+0000'"
                    ),
                },
            },
            "required": ["issue_key", "time_spent"],
        },
        is_write_operation=True,
    ),
    ToolDefinition(
        name="jira_link_to_epic",
        description="Link an existing issue to an epic",
        input_schema={
            "type": "object",
            "properties": {
                "issue_key": {
                    "type": "string",
                    "description": "The key of the issue to link (e.g., 'PROJ-123')",
                },
                "epic_key": {
                    "type": "string",
                    "description": "The key of the epic to link to (e.g., 'PROJ-456')",
                },
            },
            "required": ["issue_key", "epic_key"],
        },
        is_write_operation=True,
    ),
    ToolDefinition(
        name="jira_transition_issue",
        description="Transition a Jira issue to a new status",
        input_schema={
            "type": "object",
            "properties": {
                "issue_key": {
                    "type": "string",
                    "description": "Jira issue key (e.g., 'PROJ-123')",
                },
                "transition_id": {
                    "type": "string",
                    "description": (
                        "ID of the transition to perform. Use the jira_get_transitions tool first "
                        "to get the available transition IDs for the issue. "
                        "Example values: '11', '21', '31'"
                    ),
                },
                "fields": {
                    "type": "string",
                    "description": (
                        "JSON string of fields to update during the transition. "
                        "Some transitions require specific fields to be set. "
                        'Example: \'{"resolution": {"name": "Fixed"}}\''
                    ),
                    "default": "{}",
                },
                "comment": {
                    "type": "string",
                    "description": (
                        "Comment to add during the transition (optional). "
                        "This will be visible in the issue history."
                    ),
                },
            },
            "required": ["issue_key", "transition_id"],
        },
        is_write_operation=True,
    ),
]


JIRA_TOOLBOX = Toolbox(tool_definitions=JIRA_TOOLS)
