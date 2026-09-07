# 模块职责：版本化元数据能力包，统一维护 Schema、指标、关系与检索契约。
"""Versioned metadata registry for the Olist V1 warehouse."""

from app.metadata.catalog import MetadataCatalog, load_catalog

__all__ = ["MetadataCatalog", "load_catalog"]
