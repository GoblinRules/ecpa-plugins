"""Synthetic read-only connector used to prove onboarding without another API key."""
from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

app=FastMCP('ECPA sample')

@app.tool(annotations=ToolAnnotations(readOnlyHint=True,destructiveHint=False,openWorldHint=False))
def status() -> dict:
    """Return a fixed synthetic service status; reads no files, credentials or network."""
    return {'service':'sample','status':'ready','synthetic':True}

@app.tool(annotations=ToolAnnotations(readOnlyHint=True,destructiveHint=False,openWorldHint=False))
def echo(value: str) -> dict:
    """Echo at most 200 characters for concurrent-session isolation tests."""
    return {'value':value[:200],'synthetic':True}

if __name__=='__main__':app.run()
