import asyncio
import io
import logging
import time
from threading import Event

import gpiod
from aiochannel import Channel
from picamera2 import Picamera2
from PIL.Image import Image

from .button import acquire_button
from .camera import acquire_camera

_log = logging.getLogger(__name__)


def serve_button(button: gpiod.Line, button_pressed: Event, terminate: Event, delay: float = 0.1) -> None:
    last_value = button.get_value()
    while not terminate.is_set():
        time.sleep(delay)
        value = button.get_value()
        if value == last_value:
            continue
        last_value = value
        _log.debug(f"button {value=}")
        if value == 0 or button_pressed.is_set():
            continue
        _log.debug("button pressed")
        button_pressed.set()


def serve_camera(
    loop: asyncio.AbstractEventLoop,
    camera: Picamera2,
    image_tx: Channel[bytes],
    button_pressed: Event,
    terminate: Event,
    delay: float = 0.1,
) -> None:
    while not terminate.is_set():
        time.sleep(delay)
        if not button_pressed.is_set():
            continue
        _log.info("capture image")
        image = camera.capture_image()
        assert isinstance(image, Image)
        with io.BytesIO() as b:
            image.save(b, format="jpeg")
            buf = b.getvalue()
        _log.debug("send image")
        asyncio.run_coroutine_threadsafe(image_tx.put(buf), loop)
        button_pressed.clear()


async def post_image(raspi_secret: str, post_url: str, image: bytes) -> None:
    import aiofiles
    import aiohttp

    _log.debug("sending request")
    headers = {"Content-Type": "image/jpeg", "X-Raspi-Secret": raspi_secret}
    async with (
        aiohttp.ClientSession() as session,
        session.post(post_url, headers=headers, data=image) as response,
        aiofiles.open("out/recv.jpeg", mode="wb") as f,
    ):
        _log.info(f"request response: {response.status}")
        _log.debug("save image to out/recv.jpeg")
        await f.write(image)


async def receive_camera(raspi_secret: str, post_url: str, rx: Channel[bytes]) -> None:
    async for image in rx:
        _log.debug("receive image")
        try:
            await post_image(raspi_secret, post_url, image)
        except Exception as e:
            _log.warn(f"err: {e}")


async def client(delay: float = 0.1) -> None:
    import concurrent.futures
    import os
    import signal

    loop = asyncio.get_event_loop()
    terminate = Event()

    def quit() -> None:
        _log.info("quit handler")
        terminate.set()

    loop.add_signal_handler(signal.SIGINT, quit)

    _log.debug("starting raspi client...")
    raspi_secret = os.environ.get("RASPI_SECRET", "raspitoken")
    post_url = os.environ.get("POST_IMAGE_URL", "localhost:1323")
    button_pin = os.environ.get("BUTTON", "GPIO26")
    image_ch: Channel[bytes] = Channel(10)
    button_pressed = Event()
    with (
        acquire_button(button_pin) as button,
        acquire_camera() as camera,
        concurrent.futures.ThreadPoolExecutor() as pool,
    ):
        sbutton = loop.run_in_executor(pool, serve_button, button, button_pressed, terminate, delay)
        scamera = loop.run_in_executor(pool, serve_camera, loop, camera, image_ch, button_pressed, terminate, delay)
        receive = asyncio.create_task(receive_camera(raspi_secret, post_url, image_ch))
        await asyncio.wait([sbutton, scamera, receive], return_when=asyncio.FIRST_COMPLETED)


def run_client() -> None:
    import sys

    logging.basicConfig(stream=sys.stderr, level=logging.INFO)
    _log.setLevel(logging.DEBUG)
    asyncio.run(client())
