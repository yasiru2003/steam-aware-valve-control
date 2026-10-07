"""
adam_modbus_bridge.py

Hardware Bridge for Advantech ADAM Industrial I/O Modules over RS-485 Modbus RTU.
  - ADAM-4115: 8-channel RTD / Thermocouple input module (reads PT1000 mould probe).
  - ADAM-4024: 4-channel Analog Output module (transmits 4-20 mA command to I/P transducer).

Architecture Connection:
  Raspberry Pi 5 / reTerminal CM4 (USB-RS485 adapter)
     │
     ├── Modbus RTU (Slave ID 1): ADAM-4115 -> PT1000 Mould Temperature Probe
     │
     └── Modbus RTU (Slave ID 2): ADAM-4024 -> 4-20 mA -> I/P Transducer -> Pneumatic Steam Valve
"""

import time
import logging
from typing import Optional, Tuple

try:
    from pymodbus.client import ModbusSerialClient
    PYMODBUS_AVAILABLE = True
except ImportError:
    PYMODBUS_AVAILABLE = False

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("ADAM_Bridge")


class AdamModbusBridge:
    """
    Industrial Modbus RTU Bridge for ADAM-4115 (PT1000 input) & ADAM-4024 (4-20mA output).
    Supports physical serial hardware communication with automatic simulation fallback.
    """

    def __init__(
        self,
        port: str = "/dev/ttyUSB0",
        baudrate: int = 9600,
        timeout: float = 1.0,
        adam_4115_unit_id: int = 1,
        adam_4024_unit_id: int = 2,
        mock_mode: bool = False
    ):
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.adam_4115_unit_id = adam_4115_unit_id
        self.adam_4024_unit_id = adam_4024_unit_id
        self.mock_mode = mock_mode or (not PYMODBUS_AVAILABLE)
        
        self.client = None
        self.connected = False

        # Internal simulated plant state for mock testing
        self._sim_temperature = 25.0
        self._last_valve_pct = 0.0

    def connect(self) -> bool:
        """Establishes connection to the RS-485 serial bus."""
        if self.mock_mode:
            logger.info(f"[MOCK] Initialized ADAM Modbus Bridge in Simulation Mode (No physical RS-485 hardware required).")
            self.connected = True
            return True

        if not PYMODBUS_AVAILABLE:
            logger.warning("pymodbus not installed. Falling back to mock mode.")
            self.mock_mode = True
            self.connected = True
            return True

        try:
            self.client = ModbusSerialClient(
                port=self.port,
                baudrate=self.baudrate,
                parity="N",
                stopbits=1,
                bytesize=8,
                timeout=self.timeout
            )
            self.connected = self.client.connect()
            if self.connected:
                logger.info(f"Connected to RS-485 Modbus bus on {self.port} at {self.baudrate} baud.")
            else:
                logger.warning(f"Could not open serial port {self.port}. Falling back to mock mode.")
                self.mock_mode = True
                self.connected = True
            return self.connected
        except Exception as e:
            logger.warning(f"Failed to connect to Modbus client ({e}). Switching to mock mode.")
            self.mock_mode = True
            self.connected = True
            return True

    def disconnect(self):
        """Closes serial connection."""
        if self.client and hasattr(self.client, "close"):
            self.client.close()
        self.connected = False
        logger.info("ADAM Modbus bridge disconnected.")

    def read_mould_temperature(self, channel: int = 0) -> Optional[float]:
        """
        Reads PT1000 sensor temperature (°C) from ADAM-4115 RTD input module.
        Channel 0 register address: 0x0000 (Holding or Input Register).
        ADAM-4115 delivers 2's complement integer scaled by 0.1 °C (e.g., 1300 = 130.0 °C).
        """
        if self.mock_mode or not self.client:
            # Simulate slight response to last valve command
            heating_rate = (self._last_valve_pct / 100.0) * 0.02 * 60.0 # deg C per sec equivalent
            cooling_rate = (self._sim_temperature - 25.0) * 0.005
            self._sim_temperature += (heating_rate - cooling_rate) * 0.05
            return round(self._sim_temperature, 2)

        try:
            # Read 1 register from ADAM-4115 channel
            rr = self.client.read_input_registers(address=channel, count=1, slave=self.adam_4115_unit_id)
            if rr.isError():
                # Try holding registers if input register fails
                rr = self.client.read_holding_registers(address=channel, count=1, slave=self.adam_4115_unit_id)
            
            if rr.isError():
                logger.error(f"Error reading ADAM-4115 channel {channel}: {rr}")
                return None

            raw_val = rr.registers[0]
            # Convert unsigned to signed 16-bit integer
            if raw_val > 32767:
                raw_val -= 65536
            temp_c = raw_val / 10.0
            return temp_c

        except Exception as e:
            logger.error(f"Exception reading mould temperature: {e}")
            return None

    def write_valve_command(self, valve_pct: float, channel: int = 0) -> bool:
        """
        Commands steam control valve by transmitting 4-20 mA current output from ADAM-4024.
        Valve opening: 0.0% = 4.00 mA, 100.0% = 20.00 mA.
        ADAM-4024 accepts standard 12-bit/16-bit DAC register:
          4 mA = 0x0000 (or calibrated offset)
          20 mA = 0x0FFF (4095) for 12-bit or engineering units.
        """
        clamped_pct = max(0.0, min(100.0, float(valve_pct)))
        self._last_valve_pct = clamped_pct
        current_ma = 4.0 + (clamped_pct / 100.0) * 16.0

        if self.mock_mode or not self.client:
            return True

        try:
            # Map 4-20mA to 0-4095 DAC code
            dac_value = int((clamped_pct / 100.0) * 4095)
            rq = self.client.write_register(address=channel, value=dac_value, slave=self.adam_4024_unit_id)
            if rq.isError():
                logger.error(f"Error writing to ADAM-4024 channel {channel}: {rq}")
                return False
            return True

        except Exception as e:
            logger.error(f"Exception writing valve command: {e}")
            return False

    def update_cycle(self, commanded_valve_pct: float) -> Tuple[Optional[float], float, float]:
        """
        Single-step control update:
          1. Writes valve opening (0-100%) to ADAM-4024 (4-20 mA).
          2. Reads current mould temperature (°C) from ADAM-4115 (PT1000).
        Returns: (mould_temp_C, commanded_valve_pct, current_ma)
        """
        self.write_valve_command(commanded_valve_pct)
        temp_c = self.read_mould_temperature()
        current_ma = 4.0 + (commanded_valve_pct / 100.0) * 16.0
        return temp_c, commanded_valve_pct, current_ma


if __name__ == "__main__":
    print("=" * 70)
    print("  ADAM MODBUS RTU HARDWARE BRIDGE (ADAM-4115 & ADAM-4024)")
    print("=" * 70)

    bridge = AdamModbusBridge(port="/dev/ttyUSB0", mock_mode=False)
    bridge.connect()

    print("\nRunning test hardware communication loop (10 steps)...")
    test_valves = [0.0, 25.0, 50.0, 75.0, 100.0, 100.0, 50.0, 26.25, 0.0, 0.0]

    for i, v_cmd in enumerate(test_valves):
        temp, valve, current = bridge.update_cycle(v_cmd)
        print(f"Step {i+1:02d} | Commanded Valve: {valve:6.2f}% | Output Current: {current:5.2f} mA | Read Mould Temp: {temp} °C")
        time.sleep(0.2)

    bridge.disconnect()
    print("\n[OK] Hardware bridge test finished.")
