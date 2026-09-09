"""L2 装配：单例工厂注入，测试可整体替换；只装配不使用。"""

from functools import lru_cache

from config import Config, load_config
from services.dispatch_service import DispatchService
from services.pipeline_service import PipelineService
from services.registry_service import RegistryService
from store.db import Db
from store.event_repo import EventRepo
from store.task_repo import TaskRepo
from store.tool_repo import ToolRepo


@lru_cache(maxsize=1)
def get_config() -> Config:
    return load_config()


@lru_cache(maxsize=1)
def get_db() -> Db:
    return Db(get_config().database_url)


@lru_cache(maxsize=1)
def get_tool_repo() -> ToolRepo:
    return ToolRepo(get_db())


@lru_cache(maxsize=1)
def get_task_repo() -> TaskRepo:
    return TaskRepo(get_db())


@lru_cache(maxsize=1)
def get_event_repo() -> EventRepo:
    return EventRepo(get_db())


@lru_cache(maxsize=1)
def get_registry_service() -> RegistryService:
    return RegistryService(db=get_db(), tools_dir=get_config().tools_dir, tool_repo=get_tool_repo())


@lru_cache(maxsize=1)
def get_dispatch_service() -> DispatchService:
    return DispatchService(db=get_db(), task_repo=get_task_repo(), tool_repo=get_tool_repo())


@lru_cache(maxsize=1)
def get_pipeline_service() -> PipelineService:
    return PipelineService(db=get_db(), task_repo=get_task_repo())
