from picamera2 import Picamera2


def capture() -> None:
    picam2 = Picamera2()
    capture_config = picam2.create_still_configuration()
    picam2.configure(capture_config)
    picam2.start()
    picam2.capture_file("demo.jpg")
    picam2.stop()


def hello() -> None:
    print("hello, world")
