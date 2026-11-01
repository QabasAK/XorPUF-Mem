import serial
import struct
import os
import time
import wmi
import tempfile
import shutil

PORT      = 'COM9'
BAUD_RATE = 9600        # must match your UARTLite config — yours is 0x2580 = 9600
MAGIC     = b"PUF1"
TEMP_DIR  = tempfile.mkdtemp()

# ── Auth ──────────────────────────────────────────────────────────
def authenticate(ser):
    """Returns (state, dev_sig). state: 1=enroll/encrypt, 2=decrypt, 3=reject"""
    ser.write(b'\x01')
    ser.write(struct.pack(">I", 0))  # claimed_id = 0 for new enrollment
    ser.flush()
    state = ser.read(1)
    if not state:
        raise TimeoutError("No response from FPGA on auth")
    state = state[0]
    dev_sig = b'\x00\x00\x00\x00'
    if state == 0x01:  # STATE_ENCRYPT — new device, read signature
        dev_sig = ser.read(4)
    return state, dev_sig

# ── Hardware XOR stream ───────────────────────────────────────────
def fpga_xor(ser, data: bytes) -> bytes:
    ser.write(b'\x03')
    ser.flush()
    time.sleep(0.2)
    ser.write(struct.pack(">I", len(data) + 1))  # +1 for dummy byte
    ser.flush()

    # Dummy byte to absorb byte_cnt offset
    ser.write(bytes([0x00]))
    ser.read(1)  # discard dummy response

    result = bytearray()
    for byte in data:
        ser.write(bytes([byte]))
        b = ser.read(1)
        if not b:
            raise TimeoutError(f"FPGA stopped responding at byte {len(result)}")
        result.append(b[0])
    return bytes(result)

def show_temp_contents():
    files = os.listdir(TEMP_DIR)
    print("\n--- Current Decrypted Files in Temp ---")
    if not files:
        print("Folder is empty.")
    for f in files:
        print(f" > {f}")
    print("---------------------------------------\n")
# ── Encrypt drive ─────────────────────────────────────────────────
def encrypt_drive(drive, ser, dev_sig):
    for fname in os.listdir(drive):
        fpath = os.path.join(drive, fname)
        if not os.path.isfile(fpath) or fname.endswith(".puf"):
            continue
        with open(fpath, "rb") as f:
            plaintext = f.read()

        ciphertext = fpga_xor(ser, plaintext)

        out_path = fpath + ".puf"
        with open(out_path, "wb") as f:
            f.write(MAGIC + dev_sig + struct.pack(">I", len(plaintext)) + ciphertext)

        os.remove(fpath)
        print(f"  [OK] Encrypted: {fname}")

# ── Decrypt drive ─────────────────────────────────────────────────
def decrypt_drive(drive, ser):
    for fname in os.listdir(drive):
        fpath = os.path.join(drive, fname)
        if not os.path.isfile(fpath) or not fname.endswith(".puf"):
            continue

        with open(fpath, "rb") as f:
            header   = f.read(12)
            magic    = header[0:4]
            file_sig = header[4:8]
            size     = struct.unpack(">I", header[8:12])[0]
            ciphertext = f.read()

        if magic != MAGIC:
            continue

        # Authenticate with FPGA
        ser.write(b'\x01')
        ser.write(file_sig)
        ser.flush()
        decision = ser.read(1)
        if not decision:
            print(f"  [ERROR] No response for {fname}")
            continue

        if decision[0] == 0x02:  # STATE_DECRYPT
            plaintext = fpga_xor(ser, ciphertext)[:size]

            print(f"\n[CONTENT] Decrypted data from {fname}:")
            try:
                # This turns the raw bytes back into readable text
                print(f">>> {plaintext.decode('utf-8', errors='ignore')}")
            except Exception:
                # If it's an image or binary, just show a preview of the hex
                print(f">>> (Binary Data) {plaintext[:50].hex()}...")
            print("-" * 40)


            temp_out  = os.path.join(TEMP_DIR, fname[:-4])
            with open(temp_out, "wb") as f:
                f.write(plaintext)
            print(f"  [MATCH] Decrypted: {fname}")
            # print(f"Opening decrypted files at: {TEMP_DIR}")
            # os.startfile(TEMP_DIR)
        else:
            print(f"  [REJECTED] {fname} belongs to a different FPGA")

# ── USB handler ───────────────────────────────────────────────────
def on_usb_inserted(drive, ser):
    print(f"\nUSB detected: {drive}")
    puf_files = [f for f in os.listdir(drive) if f.endswith(".puf")]

    if not puf_files:
        print("No .puf files found — enrolling and encrypting...")
        state, dev_sig = authenticate(ser)
        if state == 0x01:
            print(f"  FPGA enrolled. Sig: {dev_sig.hex()}")
            encrypt_drive(drive, ser, dev_sig)
        else:
            print(f"  Unexpected state: {state}")
    else:
        print(f"  Found {len(puf_files)} .puf files — decrypting...")
        decrypt_drive(drive, ser)

# ── Main ──────────────────────────────────────────────────────────
if __name__ == "__main__":
    ser = serial.Serial()
    ser.port     = PORT
    ser.baudrate = BAUD_RATE
    ser.timeout  = 5
    ser.dtr      = False
    ser.rts      = False
    ser.open()
    time.sleep(2)
    ser.reset_input_buffer()

    # Clear enrollment
    ser.write(b'\xFF')
    ser.flush()
    ack = ser.read(1)
    print("Enrollment cleared" if ack == b'\xFF' else "Warning: no ack from FPGA")
    print("Watching for USB...\n")

    try:
        c = wmi.WMI()
        watcher = c.watch_for(notification_type="Creation",
                              wmi_class="Win32_LogicalDisk",
                              delay_secs=1)
        while True:
            try:
                usb = watcher(timeout_ms=1000)
                on_usb_inserted(usb.DeviceID + "\\", ser)
            except wmi.x_wmi_timed_out:
                pass

    except KeyboardInterrupt:
        print("\n[STOP] User interrupted script.")
    
    except Exception as e:
        print(f"\n[ERROR] System crash: {e}")

    finally:
        # THE CLEANUP: This runs no matter how the script ends
        if os.path.exists(TEMP_DIR):
            #print(f"Cleaning up sensitive data in {TEMP_DIR}...")
            shutil.rmtree(TEMP_DIR) 
            #print("Done. Securely closed.")
        
        if ser.is_open:
            ser.close()