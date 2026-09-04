import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from app.entities.value_info import ValueInfo
from app.repositories.es.value_es_repository import ValueESRepository


class ValueESRepositoryTest(unittest.IsolatedAsyncioTestCase):
    async def test_ensure_index_uses_configured_name_and_analyzer(self):
        indices = SimpleNamespace(
            exists=AsyncMock(return_value=False),
            create=AsyncMock(),
            put_settings=AsyncMock(),
            refresh=AsyncMock(),
        )
        cluster = SimpleNamespace(
            health=AsyncMock(return_value={"status": "yellow"}),
        )
        client = SimpleNamespace(indices=indices, cluster=cluster)
        repository = ValueESRepository(
            client,
            index_name="configured-index",
            analyzer="standard",
        )

        await repository.ensure_index()

        indices.create.assert_awaited_once_with(
            index="configured-index",
            settings={"number_of_shards": 1, "number_of_replicas": 0},
            mappings=repository.es_index_mappings,
        )
        cluster.health.assert_awaited_once_with(
            index="configured-index",
            wait_for_status="yellow",
            timeout="10s",
        )
        self.assertEqual(
            "standard",
            repository.es_index_mappings["properties"]["value"]["analyzer"],
        )

    async def test_ensure_index_updates_replicas_for_existing_index(self):
        indices = SimpleNamespace(
            exists=AsyncMock(return_value=True),
            create=AsyncMock(),
            put_settings=AsyncMock(),
        )
        cluster = SimpleNamespace(
            health=AsyncMock(return_value={"status": "green"}),
        )
        repository = ValueESRepository(
            SimpleNamespace(indices=indices, cluster=cluster),
            index_name="configured-index",
            number_of_replicas=0,
        )

        await repository.ensure_index()

        indices.put_settings.assert_awaited_once_with(
            index="configured-index",
            settings={"number_of_replicas": 0},
        )
        indices.create.assert_not_awaited()

    async def test_ensure_index_rejects_unassigned_primary_shard(self):
        indices = SimpleNamespace(
            exists=AsyncMock(return_value=True),
            put_settings=AsyncMock(),
        )
        cluster = SimpleNamespace(
            health=AsyncMock(return_value={"status": "red"}),
        )
        repository = ValueESRepository(
            SimpleNamespace(indices=indices, cluster=cluster),
            index_name="configured-index",
        )

        with self.assertRaisesRegex(RuntimeError, "主分片未分配"):
            await repository.ensure_index()

    async def test_upsert_raises_when_bulk_contains_item_errors(self):
        indices = SimpleNamespace(refresh=AsyncMock())
        client = SimpleNamespace(
            indices=indices,
            bulk=AsyncMock(return_value={
                "errors": True,
                "items": [{"index": {"error": {"reason": "write failed"}}}],
            }),
        )
        repository = ValueESRepository(client, index_name="configured-index")

        with self.assertRaisesRegex(RuntimeError, "ES批量写入失败"):
            await repository.upsert([
                ValueInfo(id="table.column.value", value="value", column_id="table.column")
            ])

        indices.refresh.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
