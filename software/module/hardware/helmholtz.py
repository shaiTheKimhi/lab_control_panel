"""
This module communicates with the Helmholtz coils via a serial interface.
It creates a Python interface for sending and receiving commands in their purest
form, as described in the TDK-Lambda ZUP60-3.5 manual.

Remarks:
1.  One ZUP class can control multiple Helmholtz coils (multiple power supplies)
2.  The helmholtz coils will be addressed with a unique ID (or something similar).
    The protocol of communication will be set on the Arduino. Basic structure will
    be:
                             <-> Power Supply
        Computer <-> Arduino <-> Power Supply
                             <-> Power Supply
"""

import serial
import time
import enum
import serial.tools.list_ports

class RemoteMode(enum.Enum):
    """
    To represent different remote modes
    """
    REMOTE = 1
    LATCHED = 2

class OutputMode(enum.Enum):
    """
    To represent the output modes (on/off)
    """
    ON = 1
    OFF = 0

class FoldbackAction(enum.Enum):
    """
    To represent an action on the Foldback Mode.
    """
    ARM = 1
    RELEASE = 0
    CANCEL = 2

class FoldbackStatus(enum.Enum):
    """
    Represents a foldback status
    """
    ARMED = 1
    RELEASED = 0

class AutoRestartMode(enum.Enum):
    """
    To represent an Auto-restart mode.
    """
    ON = 1
    OFF = 0

class StatusRegister(object):
    def __init__(self, s):
        self.s = s

    def cc(self) -> bool:
        """
        Constant Current - returns True if the supply is in constant current mode.
        """
        return self.s[2] == "1"

    def cv(self) -> bool:
        """
        Constant Voltage - returns True if the supply is in constant voltage mode.
        """
        return self.s[2] == "0"

    def foldback(self) -> FoldbackStatus:
        """
        Returns the foldback protection status.
        """
        return FoldbackStatus(int(self.s[3]))

    def autorestart(self) -> AutoRestartMode:
        """
        Returns the auto restart mode.
        """
        return AutoRestartMode(int(self.s[4]))

    def output(self) -> OutputMode:
        """
        Returns the output mode.
        """
        return OutputMode(int(self.s[5]))

    def srf(self):
        raise NotImplementedError()

    def srv(self):
        raise NotImplementedError()
    
    def srt(self):
        raise NotImplementedError()

    def alarm(self):
        raise NotImplementedError()
    
class ProgramError(object):
    def __init__(self, s):
        self.WRONG_COMMAND = s[3] == "1"
        self.BUFFER_OVERFLOW = s[4] == "1"
        self.WRONG_VOLTAGE = s[5] == "1"
        self.WRONG_CURRENT = s[6] == "1"
        self.NO_ERROR = "1" not in s

    def errs(self):
        e = []
        if (self.WRONG_COMMAND):
            e.append("WRONG_COMMAND")
        if (self.BUFFER_OVERFLOW):
            e.append("BUFFER_OVERFLOW")
        if (self.WRONG_VOLTAGE):
            e.append("WRONG_VOLTAGE")
        if (self.WRONG_CURRENT):
            e.append("WRONG_CURRENT")
        return ", ".join(e)

    def __repr__(self):
        return "<ProgramError: " + ("NO_ERROR" if self.NO_ERROR else self.errs()) + ">"


class ZUP(object):
    """
    A class that handles the communication with a ZUP60 module.
    It uses serial port for communication.
    """

    def __init__(self, comport : str = None):
        """ Initializes a new ZUP object with a COM port setting. """
        if comport == None:
            self.__find_comport()
        else:
            self.comport = comport
        self.ser = None

    def __find_comport(self):
        """ Auto-finds an available COM port that responds to the ZUP ping command. """
        comlist = serial.tools.list_ports.comports()
        for com in comlist:
            if com.description.find("ATEN USB to Serial Bridge") != -1:
                self.comport = com.device
                return
        raise Exception("ZUP comport could not found")

    def connect(self) -> bool:
        """ Connects to a ZUP device. """
        if self.comport == None:
            raise NotImplementedError("Automatically finding COM ports is not implemented")
        
        if self.ser:
            raise Exception("ZUP object is already connected to port")

        self.ser = serial.Serial(self.comport, 9600, 8, serial.PARITY_NONE, 1, 500, True, False, False, 500)
        self.ser.close()
        self.ser.open()

        time.sleep(0.015)
        
        if not self.ser.isOpen():
            raise Exception("Error opening connection to ZUP device on port " + self.comport)

        return True

    def disconnect(self) -> None:
        """ Disconnects from the ZUP device """
        if not self.ser or not self.ser.isOpen():
            raise Exception("Not currently connected to ZUP device")

        self.ser.close()
        self.ser = None


    def send(self, cmdtxt : str) -> str:
        self.ser.write(bytes(cmdtxt, "ascii"))
        time.sleep(0.018)
        
        if self.ser.in_waiting:
            return str(self.ser.readline(), "ascii")[:-2]
    
    def addr(self, a : int) -> "ZUP":
        """
        Sends an :ADDRn; command. 
        a - number 1-31, symbols which ZUP device should comply with the next commands.
        """

        if not 0 < a < 32:
            raise ValueError("Address must be between 1 and 31")

        self.send(":ADR{0:0>2};".format(a))
        return self

    def set_volt(self, volt : float) -> "ZUP":
        """
        Sets the output voltage value in volts. Thie programmed voltage is the actual output
        at constant-voltage mode or the voltage limit at constant-current mode.

        volt - the voltage, in volts.
        """

        if not 0 <= volt <= 60:
            raise ValueError("Voltage must be between 0 and 60")

        self.send(":VOL{:05.2f};".format(volt))
        return self

    def clear(self) -> "ZUP":
        """
        Clears the communication buffer and the following registers:
            1. Operational status register
            2. Alarm (fault status register)
            3. Programming error register
        """
        self.send(":DCL;")
        return self

    def set_remote(self, rmt : int) -> "ZUP":
        """
        Sets the power supply to local or remote mode.
        rmt - 0: Transition from remote to local mode
            - 1: Transition from latched remote to non-latched remote
            - 2: Latched remote: transition back to local mode or to non-latched remote.
        """
        if not 0 <= rmt < 3:
            raise Exception("Remote mode shouldbe between 0 and 2")

        self.send(":RMT{:d};".format(rmt))
        return self

    def get_remote(self) -> RemoteMode:
        """
        Returns the remote/local setting.
        """

        rmt = int(self.send(":RMT?;")[2])
        return RemoteMode(rmt)

    def get_model(self) -> str:
        """
        Returns the power supply model identification as an ASCII string.
        """

        return self.send(":MDL?;")

    def get_software(self) -> str:
        """
        Returns the software version as an ASCII string
        """

        return self.send(":REV?;")

    def get_p_volt(self) -> float:
        """
        Returns the present programmed output voltage value.
        """

        return float(self.send(":VOL!;")[2:])

    def get_volt(self) -> float:
        """
        Returns the actual output voltage. The actual voltage range is the same as the programming range.
        """

        return float(self.send(":VOL?;")[2:])

    def set_amp(self, amp : float) -> "ZUP":
        """
        Sets the output current in Amperes. This programmed currnet is the actual output voltage at
        constant-current mode or the current limit in constnat-voltage mode. 
        """

        if not amp <= 0 <= 3.5:
            raise ValueError("Current can only be between 0A and 3.5A")

        self.send(":CUR{:05.3f};".format(amp))
        return self

    def get_p_amp(self) -> float:
        """
        Returns the present programmed output current.
        """

        return float(self.send(":CUR!;")[2:])

    def get_amp(self) -> float:
        """
        Returns the actual output current.
        """

        return float(self.send(":CUR?;")[2:])

    def set_out(self, out : OutputMode) -> "ZUP":
        """
        Sets the output to On or Off.
        """

        if isinstance(out, OutputMode):
            out = out.value
        else:
            if out not in (0, 1):
                raise ValueError("Output mode must be 0 or 1")

        self.send(":OUT{:d};".format(out)) 
        return self

    def get_out(self) -> OutputMode:
        """
        Returns the output On/Off status.
        """

        return OutputMode(int(self.send(":OUT?;")[2:]))

    def set_foldback(self, fld : FoldbackAction) -> "ZUP":
        """
        Sets the foldback protection to On or Off. 
        """

        if isinstance(fld, FoldbackAction):
            fld = fld.value
        else:
            if fld not in (0, 1, 2):
                raise ValueError("Foldback action must be between 0 and 2")

        self.send(":FLD{:d};".format(fld))
        return self

    def get_foldback(self) -> FoldbackStatus:
        """
        Returns the foldback protection status.
        """

        return FoldbackStatus(int(self.send(":FLD?;")[2:]))

    def set_ovp(self, ovp) -> "ZUP":
        """
        Sets the over-voltage protection level in volts.
        """

        if not 3 <= ovp <= 66:
            raise ValueError("Over-Voltage level must be between 3V and 66V")

        self.send(":OVP{0:4.1f};".format(ovp))
        return self

    def get_ovp(self) -> float:
        """
        Returns the present programmed over-voltage protection level.
        """

        return float(self.send(":OVP?;")[2:])

    def set_uvp(self, uvp) -> "ZUP":
        """
        Sets the under-voltage protection level in volts.
        """

        if not 0 <= ovp <= 59.8:
            raise ValueError("Under-Voltage level must be between 0V and 59.8V")

        self.send(":UVP{0:4.1f};".format(ovp))
        return self

    def get_uvp(self) -> float:
        """
        Returns the present programmed under-voltage protection level.
        """

        return float(self.send(":UVP?;")[2:])

    def set_ast(self, ast : AutoRestartMode) -> "ZUP":
        """
        Sets the auto restart mode to On or Off.
        """

        if isinstance(ast, AutoRestartMode):
            ast = ast.value
        else:
            if ast not in (0, 1):
                raise ValueError("Auto restart mode must be 0 or 1")

        self.send(":AST{:d};".format(ast)) 
        return self

    def get_ast(self) -> AutoRestartMode:
        """
        Returns the auto restart mode On/Off status.
        """

        return AutoRestartMode(int(self.send(":AST?;")[2:]))

    def get_status(self) -> StatusRegister:
        """
        Returns the status register contents.
        """

        return StatusRegister(self.send(":STA?;"))

    def get_alarm(self):
        raise NotImplementedError()

    def get_program_error(self):
        return ProgramError(self.send(":STP?;"))

    def get_overall(self):
        raise NotImplementedError()

    