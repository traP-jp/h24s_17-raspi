import io
from contextlib import contextmanager
from typing import Any, Generator

from picamera2 import Picamera2
from PIL.Image import Image


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
        image = camera.capture_image()
    assert isinstance(image, Image)
    with io.BytesIO() as out:
        image.save(out, format="JPEG")
        buf = out.getvalue()
    with open("demo.jpeg", mode="wb") as f:
        f.write(buf)
