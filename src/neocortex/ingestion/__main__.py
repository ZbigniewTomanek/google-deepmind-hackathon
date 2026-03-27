import uvicorn

from neocortex.ingestion.app import create_app
from neocortex.logging import setup_logging
from neocortex.mcp_settings import MCPSettings


def main():
    setup_logging(service_name="ingestion")
    settings = MCPSettings()
    app = create_app(settings)
    uvicorn.run(app, host="0.0.0.0", port=8001)


if __name__ == "__main__":
    main()
