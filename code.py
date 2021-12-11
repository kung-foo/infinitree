#!/usr/bin/env python3

import math
import os
import random
import time

import asynccp
import board
import microcontroller
import pwmio
import storage
from analogio import AnalogIn
from asynccp.time import Duration

MAX_DUTY_CYCLE = 2 ** 16 - 1
pwm_freq = 500

state_file = "last_state.txt"

STATE_UNKNOWN = "UNKNOWN"
STATE_ACTIVE = "ACTIVE"
STATE_SLEEP = "SLEEP"

fancy_title = """
██╗███╗   ██╗███████╗██╗███╗   ██╗██╗████████╗██████╗ ███████╗███████╗
██║████╗  ██║██╔════╝██║████╗  ██║██║╚══██╔══╝██╔══██╗██╔════╝██╔════╝
██║██╔██╗ ██║█████╗  ██║██╔██╗ ██║██║   ██║   ██████╔╝█████╗  █████╗  
██║██║╚██╗██║██╔══╝  ██║██║╚██╗██║██║   ██║   ██╔══██╗██╔══╝  ██╔══╝  
██║██║ ╚████║██║     ██║██║ ╚████║██║   ██║   ██║  ██║███████╗███████╗
╚═╝╚═╝  ╚═══╝╚═╝     ╚═╝╚═╝  ╚═══╝╚═╝   ╚═╝   ╚═╝  ╚═╝╚══════╝╚══════╝

              made with <3 by Petrikke and Jonathan
                 Oslo, Norway. Christmas 2021.

"""


class HaltException(Exception):
    pass


class Led:
    def __init__(self, pin, max_duty_cycle=MAX_DUTY_CYCLE):
        self._led = pwmio.PWMOut(pin, frequency=pwm_freq, duty_cycle=0)
        self._max_duty_cycle = max_duty_cycle

    def on(self):
        self._led.duty_cycle = self._max_duty_cycle

    def off(self):
        self._led.duty_cycle = 0

    def set(self, pct: float):
        pct = min(pct, 1)
        self._led.duty_cycle = min(
            int(self._max_duty_cycle * pct), self._max_duty_cycle
        )


class Animation:
    def __init__(
        self,
        leds,
        duration: float,
        frame_rate: int,
        offset: float = 0,
        scale_max: float = 1,
    ):
        if isinstance(leds, list):
            self.leds = leds  # type: List[Led]
        else:
            self.leds = [leds]  # type: List[Led]
        self.duration = duration
        self.frame_rate = frame_rate
        self.offset = offset
        self.scale_max = scale_max

        self.frame_count = int(self.duration * self.frame_rate)

    def exec(self, frame_number: int):
        frame_number += self.offset * self.frame_rate
        frame_in_animation = frame_number % self.frame_count

        self.render(
            frame_in_animation, float(frame_in_animation) / float(self.frame_count)
        )

    def render(self, frame_in_animation: int, completed: float):
        raise NotImplementedError("implement me")

    def set_all(self, pct: float):
        pct *= self.scale_max
        for led in self.leds:
            led.set(pct)


class Sine(Animation):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def render(self, _, completed: float):
        d = 2 * math.pi * completed
        v = (1 + math.sin(d)) / 2
        self.set_all(v)


class FlashAndDecay(Animation):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def render(self, frame_in_animation: int, completed: float):
        self.set_all(math.pow(math.e, -5 * completed))


class RandomGlitch(Animation):
    def __init__(self, *args, glitch_duration: float = 0, **kwargs):
        super().__init__(*args, **kwargs)
        if glitch_duration == 0:
            glitch_duration = self.duration / 10

        self.glitch_duration = glitch_duration

        self.glitch_values = []

        for _ in range(int(self.duration / self.glitch_duration)):
            self.glitch_values.append(random.uniform(0, 1))

        if self.frame_count % len(self.glitch_values) != 0:
            raise ValueError("XXX")

        self.frames_per_glitch = math.floor(self.frame_count / len(self.glitch_values))

    def render(self, frame_in_animation: int, completed: float):

        glitch_index = math.floor(frame_in_animation / self.frames_per_glitch)

        g1 = self.glitch_values[glitch_index]
        g2 = self.glitch_values[(glitch_index + 1) % len(self.glitch_values)]

        step = (g2 - g1) / self.frames_per_glitch

        steps = frame_in_animation - glitch_index * self.frames_per_glitch

        self.set_all(g1 + steps * step)


class Blink(Animation):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def render(self, _, completed: float):
        if completed <= 0.5:
            self.set_all(0)
        else:
            self.set_all(1)


class Static(Animation):
    def __init__(self, pct: float = 1, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.pct = pct
        self.is_set = False

    def render(self, frame_in_animation: int, completed: float):
        if not self.is_set:
            self.set_all(self.pct)
            self.is_set = True


class App:
    def __init__(self, frame_rate: int = 25):
        if not is_usb_connected():
            self.init_state_file()

        self.vbat_voltage = AnalogIn(board.VOLTAGE_MONITOR)
        self.start = 0
        self.frame_rate = frame_rate

        self.leds = []  # type: List[Led]

        self.led_light_green = self.register_led(board.D5)
        self.led_star = self.register_led(board.D9, 2 ** 14)
        self.led_red = self.register_led(board.D10)
        self.led_green = self.register_led(board.D12, 2 ** 14)

        self.blank()

        self.current_animation = 0

        self.switch_every = 15

        main_fade_duration = 5

        candle = RandomGlitch(
            self.led_star,
            duration=2,
            frame_rate=self.frame_rate,
            glitch_duration=(1 / self.frame_rate) * 5,
        )

        self.animations = [
            [
                FlashAndDecay(self.leds, duration=2, frame_rate=self.frame_rate),
            ],
            [
                Blink(
                    [self.led_green, self.led_light_green],
                    duration=1,
                    frame_rate=self.frame_rate,
                ),
                Blink(self.led_red, duration=1, frame_rate=self.frame_rate, offset=0.5),
                candle,
            ],
            [
                Sine(
                    self.led_green,
                    duration=main_fade_duration,
                    frame_rate=self.frame_rate,
                ),
                Sine(
                    self.led_red,
                    duration=main_fade_duration,
                    frame_rate=self.frame_rate,
                    offset=main_fade_duration / 2,
                ),
                candle,
            ],
            [
                RandomGlitch(
                    self.led_red,
                    duration=4,
                    frame_rate=self.frame_rate,
                ),
                RandomGlitch(
                    self.led_green,
                    duration=4,
                    frame_rate=self.frame_rate,
                ),
                RandomGlitch(
                    self.led_light_green, duration=2, frame_rate=self.frame_rate
                ),
                candle,
            ],
            [
                Blink(self.leds, duration=1, frame_rate=self.frame_rate),
            ],
            [
                FlashAndDecay(self.leds, duration=2, frame_rate=self.frame_rate),
            ],
        ]

    def register_led(self, pin, max_duty_cycle=MAX_DUTY_CYCLE) -> Led:
        led = Led(pin, max_duty_cycle)
        self.leds.append(led)
        return led

    def blank(self):
        for led in self.leds:
            led.off()

    async def draw_frame(self):
        frame = self.frame_number

        for animation in self.animations[self.current_animation]:
            animation.exec(frame)

    async def update_animation_set(self):
        if self.elapsed <= 2:
            return

        if self.current_animation == 0 or int(self.elapsed % self.switch_every) == 0:
            self.current_animation += 1
            if self.current_animation >= len(self.animations):
                self.current_animation = 1

            animation_names = set()
            for clz in self.animations[self.current_animation]:
                animation_names.add(clz.__class__.__name__)

            print(f"animation #{self.current_animation}: {animation_names}")

    @property
    def elapsed(self) -> float:
        return (time.monotonic_ns() - self.start) / 1_000_000_000

    @property
    def frame_number(self) -> int:
        return int(self.frame_rate * self.elapsed)

    async def print_power(self):
        v = (self.vbat_voltage.value * 3.3) / 65536 * 2
        print(f"voltage={v:.2f} temperature={microcontroller.cpu.temperature}")

    def halt(self):
        print("going to sleep...")

        self.set_state(STATE_SLEEP)

        self.blank()

        raise HaltException()

    @staticmethod
    def get_last_state() -> str:
        try:
            with open(state_file, "r") as f:
                return f.read().strip()
        except OSError:
            return STATE_UNKNOWN

    def init_state_file(self):
        try:
            os.stat(state_file)
        except OSError:
            self.set_state(STATE_ACTIVE)

    def set_state(self, state):
        if is_usb_connected():
            return

        try:
            storage.remount("/", readonly=False)
            with open(state_file, "w") as f:
                f.write(state)
        finally:
            storage.remount("/", readonly=True)

    def run(self, run_for=1):
        print(fancy_title)

        print(f"last state: {self.get_last_state()}")

        # someone has triggered the button (probably) which we'll interpret as a "stop blinking" command
        if self.get_last_state() == STATE_ACTIVE:
            if not is_usb_connected():
                self.halt()  # sets state to STATE_SLEEP
                # never gets here

        # we _were_ sleeping, therefore, time to walk up and get to blinking
        if self.get_last_state() == STATE_SLEEP:
            self.set_state(STATE_ACTIVE)

        loop = asynccp.Loop(debug=False)

        loop.schedule(frequency=self.frame_rate, coroutine_function=self.draw_frame)
        loop.schedule(Duration.of_seconds(5), coroutine_function=self.print_power)
        loop.schedule(
            Duration.of_seconds(1), coroutine_function=self.update_animation_set
        )
        loop.schedule_later(Duration.of_minutes(run_for), coroutine_function=self.halt)

        self.start = time.monotonic_ns()

        loop.run()


def is_usb_connected():
    try:
        storage.remount("/", readonly=False)  # attempt to mount readwrite
        storage.remount("/", readonly=True)  # attempt to mount readonly
    except RuntimeError:
        return True
    return False


try:
    App().run(run_for=60 * 4)
except HaltException:
    # TODO(jonathan): replace with real "deep sleep" once implemented
    time.sleep(float("inf"))
