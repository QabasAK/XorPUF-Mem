import serial
import struct
import time

ser = serial.Serial("COM9", 9600, timeout=5)
print("Port open:", ser.is_open)

time.sleep(0.3)
ser.reset_input_buffer()

ser.write(struct.pack(">Q", 42))
time.sleep(0.5)

response = ser.read(4)
print("Response bytes:", response.hex())
print("Response value:", struct.unpack(">I", response)[0])

ser.close()