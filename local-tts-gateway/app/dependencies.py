from fastapi import Request


def get_provider_registry(request: Request):
    return request.app.state.provider_registry


def get_process_manager(request: Request):
    return request.app.state.process_manager
