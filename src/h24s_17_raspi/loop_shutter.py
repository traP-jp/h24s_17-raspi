import asyncio
import concurrent.futures
import io
import logging
import sys
import time

import aiofiles
from aiochannel import Channel
from picamera2 import Picamera2
from PIL.Image import Image

from .camera import acquire_camera

_log = logging.getLogger(__name__)


def trigger(
    loop: asyncio.AbstractEventLoop, camera: Picamera2, tx: Channel[Image], delay: float = 1, count: int = 10
) -> None:
    for i in range(count):
        _log.debug(f"read image {i}")
        image = camera.capture_image()
        assert isinstance(image, Image)
        _log.debug(f"put image {i}")
        asyncio.run_coroutine_threadsafe(tx.put(image), loop)
        time.sleep(delay)


async def receive(rx: Channel[Image]) -> None:
    i = 0
    async for image in rx:
        assert isinstance(image, Image)
        _log.debug(f"receive image {i}")
        with io.BytesIO() as b:
            image.save(b, format="jpeg")
            buf = b.getvalue()
        async with aiofiles.open(f"out/demo{i}.jpeg", mode="wb") as f:
            await asyncio.shield(f.write(buf))
        _log.info(f"saved image to out/demo{i}.jpeg")
        i += 1


async def shutter() -> None:
    loop = asyncio.get_event_loop()
    ch: Channel[Image] = Channel()
    with acquire_camera() as camera, concurrent.futures.ThreadPoolExecutor() as pool:
        trig_fut = loop.run_in_executor(pool, trigger, loop, camera, ch)
        recv_task = asyncio.create_task(receive(ch))
        await asyncio.wait([trig_fut, recv_task], return_when=asyncio.FIRST_COMPLETED)
    _log.info("shutter loop done!")


def loop_shutter() -> None:
    logging.basicConfig(stream=sys.stderr, level=logging.INFO)
    _log.setLevel(logging.DEBUG)
    asyncio.run(shutter())
