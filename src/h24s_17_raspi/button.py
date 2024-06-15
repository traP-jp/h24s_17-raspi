import asyncio
import concurrent.futures
import logging
import sys
import time
from contextlib import contextmanager
from threading import Event
from typing import Any, Generator

import gpiod
from aiochannel import Channel

_log = logging.getLogger(__name__)


@contextmanager
def acquire_button(line_name: str) -> Generator[gpiod.Line, Any, None]:
    chip = gpiod.Chip("gpiochip0", gpiod.Chip.OPEN_BY_NAME)
    line = chip.find_line(line_name)
    try:
        line.request(consumer="h24s17", type=gpiod.LINE_REQ_DIR_IN)
        yield line
    finally:
        line.release()


def watch_button(loop: asyncio.AbstractEventLoop, button: gpiod.Line, tx: Channel[int], terminate: Event) -> None:
    last_value = button.get_value()
    while not terminate.is_set():
        value = button.get_value()
        if value != last_value:
            asyncio.run_coroutine_threadsafe(tx.put(value), loop)
        last_value = value
        time.sleep(0.1)


async def listen_button_event(rx: Channel[int]) -> None:
    async for v in rx:
        _log.info(f"button={v}")


async def sleep_then_set(delay: float, event: Event) -> None:
    try:
        await asyncio.sleep(delay)
    finally:
        event.set()


async def bwatch() -> None:
    loop = asyncio.get_event_loop()
    ch: Channel[int] = Channel(10)
    term = Event()
    with acquire_button("GPIO26") as button, concurrent.futures.ThreadPoolExecutor() as pool:
        _log.debug("exec watch-button")
        watch_fut = loop.run_in_executor(pool, watch_button, loop, button, ch, term)
        _log.debug("create listen task")
        listen_task = asyncio.create_task(listen_button_event(ch))
        sleep_task = asyncio.create_task(sleep_then_set(30, term))
        await asyncio.wait([watch_fut, listen_task, sleep_task], return_when=asyncio.FIRST_COMPLETED)
    _log.info("button watch loop done!")


def run_watch_button() -> None:
    logging.basicConfig(stream=sys.stderr, level=logging.INFO)
    _log.setLevel(logging.DEBUG)
    asyncio.run(bwatch())
