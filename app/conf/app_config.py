from dataclasses import dataclass
from pathlib import Path
from typing import cast

from omegaconf import OmegaConf


# 日志配置
@dataclass
class File:
    enable: bool
    level: str
    path: str
    rotation: str
    retention: str


@dataclass
class Console:
    enable: bool
    level: str


@dataclass
class LoggingConfig:
    file: File
    console: Console


# 数据库配置
@dataclass
class DBConfig:
    host: str
    port: int
    user: str
    password: str
    database: str


@dataclass
class QdrantConfig:
    host: str
    port: int
    embedding_size: int


@dataclass
class EmbeddingConfig:
    base_url: str
    model: str
    api_key_env: str
    timeout: float
    max_retries: int


@dataclass
class ESConfig:
    host: str
    port: int
    index_name: str
    analyzer: str = "standard"
    number_of_shards: int = 1
    number_of_replicas: int = 0


@dataclass
class LLMConfig:
    base_url: str
    model: str
    api_key_env: str
    timeout: float
    max_retries: int


@dataclass
class AppConfig:
    logging: LoggingConfig
    db_meta: DBConfig
    db_dw: DBConfig
    qdrant: QdrantConfig
    embedding: EmbeddingConfig
    es: ESConfig
    llm: LLMConfig

# 1.从本地获取yaml文件得到OmegaConf对象
context = OmegaConf.load(Path(__file__).parents[2] / 'conf' / 'app_config.yaml')
# 2.通过dataclass对象得到OmegaConf对象
structured = OmegaConf.structured(AppConfig)

# 3.合并内容跟结构化对象，转为dataclass对象
app_config = cast(
    AppConfig, OmegaConf.to_object(OmegaConf.merge(structured, context))
)
