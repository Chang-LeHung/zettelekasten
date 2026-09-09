"""Shared adapters used by asynchronous application routes."""

from collections.abc import Callable

from starlette.concurrency import run_in_threadpool


async def run_sync[**ParametersT, ResultT](
    function: Callable[ParametersT, ResultT],
    *args: ParametersT.args,
    **kwargs: ParametersT.kwargs,
) -> ResultT:
    """Run one synchronous storage operation outside the ASGI event loop."""
    return await run_in_threadpool(function, *args, **kwargs)
