from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import PackMetadataModel


class PackRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_type(self, journey_type: str) -> PackMetadataModel | None:
        stmt = select(PackMetadataModel).where(PackMetadataModel.journey_type == journey_type)
        return await self.session.scalar(stmt)

    async def list_all(self) -> list[PackMetadataModel]:
        stmt = select(PackMetadataModel).order_by(PackMetadataModel.journey_type.asc())
        result = await self.session.scalars(stmt)
        return list(result.all())

    async def upsert(
        self,
        journey_type: str,
        schema_version: str,
        display_name: str,
        description: str,
        icon: str,
        flagship_demo: bool,
        manifest_yaml: str | None = None,
    ) -> PackMetadataModel:
        pack = await self.get_by_type(journey_type)
        now = datetime.now(UTC)
        if pack:
            pack.schema_version = schema_version
            pack.display_name = display_name
            pack.description = description
            pack.icon = icon
            pack.flagship_demo = flagship_demo
            pack.manifest_yaml = manifest_yaml
            pack.updated_at = now
        else:
            pack = PackMetadataModel(
                journey_type=journey_type,
                schema_version=schema_version,
                display_name=display_name,
                description=description,
                icon=icon,
                flagship_demo=flagship_demo,
                manifest_yaml=manifest_yaml,
                updated_at=now,
            )
            self.session.add(pack)
        await self.session.flush()
        return pack
