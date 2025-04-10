from .schema import ToolDefinition, Toolbox

# Define Confluence tools
CONFLUENCE_TOOLS = [
    ToolDefinition(
        name="confluence_search",
        description="Search Confluence content using simple terms or CQL",
        input_schema={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query - can be either a simple text (e.g. 'project documentation') or a CQL query string. Examples of CQL:\n"
                    "- Basic search: 'type=page AND space=DEV'\n"
                    "- Personal space search: 'space=\"~username\"' (note: personal space keys starting with ~ must be quoted)\n"
                    "- Search by title: 'title~\"Meeting Notes\"'\n"
                    "- Recent content: 'created >= \"2023-01-01\"'\n"
                    "- Content with specific label: 'label=documentation'\n"
                    "- Recently modified content: 'lastModified > startOfMonth(\"-1M\")'\n"
                    "- Content modified this year: 'creator = currentUser() AND lastModified > startOfYear()'\n"
                    "- Content you contributed to recently: 'contributor = currentUser() AND lastModified > startOfWeek()'\n"
                    "- Content watched by user: 'watcher = \"user@domain.com\" AND type = page'\n"
                    '- Exact phrase in content: \'text ~ "\\"Urgent Review Required\\"" AND label = "pending-approval"\'\n'
                    '- Title wildcards: \'title ~ "Minutes*" AND (space = "HR" OR space = "Marketing")\'\n'
                    'Note: Special identifiers need proper quoting in CQL: personal space keys (e.g., "~username"), reserved words, numeric IDs, and identifiers with special characters.',
                },
                "limit": {
                    "type": "number",
                    "description": "Maximum number of results (1-50)",
                    "default": 10,
                    "minimum": 1,
                    "maximum": 50,
                },
                "spaces_filter": {
                    "type": "string",
                    "description": "Comma-separated list of space keys to filter results by. Overrides the environment variable CONFLUENCE_SPACES_FILTER if provided.",
                },
            },
            "required": ["query"],
        },
    ),
    ToolDefinition(
        name="confluence_get_page",
        description="Get content of a specific Confluence page by ID",
        input_schema={
            "type": "object",
            "properties": {
                "page_id": {
                    "type": "string",
                    "description": "Confluence page ID (numeric ID, can be found in the page URL). "
                    "For example, in the URL 'https://example.atlassian.net/wiki/spaces/TEAM/pages/123456789/Page+Title', "
                    "the page ID is '123456789'",
                },
                "include_metadata": {
                    "type": "boolean",
                    "description": "Whether to include page metadata such as creation date, last update, version, and labels",
                    "default": True,
                },
                "convert_to_markdown": {
                    "type": "boolean",
                    "description": "Whether to convert page to markdown (true) or keep it in raw HTML format (false). Raw HTML can reveal macros (like dates) not visible in markdown, but CAUTION: using HTML significantly increases token usage in AI responses.",
                    "default": True,
                },
            },
            "required": ["page_id"],
        },
    ),
    ToolDefinition(
        name="confluence_get_page_children",
        description="Get child pages of a specific Confluence page",
        input_schema={
            "type": "object",
            "properties": {
                "parent_id": {
                    "type": "string",
                    "description": "The ID of the parent page whose children you want to retrieve",
                },
                "expand": {
                    "type": "string",
                    "description": "Fields to expand in the response (e.g., 'version', 'body.storage')",
                    "default": "version",
                },
                "limit": {
                    "type": "number",
                    "description": "Maximum number of child pages to return (1-50)",
                    "default": 25,
                    "minimum": 1,
                    "maximum": 50,
                },
                "include_content": {
                    "type": "boolean",
                    "description": "Whether to include the page content in the response",
                    "default": False,
                },
            },
            "required": ["parent_id"],
        },
    ),
    ToolDefinition(
        name="confluence_get_page_ancestors",
        description="Get ancestor (parent) pages of a specific Confluence page",
        input_schema={
            "type": "object",
            "properties": {
                "page_id": {
                    "type": "string",
                    "description": "The ID of the page whose ancestors you want to retrieve",
                },
            },
            "required": ["page_id"],
        },
    ),
    ToolDefinition(
        name="confluence_get_comments",
        description="Get comments for a specific Confluence page",
        input_schema={
            "type": "object",
            "properties": {
                "page_id": {
                    "type": "string",
                    "description": "Confluence page ID (numeric ID, can be parsed from URL, "
                    "e.g. from 'https://example.atlassian.net/wiki/spaces/TEAM/pages/123456789/Page+Title' "
                    "-> '123456789')",
                }
            },
            "required": ["page_id"],
        },
    ),
    # Write operations
    ToolDefinition(
        name="confluence_create_page",
        description="Create a new Confluence page",
        input_schema={
            "type": "object",
            "properties": {
                "space_key": {
                    "type": "string",
                    "description": "The key of the space to create the page in "
                    "(usually a short uppercase code like 'DEV', 'TEAM', or 'DOC')",
                },
                "title": {
                    "type": "string",
                    "description": "The title of the page",
                },
                "content": {
                    "type": "string",
                    "description": "The content of the page in Markdown format. "
                    "Supports headings, lists, tables, code blocks, and other "
                    "Markdown syntax",
                },
                "parent_id": {
                    "type": "string",
                    "description": "Optional parent page ID. If provided, this page "
                    "will be created as a child of the specified page",
                },
            },
            "required": ["space_key", "title", "content"],
        },
        is_write_operation=True,
    ),
    ToolDefinition(
        name="confluence_update_page",
        description="Update an existing Confluence page",
        input_schema={
            "type": "object",
            "properties": {
                "page_id": {
                    "type": "string",
                    "description": "The ID of the page to update",
                },
                "title": {
                    "type": "string",
                    "description": "The new title of the page",
                },
                "content": {
                    "type": "string",
                    "description": "The new content of the page in Markdown format",
                },
                "is_minor_edit": {
                    "type": "boolean",
                    "description": "Whether this is a minor edit",
                    "default": False,
                },
                "version_comment": {
                    "type": "string",
                    "description": "Optional comment for this version",
                    "default": "",
                },
            },
            "required": ["page_id", "title", "content"],
        },
        is_write_operation=True,
    ),
    ToolDefinition(
        name="confluence_delete_page",
        description="Delete an existing Confluence page",
        input_schema={
            "type": "object",
            "properties": {
                "page_id": {
                    "type": "string",
                    "description": "The ID of the page to delete",
                },
            },
            "required": ["page_id"],
        },
        is_write_operation=True,
    ),
    ToolDefinition(
        name="confluence_attach_content",
        description="Attach content to a Confluence page",
        input_schema={
            "type": "object",
            "properties": {
                "content": {
                    "type": "string",
                    "format": "binary",
                    "description": "The content to attach (bytes)",
                },
                "name": {
                    "type": "string",
                    "description": "The name of the attachment",
                },
                "page_id": {
                    "type": "string",
                    "description": "The ID of the page to attach the content to",
                },
            },
            "required": ["content", "name", "page_id"],
        },
        is_write_operation=True,
    ),
]

CONFLUENCE_TOOLBOX = Toolbox(tool_definitions=CONFLUENCE_TOOLS)
