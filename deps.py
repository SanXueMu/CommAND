"""L2 装配：单例工厂注入，测试可整体替换；只装配不使用。"""

from functools import lru_cache

from config import Config, load_config
from core.runner import Runner
from core.scheduler import Scheduler
from services.dispatch_service import DispatchService
from services.pipeline_service import PipelineService
from services.registry_service import RegistryService
from store.db import Db
from store.event_repo import EventRepo
from store.key_repo import KeyRepo
from store.site_repo import SiteRepo
from store.pipeline_repo import PipelineRepo
from store.run_event_repo import RunEventRepo
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
def get_pipeline_repo() -> PipelineRepo:
    return PipelineRepo(get_db())


def get_run_event_repo() -> RunEventRepo:
    return RunEventRepo(get_db())


@lru_cache(maxsize=1)
def get_key_repo() -> KeyRepo:
    return KeyRepo(get_db())


def get_site_repo() -> SiteRepo:
    return SiteRepo(get_db())


@lru_cache(maxsize=1)
def get_registry_service() -> RegistryService:
    return RegistryService(db=get_db(), tools_dir=get_config().tools_dir, tool_repo=get_tool_repo())


@lru_cache(maxsize=1)
def get_dispatch_service() -> DispatchService:
    return DispatchService(
        db=get_db(),
        task_repo=get_task_repo(),
        tool_repo=get_tool_repo(),
        event_repo=get_event_repo(),
        scheduler=get_scheduler(),
    )


@lru_cache(maxsize=1)
def get_runner() -> Runner:
    return Runner()


@lru_cache(maxsize=1)
def get_scheduler() -> Scheduler:
    return Scheduler(
        db=get_db(),
        runner=get_runner(),
        task_repo=get_task_repo(),
        tool_repo=get_tool_repo(),
        event_repo=get_event_repo(),
        config=get_config(),
        # 惰性解析打断 dispatch→scheduler→pipeline→dispatch 构造环
        on_task_done=lambda task: get_pipeline_service().advance(task),
        key_repo=get_key_repo(),
    )


@lru_cache(maxsize=1)
def get_pipeline_service() -> PipelineService:
    return PipelineService(
        db=get_db(),
        pipeline_repo=get_pipeline_repo(),
        task_repo=get_task_repo(),
        tool_repo=get_tool_repo(),
        dispatch_service=get_dispatch_service(),
        run_event_repo=get_run_event_repo(),
    )
