"""Reference FastMCP client for the process-toolkit server in server.py.

This is NOT meant to be the third-party consumer's own client -- it exists
to prove the server actually works end-to-end, and to double as living
usage documentation. Any MCP client in any language can call the same
tools the same way.

Usage:
    uv run python client.py demo                         # against the default
                                                           # http://127.0.0.1:8765/mcp
    uv run python client.py demo --url http://host:port/mcp
    uv run python client.py demo --stdio                 # launches `python server.py
                                                           # --transport stdio` itself
"""

import argparse
import asyncio
import base64
import os

from fastmcp import Client

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_URL = "http://127.0.0.1:8765/mcp"


def _client_for(args: argparse.Namespace) -> Client:
    if args.stdio:
        return Client({
            "mcpServers": {
                "process-toolkit": {
                    "command": "python",
                    "args": [os.path.join(THIS_DIR, "server.py"), "--transport", "stdio"],
                }
            }
        })
    return Client(args.url)


async def run_demo(args: argparse.Namespace) -> None:
    session_id = args.session_id

    async with _client_for(args) as client:
        schema_types = (await client.call_tool("list_schema_types")).data
        print(f"schema_types: {schema_types}")

        template = (await client.call_tool("load_template", {"schema_type": "togaf"})).data
        template["document_metadata"].update({
            "document_id": "ARCH-DEMO-001",
            "system_name": "Checkout Service",
            "title": "Checkout Service",
        })
        # The template ships one example requirement item with blank
        # fields as a shape reference -- clear both lists so this demo's
        # validation doesn't fail on an intentionally-empty placeholder.
        template["architecture_requirements_specification"]["functional_requirements"] = []
        template["architecture_requirements_specification"]["non_functional_requirements"] = []

        validation = (await client.call_tool(
            "validate_json", {"schema_type": "togaf", "data": template},
        )).data
        print(f"validate_json: valid={validation['valid']} issues={validation['issues']}")
        assert validation["valid"], "demo data failed validation -- fix the demo, not the server"

        persisted = (await client.call_tool(
            "persist_json", {"schema_type": "togaf", "data": template, "session_id": session_id},
        )).data
        print(f"persist_json: {persisted['message']}")

        generated = (await client.call_tool(
            "generate_document",
            {"schema_type": "togaf", "session_id": session_id, "variant": "vision"},
        )).data
        print(f"generate_document: {generated['message']}")

        out_dir = os.path.join(THIS_DIR, "demo_downloads")
        os.makedirs(out_dir, exist_ok=True)
        for doc in generated["documents"]:
            artifact = (await client.call_tool(
                "get_artifact", {"filename": doc["filename"], "session_id": session_id},
            )).data
            out_path = os.path.join(out_dir, artifact["filename"])
            with open(out_path, "wb") as f:
                f.write(base64.b64decode(artifact["base64"]))
            print(f"wrote {out_path} ({artifact['size_bytes']} bytes)")

        artifacts = (await client.call_tool(
            "list_artifacts", {"session_id": session_id},
        )).data
        print(f"list_artifacts: {[a['filename'] for a in artifacts]}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    demo = sub.add_parser("demo", help="Run the end-to-end togaf vision document demo.")
    demo.add_argument("--url", default=DEFAULT_URL, help=f"Streamable HTTP MCP URL (default: {DEFAULT_URL})")
    demo.add_argument("--stdio", action="store_true", help="Launch server.py over stdio instead of connecting via HTTP.")
    demo.add_argument("--session-id", dest="session_id", default="client-demo")

    args = parser.parse_args()
    if args.command == "demo":
        asyncio.run(run_demo(args))


if __name__ == "__main__":
    main()
