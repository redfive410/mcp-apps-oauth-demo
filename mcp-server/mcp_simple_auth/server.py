"""
MCP Resource Server with Token Introspection.

This server validates tokens via Authorization Server introspection and serves MCP resources.
Demonstrates RFC 9728 Protected Resource Metadata for AS/RS separation.

NOTE: this is a simplified example for demonstration purposes.
This is not a production-ready implementation.
"""

import datetime
import logging
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Literal

import click
import httpx
import mcp.types as types
from pydantic import AnyHttpUrl
from pydantic_settings import BaseSettings, SettingsConfigDict
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from mcp.server.auth.settings import AuthSettings
from mcp.server.fastmcp.server import FastMCP

from .token_verifier import IntrospectionTokenVerifier

logger = logging.getLogger(__name__)


class ResourceServerSettings(BaseSettings):
    """Settings for the MCP Resource Server."""

    model_config = SettingsConfigDict(env_prefix="MCP_RESOURCE_")

    # Server settings
    host: str = "localhost"
    port: int = 8001
    server_url: AnyHttpUrl = AnyHttpUrl("http://localhost:8001/mcp")

    # Authorization Server settings
    auth_server_url: AnyHttpUrl = AnyHttpUrl("http://localhost:9000")
    auth_server_introspection_endpoint: str = "http://localhost:9000/introspect"
    # No user endpoint needed - we get user data from token introspection

    # MCP settings
    mcp_scope: str = "user"

    # RFC 8707 resource validation
    oauth_strict: bool = False

    # TODO(Marcelo): Is this even needed? I didn't have time to check.
    def __init__(self, **data: Any):
        """Initialize settings with values from environment variables."""
        super().__init__(**data)


def create_resource_server(settings: ResourceServerSettings) -> FastMCP:
    """
    Create MCP Resource Server with token introspection.

    This server:
    1. Provides protected resource metadata (RFC 9728)
    2. Validates tokens via Authorization Server introspection
    3. Serves MCP tools and resources
    """
    # Create token verifier for introspection with RFC 8707 resource validation
    token_verifier = IntrospectionTokenVerifier(
        introspection_endpoint=settings.auth_server_introspection_endpoint,
        server_url=str(settings.server_url),
        validate_resource=settings.oauth_strict,  # Only validate when --oauth-strict is set
    )

    # Create FastMCP server as a Resource Server
    app = FastMCP(
        name="MCP Resource Server",
        instructions="Resource Server that validates tokens via Authorization Server introspection",
        host=settings.host,
        port=settings.port,
        debug=True,
        stateless_http=True,
        # Auth configuration for RS mode
        token_verifier=token_verifier,
        auth=AuthSettings(
            issuer_url=settings.auth_server_url,
            required_scopes=[settings.mcp_scope],
            resource_server_url=settings.server_url,
        ),
    )

    # --- Widget setup ---
    WIDGET_URI = "ui://widget/tool-output.html"
    MIME_TYPE = "text/html;profile=mcp-app"

    @lru_cache(maxsize=None)
    def _load_widget_html() -> str:
        assets_dir = Path(__file__).resolve().parent.parent / "widget" / "assets"
        html_path = assets_dir / "tool-output.html"
        if html_path.exists():
            return html_path.read_text(encoding="utf8")
        raise FileNotFoundError(
            f"Widget HTML not found at {html_path}. "
            "Run `cd widget && pnpm install && pnpm run build` first."
        )

    def _tool_meta() -> Dict[str, Any]:
        return {"ui": {"resourceUri": WIDGET_URI}}

    # --- Low-level handlers for tools (to support _meta.ui) ---

    @app._mcp_server.list_tools()
    async def _list_tools() -> List[types.Tool]:
        meta = _tool_meta()
        return [
            types.Tool(
                name="get_time",
                title="Get Time",
                description=(
                    "Get the current server time.\n\n"
                    "This tool demonstrates that system information can be protected "
                    "by OAuth authentication. User must be authenticated to access it."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {},
                    "additionalProperties": False,
                },
                _meta=meta,
            ),
            types.Tool(
                name="get_meaning_of_67",
                title="Get Meaning of 67",
                description=(
                    "Gets the meaning of 67.\n\n"
                    "This tool demonstrates that system information can be protected "
                    "by OAuth authentication. User must be authenticated to access it."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "user_context": {
                            "type": "string",
                            "default": "",
                            "description": "Optional context about user preferences, income, etc.",
                        }
                    },
                    "additionalProperties": False,
                },
                _meta=meta,
            ),
        ]

    @app._mcp_server.list_resources()
    async def _list_resources() -> List[types.Resource]:
        return [
            types.Resource(
                name="tool-output-widget",
                title="Tool Output Widget",
                uri=WIDGET_URI,
                description="Widget that renders tool output as markdown",
                mimeType=MIME_TYPE,
                _meta={"ui": {"prefersBorder": True}},
            )
        ]

    async def _handle_read_resource(req: types.ReadResourceRequest) -> types.ServerResult:
        if str(req.params.uri) != WIDGET_URI:
            return types.ServerResult(
                types.ReadResourceResult(
                    contents=[],
                    _meta={"error": f"Unknown resource: {req.params.uri}"},
                )
            )
        contents = [
            types.TextResourceContents(
                uri=WIDGET_URI,
                mimeType=MIME_TYPE,
                text=_load_widget_html(),
                _meta={"ui": {"prefersBorder": True}},
            )
        ]
        return types.ServerResult(types.ReadResourceResult(contents=contents))

    async def _handle_call_tool(req: types.CallToolRequest) -> types.ServerResult:
        tool_name = req.params.name
        arguments = req.params.arguments or {}

        if tool_name == "get_time":
            now = datetime.datetime.now()
            result = {
                "current_time": now.isoformat(),
                "timezone": "UTC",
                "timestamp": now.timestamp(),
                "formatted": now.strftime("%Y-%m-%d %H:%M:%S"),
            }
        elif tool_name == "get_meaning_of_67":
            user_context = arguments.get("user_context", "")
            result = {
                "definition": "67 does not mean anything other than...the kids are alright.",
                "user_context": user_context,
            }
        else:
            return types.ServerResult(
                types.CallToolResult(
                    content=[types.TextContent(type="text", text=f"Unknown tool: {tool_name}")],
                    isError=True,
                )
            )

        return types.ServerResult(
            types.CallToolResult(
                content=[types.TextContent(type="text", text=str(result))],
                structuredContent=result,
            )
        )

    app._mcp_server.request_handlers[types.CallToolRequest] = _handle_call_tool
    app._mcp_server.request_handlers[types.ReadResourceRequest] = _handle_read_resource

    # CORS headers for browser-based clients like MCP Inspector
    cors_headers = {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
        "Access-Control-Allow-Headers": "*",
        "Access-Control-Expose-Headers": "*",
    }

    # Add OAuth well-known endpoints using FastMCP's custom_route decorator
    # RFC 9728: For resource at /mcp, metadata must be at /.well-known/oauth-protected-resource/mcp
    @app.custom_route("/.well-known/oauth-protected-resource/mcp", methods=["GET", "OPTIONS"])
    async def oauth_protected_resource_mcp(request: Request) -> JSONResponse:
        """RFC 9728 Protected Resource Metadata endpoint (path-based)."""
        if request.method == "OPTIONS":
            return JSONResponse({}, headers=cors_headers)
        return JSONResponse({
            "resource": str(settings.server_url),
            "authorization_servers": [str(settings.auth_server_url)],
            "scopes_supported": [settings.mcp_scope],
            "bearer_methods_supported": ["header"],
            "resource_documentation": "https://modelcontextprotocol.io",
        }, headers=cors_headers)

    # Also serve at root for backwards compatibility
    @app.custom_route("/.well-known/oauth-protected-resource", methods=["GET", "OPTIONS"])
    async def oauth_protected_resource(request: Request) -> JSONResponse:
        """RFC 9728 Protected Resource Metadata endpoint (root)."""
        if request.method == "OPTIONS":
            return JSONResponse({}, headers=cors_headers)
        return JSONResponse({
            "resource": str(settings.server_url),
            "authorization_servers": [str(settings.auth_server_url)],
            "scopes_supported": [settings.mcp_scope],
            "bearer_methods_supported": ["header"],
            "resource_documentation": "https://modelcontextprotocol.io",
        }, headers=cors_headers)

    @app.custom_route("/.well-known/oauth-authorization-server", methods=["GET", "OPTIONS"])
    async def oauth_authorization_server(request: Request) -> JSONResponse:
        """Proxy Authorization Server Metadata from the AS."""
        if request.method == "OPTIONS":
            return JSONResponse({}, headers=cors_headers)
        auth_server_base = str(settings.auth_server_url).rstrip("/")
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(
                    f"{auth_server_base}/.well-known/oauth-authorization-server",
                    timeout=10.0,
                )
                if response.status_code == 200:
                    return JSONResponse(response.json(), headers=cors_headers)
            except Exception as e:
                logger.warning(f"Failed to fetch AS metadata: {e}")
            # If AS doesn't have this endpoint or failed, return minimal metadata
            return JSONResponse({
                "issuer": auth_server_base,
                "authorization_endpoint": f"{auth_server_base}/authorize",
                "token_endpoint": f"{auth_server_base}/token",
                "introspection_endpoint": f"{auth_server_base}/introspect",
                "scopes_supported": [settings.mcp_scope],
                "response_types_supported": ["code"],
                "grant_types_supported": ["authorization_code"],
                "token_endpoint_auth_methods_supported": ["client_secret_post", "client_secret_basic"],
            }, headers=cors_headers)

    @app.custom_route("/.well-known/openid-configuration", methods=["GET", "OPTIONS"])
    async def openid_configuration(request: Request) -> JSONResponse:
        """Proxy OpenID Configuration from the AS."""
        if request.method == "OPTIONS":
            return JSONResponse({}, headers=cors_headers)
        auth_server_base = str(settings.auth_server_url).rstrip("/")
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(
                    f"{auth_server_base}/.well-known/openid-configuration",
                    timeout=10.0,
                )
                if response.status_code == 200:
                    return JSONResponse(response.json(), headers=cors_headers)
            except Exception as e:
                logger.warning(f"Failed to fetch OIDC config: {e}")
            # If AS doesn't have OIDC or failed, return minimal OAuth metadata
            return JSONResponse({
                "issuer": auth_server_base,
                "authorization_endpoint": f"{auth_server_base}/authorize",
                "token_endpoint": f"{auth_server_base}/token",
                "scopes_supported": [settings.mcp_scope, "openid"],
                "response_types_supported": ["code"],
                "grant_types_supported": ["authorization_code"],
            }, headers=cors_headers)

    return app

@click.command()
@click.option("--port", default=8001, help="Port to listen on")
@click.option("--host", default="localhost", help="Host to bind to")
@click.option("--auth-server", default="http://localhost:9000", help="Authorization Server URL")
@click.option("--server-url", default=None, help="Public server URL (required for HTTPS)")
@click.option(
    "--transport",
    default="streamable-http",
    type=click.Choice(["sse", "streamable-http"]),
    help="Transport protocol to use ('sse' or 'streamable-http')",
)
@click.option(
    "--oauth-strict",
    is_flag=True,
    help="Enable RFC 8707 resource validation",
)
def main(port: int, host: str, auth_server: str, server_url: str | None, transport: Literal["sse", "streamable-http"], oauth_strict: bool) -> int:
    """
    Run the MCP Resource Server.

    This server:
    - Provides RFC 9728 Protected Resource Metadata
    - Validates tokens via Authorization Server introspection
    - Serves MCP tools requiring authentication

    Must be used with a running Authorization Server.
    """
    import os

    logging.basicConfig(level=logging.INFO)

    # Allow Cloud Run to override port via PORT env var
    port = int(os.environ.get("PORT", port))

    # Get server URL from env var or CLI option
    # For Cloud Run deployments, this should be the public HTTPS URL
    server_url = os.environ.get("MCP_RESOURCE_SERVER_URL", server_url)
    if not server_url:
        # Default to local development URL
        server_url = f"http://{host}:{port}/mcp"

    # Get auth server URL from env var or CLI option
    auth_server = os.environ.get("MCP_RESOURCE_AUTH_SERVER_URL", auth_server)

    try:
        # Parse auth server URL
        auth_server_url = AnyHttpUrl(auth_server)

        # Create settings
        settings = ResourceServerSettings(
            host=host,
            port=port,
            server_url=AnyHttpUrl(server_url),
            auth_server_url=auth_server_url,
            auth_server_introspection_endpoint=f"{auth_server}/introspect",
            oauth_strict=oauth_strict,
        )
    except ValueError as e:
        logger.error(f"Configuration error: {e}")
        logger.error("Make sure to provide a valid Authorization Server URL")
        return 1

    try:
        mcp_server = create_resource_server(settings)

        logger.info(f"🚀 MCP Resource Server running on {settings.server_url}")
        logger.info(f"🔑 Using Authorization Server: {settings.auth_server_url}")

        # Get the Starlette app and wrap it with CORS middleware for browser-based clients
        if transport == "streamable-http":
            starlette_app = mcp_server.streamable_http_app()
        else:
            starlette_app = mcp_server.sse_app()

        # Add CORS middleware for browser-based clients like MCP Inspector
        # NOTE: When allow_credentials=True, you CANNOT use wildcards (*) for origins
        # The CORSMiddleware automatically reflects the Origin header when configured this way
        starlette_app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=False,  # Set to False to allow wildcard origins
            allow_methods=["*"],
            allow_headers=["*"],
            expose_headers=["WWW-Authenticate", "Content-Type", "X-Request-Id"],
        )

        # Run with uvicorn directly
        import uvicorn
        uvicorn.run(starlette_app, host=host, port=port)
        logger.info("Server stopped")
        return 0
    except Exception:
        logger.exception("Server error")
        return 1


if __name__ == "__main__":
    main()  # type: ignore[call-arg]
