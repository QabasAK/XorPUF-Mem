import serial, struct, time, os, wmi
import tempfile, shutil

TEMP_DIR = tempfile.mkdtemp()

PORT  = "COM9"
BAUD  = 9600
MAGIC = b"PUF1"

# FSM decisions
ENROLL_ENCRYPT = 0x01
DECRYPT        = 0x02
REJECT         = 0x03

# ── PUF communication ─────────────────────────────────────────────
def get_puf_key(ser, challenge: int) -> bytes:
    ser.write(b'\x02')
    ser.write(struct.pack(">I", challenge))
    ser.flush()
    time.sleep(0.1)
    resp = ser.read(4)
    if len(resp) < 4:
        raise TimeoutError(f"No response for challenge {challenge}")
    return resp

def xor_data(data: bytes, ser, start=0) -> bytes:
    result = bytearray()
    for i in range(0, len(data), 4):
        block = data[i:i+4]
        key   = get_puf_key(ser, i // 4 + start)
        # Pad block to 4 bytes for XOR, but only keep original length
        padded_block = block.ljust(4, b'\x00')
        enc = bytes(b ^ k for b, k in zip(padded_block, key))
        result.extend(enc[:len(block)]) 
    return bytes(result)

# ── File operations ───────────────────────────────────────────────
def encrypt_file(input_path: str, output_path: str, ser):
    # Ask FPGA for its Signature
    ser.write(b'\x01')
    ser.write(struct.pack(">I", 0))
    ser.flush()
    
    status = ser.read(1)[0]
    if status != 0x01: # STATE_ENCRYPT
        print("Error: Device already enrolled or rejected.")
        return

    dev_sig = ser.read(4)
    
    with open(input_path, "rb") as f:
        plaintext = f.read()

    ciphertext = xor_data(plaintext, ser)
    
    with open(output_path, "wb") as f:
        # Header: MAGIC (4) + SIG (4) + SIZE (4) = 12 bytes total
        f.write(MAGIC + dev_sig + struct.pack(">I", len(plaintext)) + ciphertext)
    print(f"  [OK] Locked to Device Sig: {dev_sig.hex()}")

# -- Verify Signature with Hardware --
def decrypt_file(input_path: str, output_path: str, ser):
    with open(input_path, "rb") as f:
        header = f.read(12)
        magic = header[0:4]
        file_sig = header[4:8]
        size = struct.unpack(">I", header[8:12])[0]
        ciphertext = f.read()

    if magic != MAGIC:
        return

    # Challenge the FPGA: "Is this your signature?"
    ser.write(b'\x01')
    ser.write(file_sig) 
    ser.flush()
    
    decision = ser.read(1)[0]
    
    if decision == 0x02: # STATE_DECRYPT (Match)
        print("  [MATCH] Hardware identity verified.")
        plaintext = xor_data(ciphertext, ser)[:size]
        with open(output_path, "wb") as f:
            f.write(plaintext)
    else:
        print(f"  [ACCESS DENIED] File signature {file_sig.hex()} does not match this FPGA!")

# ── Drive Operations ──────────────────────────────────────
def encrypt_drive(drive: str, ser, dev_sig):
    for fname in os.listdir(drive):
        fpath = os.path.join(drive, fname)
        if not os.path.isfile(fpath) or fname.endswith(".puf"):
            continue

        with open(fpath, "rb") as f:
            plaintext = f.read()
        
        ciphertext = xor_data(plaintext, ser)
        
        out_path = fpath + ".puf"
        with open(out_path, "wb") as f:
            # Header: MAGIC + SIG + SIZE
            f.write(MAGIC + dev_sig + struct.pack(">I", len(plaintext)) + ciphertext)
            
        os.remove(fpath)
        print(f"  [OK] Encrypted & Bound: {fname}")

def decrypt_drive(drive: str, ser):
    for fname in os.listdir(drive):
        fpath = os.path.join(drive, fname)
        if not os.path.isfile(fpath) or not fname.endswith(".puf"):
            continue
        
        temp_out = os.path.join(TEMP_DIR, fname[:-4])
        decrypt_file(fpath, temp_out, ser)
        
        if os.path.exists(temp_out):
            with open(temp_out, "r", errors="replace") as f:
                print(f"\n  ── {fname[:-4]} ──\n  {f.read()}\n  ────────────────")
            os.remove(temp_out)

# ── FSM handler ───────────────────────────────────────────────────
def on_usb_inserted(drive: str, ser):
    print(f"\nUSB detected: {drive}")
    
    puf_files = [f for f in os.listdir(drive) if f.endswith(".puf")]

    if not puf_files:
        print("No encrypted files found. Initiating ENROLLMENT...")
        ser.write(b'\x01')
        ser.write(struct.pack(">I", 0)) 
        ser.flush()
        
        resp = ser.read(1)
        if resp and resp[0] == ENROLL_ENCRYPT:
            dev_sig = ser.read(4)
            print(f"FPGA Authorized for Enrollment. Sig: {dev_sig.hex()}")
            encrypt_drive(drive, ser, dev_sig)
    else:
        print(f"Found {len(puf_files)} .puf files. Attempting DECRYPTION...")
        decrypt_drive(drive, ser)

# ── Main loop ─────────────────────────────────────────────────────
if __name__ == "__main__":
    ser = serial.Serial()
    ser.port = PORT
    ser.baudrate = BAUD
    ser.timeout = 5

    ser.dtr = False
    ser.rts = False
    
    ser.open() 
    time.sleep(3)
    ser.reset_input_buffer()
    ser.write(b'\xFF')
    ser.flush()
    ack = ser.read(1)
    print("Enrollment cleared on FPGA" if ack == b'\xFF' else "Warning: no ack")
    print("PUF Security System ready.")
    print("Watching for USB insertion... (Ctrl+C to stop)\n")

    c       = wmi.WMI()
    watcher = c.watch_for(
        notification_type="Creation",
        wmi_class="Win32_LogicalDisk",
        delay_secs=1
    )

    watcher_remove = c.watch_for(
        notification_type="Deletion",
        wmi_class="Win32_LogicalDisk",
        delay_secs=1
    )

    try:
        while True:
            try:
                usb = watcher(timeout_ms=1000)
                on_usb_inserted(usb.DeviceID + "\\", ser)
            except wmi.x_wmi_timed_out:
                pass

            # try:
            #     usb = watcher_remove(timeout_ms=500)
            #     on_usb_removed(usb.DeviceID + "\\", ser)
            # except wmi.x_wmi_timed_out:
            #     pass
    except KeyboardInterrupt:
        print("\nShutting down.")
        ser.close()