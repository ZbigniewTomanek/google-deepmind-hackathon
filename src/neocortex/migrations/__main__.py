"""CLI entry point: python -m neocortex.migrations"""

import asyncio
import sys

from loguru import logger

from neocortex.config import PostgresConfig
from neocortex.migrations.runner import MigrationRunner
from neocortex.postgres_service import PostgresService


async def main() -> None:
    config = PostgresConfig()
    pg = PostgresService(config)
    await pg.connect()
    try:
        runner = MigrationRunner(pg)
        public_count = await runner.run_public()
        graph_count = await runner.run_graph_schemas()
        logger.info(
            "migration_summary",
            public_applied=public_count,
            graph_applied=graph_count,
        )
        print(f"Migrations complete: {public_count} public, {graph_count} graph-schema")
    finally:
        await pg.disconnect()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.exit(130)
