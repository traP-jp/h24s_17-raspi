from contextlib import contextmanager
from typing import Any, Generator

from picamera2 import Picamera2


@contextmanager
def acquire_camera(config: dict | None = None) -> Generator[Picamera2, Any, None]:
    picam2 = Picamera2()
    config = config or picam2.create_still_configuration()
    picam2.configure(config)
    try:
        picam2.start()
        yield picam2
    finally:
        picam2.stop()


def capture() -> None:
    with acquire_camera() as camera:
        camera.capture_file("demo.jpg")
