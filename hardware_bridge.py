import time
import logging

try:
    import serial
except ImportError:
    serial = None

logger = logging.getLogger(__name__)

class ESP32SerialBridge:
    def __init__(self, port="/dev/ttyUSB0", baudrate=115200, timeout=1.0):
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.ser = None
        self.connected = False

    def connect(self):
        if not serial:
            logger.error("pyserial is not installed. Please install it using 'pip install pyserial'")
            return False
            
        try:
            self.ser = serial.Serial(self.port, self.baudrate, timeout=self.timeout)
            time.sleep(2) # Wait for ESP32 to reboot upon connection
            self.connected = True
            logger.info(f"Successfully connected to ESP32 on {self.port}")
            return True
        except Exception as e:
            logger.error(f"Failed to connect to ESP32 on {self.port}: {str(e)}")
            self.connected = False
            return False

    def disconnect(self):
        if self.ser and self.ser.is_open:
            self.ser.close()
        self.connected = False

    def update_physics(self, valve_pct):
        if not self.connected or not self.ser:
            return None
            
        try:
            # Send the valve percentage to the ESP32
            command = f"V:{valve_pct:.2f}\n"
            self.ser.write(command.encode('utf-8'))
            self.ser.flush()
            
            # Wait for the ESP32 to reply with the simulated temperature
            reply = self.ser.readline().decode('utf-8').strip()
            
            if reply.startswith("T:"):
                temperature = float(reply[2:])
                return temperature
            else:
                logger.warning(f"Unexpected reply from ESP32: {reply}")
                return None
                
        except Exception as e:
            logger.error(f"Serial communication error: {str(e)}")
            self.connected = False
            return None
