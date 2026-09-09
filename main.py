"""L0 入口：CLI（serve / register）+ app 工厂，零领域知识。"""

import argparse


def create_app():
    from contextlib import asynccontextmanager

    from fastapi import FastAPI

    import deps
    from api import pipelines_router, system_router, tasks_router, tools_router

    @asynccontextmanager
    async def lifespan(app):
        db = deps.get_db()
        db.open()
        db.apply_migrations()
        scheduler = deps.get_scheduler()
        scheduler.start()
        yield
        scheduler.stop()
        db.close()

    app = FastAPI(title="CommAND", version="0.1.0", lifespan=lifespan)
    app.include_router(system_router.router, prefix="/api")
    app.include_router(tools_router.router, prefix="/api")
    app.include_router(tasks_router.router, prefix="/api")
    app.include_router(pipelines_router.router, prefix="/api")
    app.include_router(pipelines_router.runs_router, prefix="/api")
    return app


def cmd_serve(args: argparse.Namespace) -> None:
    import uvicorn

    import deps

    config = deps.get_config()
    uvicorn.run("main:create_app", factory=True, host=config.host, port=config.port)


def cmd_register(args: argparse.Namespace) -> None:
    import json

    import deps

    try:
        result = deps.get_registry_service().scan()
        print(json.dumps(result, ensure_ascii=False, indent=2))
    finally:
        deps.get_db().close()


def main() -> None:
    parser = argparse.ArgumentParser(prog="command")
    sub = parser.add_subparsers(dest="command", required=True)
    serve = sub.add_parser("serve", help="启动 API + worker（本地单用户单进程）")
    serve.set_defaults(func=cmd_serve)
    register = sub.add_parser("register", help="扫描 tools/ 校验并注册小工具")
    register.set_defaults(func=cmd_register)
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
