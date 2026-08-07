import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Iterable, Literal, Optional

from ..config import Settings

logger = logging.getLogger(__name__)

RobotManualAction = Literal[
    "forward",
    "reverse",
    "left",
    "right",
    "brush_on",
    "brush_off",
    "return_home",
    "stop",
]


class RobotControllerError(RuntimeError):
    pass


class RobotTimeoutError(RobotControllerError):
    pass


class RobotController(ABC):
    @abstractmethod
    def connect(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def is_ready(self) -> bool:
        raise NotImplementedError

    @abstractmethod
    def clean_forward(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def clean_reverse(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def stop(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def return_home(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def emergency_stop(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def run_manual_command(
        self,
        action: RobotManualAction,
        *,
        speed: Optional[float] = None,
        duration_seconds: Optional[float] = None,
    ) -> None:
        raise NotImplementedError

    @abstractmethod
    def close(self) -> None:
        raise NotImplementedError


class MockRobotController(RobotController):
    def __init__(self, ready: bool = True):
        self.ready = ready
        self.commands: list[str] = []
        self.timeout_on: Optional[str] = None
        self.connected = False

    def connect(self) -> None:
        self.connected = True
        logger.info("Mock robot connected")

    def is_ready(self) -> bool:
        return self.ready and self.connected

    def _record(self, command: str) -> None:
        logger.info("Mock robot command: %s", command)
        self.commands.append(command)
        if self.timeout_on == command:
            raise RobotTimeoutError(f"Mock timeout during {command}")

    def clean_forward(self) -> None:
        self._record("CLEAN_FORWARD")

    def clean_reverse(self) -> None:
        self._record("CLEAN_REVERSE")

    def stop(self) -> None:
        self._record("STOP")

    def return_home(self) -> None:
        self._record("RETURN_HOME")

    def emergency_stop(self) -> None:
        self._record("EMERGENCY_STOP")

    def run_manual_command(
        self,
        action: RobotManualAction,
        *,
        speed: Optional[float] = None,
        duration_seconds: Optional[float] = None,
    ) -> None:
        command = f"MANUAL_{action.upper()}"
        if speed is not None:
            command = f"{command}:{speed:.2f}"
        if duration_seconds is not None:
            command = f"{command}:{duration_seconds:.2f}s"
        self._record(command)

    def close(self) -> None:
        self.connected = False
        logger.info("Mock robot closed")


class SerialRobotController(RobotController):
    def __init__(self, settings: Settings):
        self.settings = settings
        self.commands = settings.robot_commands
        self._serial = None

    def connect(self) -> None:
        try:
            import serial

            self._serial = serial.Serial(
                port=self.settings.robot_serial_port,
                baudrate=self.settings.robot_baud_rate,
                timeout=1,
                write_timeout=3,
            )
            logger.info("Serial robot connected on %s", self.settings.robot_serial_port)
        except Exception as exc:
            self._serial = None
            logger.exception("Serial robot connection failed")
            raise RobotControllerError(f"Robot serial connection failed: {exc}") from exc

    def is_ready(self) -> bool:
        return self._serial is not None and getattr(self._serial, "is_open", False)

    def clean_forward(self) -> None:
        self._send_and_wait(
            self.commands["clean_forward"],
            complete_acks={"END_REACHED"},
            timeout_seconds=self.settings.forward_timeout_seconds,
        )

    def clean_reverse(self) -> None:
        self._send_and_wait(
            self.commands["clean_reverse"],
            complete_acks={"HOME_REACHED"},
            timeout_seconds=self.settings.return_timeout_seconds,
        )

    def stop(self) -> None:
        self._send_and_wait(
            self.commands["stop"],
            complete_acks={"OK", "STOPPED"},
            timeout_seconds=5,
            allow_timeout_after_send=True,
        )

    def return_home(self) -> None:
        self._send_and_wait(
            self.commands["return_home"],
            complete_acks={"HOME_REACHED", "OK"},
            timeout_seconds=self.settings.return_timeout_seconds,
        )

    def emergency_stop(self) -> None:
        self._send_and_wait(
            self.commands["emergency_stop"],
            complete_acks={"OK", "STOPPED"},
            timeout_seconds=5,
            allow_timeout_after_send=True,
        )

    def run_manual_command(
        self,
        action: RobotManualAction,
        *,
        speed: Optional[float] = None,
        duration_seconds: Optional[float] = None,
    ) -> None:
        if action == "forward":
            self.clean_forward()
        elif action == "reverse":
            self.clean_reverse()
        elif action == "return_home":
            self.return_home()
        elif action in {"stop", "brush_off"}:
            self.stop()
        elif action == "brush_on":
            raise RobotControllerError("Serial robot controller does not support brush-only control.")
        elif action in {"left", "right"}:
            raise RobotControllerError("Serial robot controller does not support manual turning.")
        else:
            raise RobotControllerError(f"Unsupported manual robot action: {action}")

    def close(self) -> None:
        if self._serial is not None:
            self._serial.close()
            logger.info("Serial robot closed")

    def _send_and_wait(
        self,
        command: str,
        complete_acks: Iterable[str],
        timeout_seconds: float,
        allow_timeout_after_send: bool = False,
    ) -> None:
        if not self.is_ready():
            raise RobotControllerError("Robot controller is not connected.")

        assert self._serial is not None
        logger.info("Sending robot command: %s", command)
        self._serial.write(f"{command}\n".encode("utf-8"))
        self._serial.flush()

        deadline = time.monotonic() + timeout_seconds
        complete_ack_set = set(complete_acks)
        saw_ok = False
        while time.monotonic() < deadline:
            line = self._serial.readline().decode("utf-8", errors="ignore").strip()
            if not line:
                continue
            logger.info("Robot acknowledgement: %s", line)
            if line == "ERROR":
                raise RobotControllerError(f"Robot returned ERROR after {command}")
            if line == "OK":
                saw_ok = True
            if line in complete_ack_set:
                return

        if allow_timeout_after_send and saw_ok:
            return
        raise RobotTimeoutError(f"Robot command {command} timed out after {timeout_seconds} seconds.")


@dataclass(frozen=True)
class MotorPins:
    name: str
    in1: int
    in2: int
    pwm: int


class DRI0042MotorDriver:
    def __init__(self, pins: MotorPins, *, pwm_frequency_hz: int):
        try:
            from gpiozero import DigitalOutputDevice, PWMOutputDevice
        except Exception as exc:
            raise RobotControllerError(
                "gpiozero is required for ROBOT_CONTROLLER=gpio. "
                "Run backend/install_pi.sh on Raspberry Pi OS."
            ) from exc

        self.pins = pins
        self._in1 = DigitalOutputDevice(pins.in1, initial_value=False)
        self._in2 = DigitalOutputDevice(pins.in2, initial_value=False)
        self._pwm = PWMOutputDevice(pins.pwm, frequency=pwm_frequency_hz, initial_value=0.0)

    def forward(self, speed: float) -> None:
        self._set(True, False, speed)

    def reverse(self, speed: float) -> None:
        self._set(False, True, speed)

    def stop(self) -> None:
        self._pwm.value = 0.0
        self._in1.off()
        self._in2.off()

    def close(self) -> None:
        self.stop()
        self._pwm.close()
        self._in1.close()
        self._in2.close()

    def _set(self, in1: bool, in2: bool, speed: float) -> None:
        duty_cycle = max(0.0, min(1.0, speed))
        self._pwm.value = 0.0
        self._in1.value = in1
        self._in2.value = in2
        self._pwm.value = duty_cycle
        logger.info(
            "%s motor direction set: in1=%s in2=%s speed=%.2f",
            self.pins.name,
            in1,
            in2,
            duty_cycle,
        )


class GPIORobotController(RobotController):
    LEFT_MOTOR = MotorPins(name="left", in1=17, in2=27, pwm=18)
    RIGHT_MOTOR = MotorPins(name="right", in1=22, in2=23, pwm=12)
    BRUSH_MOTOR = MotorPins(name="brush", in1=5, in2=6, pwm=13)

    def __init__(self, settings: Settings):
        self.settings = settings
        self._left: Optional[DRI0042MotorDriver] = None
        self._right: Optional[DRI0042MotorDriver] = None
        self._brush: Optional[DRI0042MotorDriver] = None
        self.connected = False

    def connect(self) -> None:
        try:
            self._left = DRI0042MotorDriver(
                self.LEFT_MOTOR,
                pwm_frequency_hz=self.settings.robot_pwm_frequency_hz,
            )
            self._right = DRI0042MotorDriver(
                self.RIGHT_MOTOR,
                pwm_frequency_hz=self.settings.robot_pwm_frequency_hz,
            )
            self._brush = DRI0042MotorDriver(
                self.BRUSH_MOTOR,
                pwm_frequency_hz=self.settings.robot_pwm_frequency_hz,
            )
            self.stop()
            self.connected = True
            logger.info("GPIO robot connected with DRI0042 motor drivers")
        except Exception as exc:
            self.connected = False
            self.close()
            logger.exception("GPIO robot connection failed")
            if isinstance(exc, RobotControllerError):
                raise
            raise RobotControllerError(f"GPIO robot connection failed: {exc}") from exc

    def is_ready(self) -> bool:
        return self.connected and all((self._left, self._right, self._brush))

    def clean_forward(self) -> None:
        self._run_drive(
            direction="forward",
            include_brush=True,
            duration_seconds=self.settings.forward_timeout_seconds,
        )

    def clean_reverse(self) -> None:
        self._run_drive(
            direction="reverse",
            include_brush=True,
            duration_seconds=self.settings.return_timeout_seconds,
        )

    def stop(self) -> None:
        for driver in (self._left, self._right, self._brush):
            if driver is not None:
                driver.stop()
        logger.info("GPIO robot stopped")

    def return_home(self) -> None:
        self.stop()
        logger.info("GPIO return_home resolved with stop; timed reverse is handled by clean_reverse")

    def emergency_stop(self) -> None:
        self.stop()

    def run_manual_command(
        self,
        action: RobotManualAction,
        *,
        speed: Optional[float] = None,
        duration_seconds: Optional[float] = None,
    ) -> None:
        drive_speed = self._speed_or_default(speed, self.settings.robot_drive_speed)
        brush_speed = self._speed_or_default(speed, self.settings.robot_brush_speed)

        if action == "forward":
            self._drive_forward(drive_speed)
        elif action == "reverse":
            self._drive_reverse(drive_speed)
        elif action == "left":
            self._turn_left(drive_speed)
        elif action == "right":
            self._turn_right(drive_speed)
        elif action == "brush_on":
            self._start_brush(brush_speed)
        elif action == "brush_off":
            self._stop_brush()
        elif action == "return_home":
            self._stop_brush()
            self._drive_reverse(drive_speed)
        elif action == "stop":
            self.stop()
        else:
            raise RobotControllerError(f"Unsupported manual robot action: {action}")

        if duration_seconds:
            time.sleep(duration_seconds)
            if action == "brush_on":
                self._stop_brush()
            elif action != "brush_off":
                self.stop()

    def close(self) -> None:
        for driver in (self._left, self._right, self._brush):
            if driver is not None:
                try:
                    driver.close()
                except Exception:
                    logger.exception("Failed to close GPIO motor driver")
        self.connected = False

    def _run_drive(self, direction: Literal["forward", "reverse"], include_brush: bool, duration_seconds: float) -> None:
        if not self.is_ready():
            raise RobotControllerError("GPIO robot controller is not connected.")
        if include_brush:
            self._start_brush(self.settings.robot_brush_speed)
            if self.settings.robot_brush_lead_seconds:
                logger.info(
                    "GPIO brush lead active for %.2f seconds before %s movement",
                    self.settings.robot_brush_lead_seconds,
                    direction,
                )
                time.sleep(self.settings.robot_brush_lead_seconds)
        else:
            self._stop_brush()
        if direction == "forward":
            self._drive_forward(self.settings.robot_drive_speed)
        else:
            self._drive_reverse(self.settings.robot_drive_speed)
        time.sleep(duration_seconds)
        self.stop()

    def _drive_forward(self, speed: float) -> None:
        self._movement_drivers().forward(speed)

    def _drive_reverse(self, speed: float) -> None:
        self._movement_drivers().reverse(speed)

    def _turn_left(self, speed: float) -> None:
        left, right = self._require_movement_drivers()
        left.reverse(speed)
        right.forward(speed)

    def _turn_right(self, speed: float) -> None:
        left, right = self._require_movement_drivers()
        left.forward(speed)
        right.reverse(speed)

    def _start_brush(self, speed: float) -> None:
        brush = self._require_driver(self._brush, "brush")
        brush.forward(speed)

    def _stop_brush(self) -> None:
        brush = self._require_driver(self._brush, "brush")
        brush.stop()

    def _movement_drivers(self) -> "_MovementDrivers":
        left, right = self._require_movement_drivers()
        return _MovementDrivers(left=left, right=right)

    def _require_movement_drivers(self) -> tuple[DRI0042MotorDriver, DRI0042MotorDriver]:
        return (
            self._require_driver(self._left, "left"),
            self._require_driver(self._right, "right"),
        )

    def _require_driver(self, driver: Optional[DRI0042MotorDriver], name: str) -> DRI0042MotorDriver:
        if driver is None:
            raise RobotControllerError(f"GPIO {name} motor driver is not connected.")
        return driver

    def _speed_or_default(self, speed: Optional[float], default: float) -> float:
        if speed is None:
            return default
        return max(0.0, min(1.0, speed))


@dataclass(frozen=True)
class _MovementDrivers:
    left: DRI0042MotorDriver
    right: DRI0042MotorDriver

    def forward(self, speed: float) -> None:
        self.left.forward(speed)
        self.right.forward(speed)

    def reverse(self, speed: float) -> None:
        self.left.reverse(speed)
        self.right.reverse(speed)


def build_robot_controller(settings: Settings) -> RobotController:
    if not settings.robot_enabled:
        robot = MockRobotController(ready=False)
        robot.connect()
        return robot

    if settings.robot_controller.lower() == "gpio":
        gpio_robot = GPIORobotController(settings)
        try:
            gpio_robot.connect()
            return gpio_robot
        except RobotControllerError:
            logger.warning("Falling back to mock robot because GPIO controller is unavailable")
            robot = MockRobotController(ready=False)
            robot.connect()
            return robot

    if settings.robot_controller.lower() != "serial":
        logger.warning("Unknown ROBOT_CONTROLLER=%s. Falling back to serial.", settings.robot_controller)

    serial_robot = SerialRobotController(settings)
    try:
        serial_robot.connect()
        return serial_robot
    except RobotControllerError:
        logger.warning("Falling back to mock robot because serial controller is unavailable")
        robot = MockRobotController(ready=False)
        robot.connect()
        return robot
