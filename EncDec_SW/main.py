import serial
import struct
import time
import os

PORT     = "COM9"
BAUD     = 9600
MAGIC    = b"PUF1"

# THIS IS OLDER VERSION ACTUAL IMPLEMENTATION IS IN DETECT_USB.PY GRACIASSS POR ESCUCHAR

def get_puf_key(ser, challenge: int) -> bytes:
    ser.write(struct.pack(">Q", challenge))
    time.sleep(0.1)
    response = ser.read(4)
    if len(response) < 4:
        raise TimeoutError(f"No response for challenge {challenge}")
    return response

def xor_data(data: bytes, ser, start_challenge=0) -> bytes:
    result = bytearray()
    challenge = start_challenge
    for i in range(0, len(data), 4):
        block = data[i:i+4]
        key   = get_puf_key(ser, challenge)
        enc   = bytes(b ^ k for b, k in zip(block, key))
        if len(enc) < 4:
            enc = enc.ljust(4, b'\x00')
        result.extend(enc)
        challenge += 1
    return bytes(result[:len(data)])

def encrypt_file(input_path: str, output_path: str):
    with open(input_path, "rb") as f:
        plaintext = f.read()
    ser = serial.Serial(PORT, BAUD, timeout=5)
    time.sleep(0.3)
    ser.reset_input_buffer()
    print(f"Encrypting {len(plaintext)} bytes...")
    ciphertext = xor_data(plaintext, ser)
    ser.close()
    with open(output_path, "wb") as f:
        f.write(MAGIC)
        f.write(struct.pack(">I", len(plaintext)))
        f.write(ciphertext)
    print(f"[OK] Encrypted → {output_path}")

def decrypt_file(input_path: str, output_path: str):
    with open(input_path, "rb") as f:
        raw = f.read()
    if raw[:4] != MAGIC:
        print("[ERROR] Not a PUF-encrypted file.")
        return
    original_size = struct.unpack(">I", raw[4:8])[0]
    ciphertext    = raw[8:]
    ser = serial.Serial(PORT, BAUD, timeout=5)
    time.sleep(0.3)
    ser.reset_input_buffer()
    print(f"Decrypting {len(ciphertext)} bytes...")
    plaintext = xor_data(ciphertext, ser)[:original_size]
    ser.close()
    with open(output_path, "wb") as f:
        f.write(plaintext)
    print(f"[OK] Decrypted → {output_path}")

if __name__ == "__main__":
    with open("secret.txt", "w") as f:
        f.write("Confidential: launch codes 42-ALPHA-7")

    encrypt_file("secret.txt", "secret.puf")
    decrypt_file("D:\\secret.puf", "recovered.txt") 

    with open("recovered.txt", "r") as f:
        print(f"\nRecovered: {f.read()}")