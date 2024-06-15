import asyncio
import logging
from threading import Event

import gpiod
from aiochannel import Channel
from picamera2 import Picamera2

from .button import acquire_button
from .camera import acquire_camera

_log = logging.getLogger(__name__)


def serve_camera(
    loop: asyncio.AbstractEventLoop,
    button: gpiod.Line,
    camera: Picamera2,
    tx: Channel[bytes],
    terminate: Event,
    delay: float = 0.1,
) -> None:
    import io
    import time

    from PIL.Image import Image

    last_value = button.get_value()
    while not terminate.is_set():
        time.sleep(delay)
        value = button.get_value()
        if value == last_value:
            continue
        last_value = value
        _log.debug(f"button value = {value}")
        if value == 0:
            continue
        image = camera.capture_image()
        assert isinstance(image, Image)
        with io.BytesIO() as b:
            image.save(b, format="jpeg")
            buf = b.getvalue()
        asyncio.run_coroutine_threadsafe(tx.put(buf), loop)


async def receive_camera(raspi_token: str, post_url: str, rx: Channel[bytes]) -> None:
    import aiohttp

    headers = {"Content-Type": "image/jpeg", "X-Raspi-Token": raspi_token}
    async for image in rx:
        async with (
            aiohttp.ClientSession() as session,
            session.post(post_url, headers=headers, data=image) as response,
        ):
            _log.info(f"request response: {response.status}")


async def client(delay: float = 0.1) -> None:
    import concurrent.futures
    import os
    import signal

    raspi_token = os.environ.get("RASPI_TOKEN", "raspitoken")
    post_url = os.environ.get("POST_IMAGE_URL", "localhost:1323")
    button_pin = os.environ.get("BUTTON", "GPIO26")
    loop = asyncio.get_event_loop()
    ch: Channel[bytes] = Channel(10)
    terminate = Event()

    def quit() -> None:
        terminate.set()

    loop.add_signal_handler(signal.SIGINT, quit)
    loop.add_signal_handler(signal.SIGKILL, quit)

    _log.debug("starting raspi client...")
    with (
        acquire_button(button_pin) as button,
        acquire_camera() as camera,
        concurrent.futures.ThreadPoolExecutor() as pool,
    ):
        serve = loop.run_in_executor(pool, serve_camera, loop, button, camera, ch, terminate, delay)
        receive = asyncio.create_task(receive_camera(raspi_token, post_url, ch))
        await asyncio.wait([serve, receive], return_when=asyncio.FIRST_COMPLETED)


def run_client() -> None:
    import sys

    logging.basicConfig(stream=sys.stderr, level=logging.INFO)
    _log.setLevel(logging.INFO)
    asyncio.run(client())
