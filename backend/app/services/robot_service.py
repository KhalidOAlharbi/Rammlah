import logging
import time
from abc import ABC, abstractmethod
from typing import Iterable, Optional

from ..config import Settings

logger = logging.getLogger(__name__)


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


def build_robot_controller(settings: Settings) -> RobotController:
    if not settings.robot_enabled:
        robot = MockRobotController(ready=False)
        robot.connect()
        return robot

    serial_robot = SerialRobotController(settings)
    try:
        serial_robot.connect()
        return serial_robot
    except RobotControllerError:
        logger.warning("Falling back to mock robot because serial controller is unavailable")
        robot = MockRobotController(ready=False)
        robot.connect()
        return robot
