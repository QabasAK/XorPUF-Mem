"""Command-line host for the XorPUF-Mem MicroBlaze UART demo."""

import argparse
from contextlib import closing
import logging
import os
from pathlib import Path
import shutil
import struct
import sys
import tempfile
import time

LOG = logging.getLogger("xorpuf")
HEADER = struct.Struct(">4s4sI")
MAGIC = b"PUF1"
MAX_SIZE = 0xFFFFFFFE  # Firmware count includes one host dummy byte.


def read_exact(port, count):
    """Collect short serial reads; an empty read means the timeout expired."""
    data = bytearray()
    while len(data) < count:
        chunk = port.read(count - len(data))
        if not chunk:
            raise TimeoutError(f"FPGA response timed out ({len(data)}/{count} bytes)")
        data.extend(chunk)
    return bytes(data)


def write_all(port, data):
    sent = 0
    while sent < len(data):
        count = port.write(data[sent:])
        if not count:
            raise TimeoutError("UART write timed out")
        sent += count


def authenticate(port, signature=b"\0" * 4):
    write_all(port, b"\x01" + signature)
    port.flush()
    state = read_exact(port, 1)[0]
    if state == 1:
        return state, read_exact(port, 4)
    if state in (2, 3):
        return state, None
    raise ValueError(f"Unexpected authentication state: {state}")


def reset_enrollment(port):
    write_all(port, b"\xff")
    port.flush()
    if read_exact(port, 1) != b"\xff":
        raise ValueError("FPGA did not acknowledge enrollment reset")


def transform(port, source, target, size):
    """Stream a file using the original byte-at-a-time firmware protocol."""
    if not 0 <= size <= MAX_SIZE:
        raise ValueError("File is too large for the firmware's 32-bit byte count")
    write_all(port, b"\x03")
    port.flush()
    time.sleep(0.2)
    write_all(port, struct.pack(">I", size + 1))
    port.flush()
    # Keep the historical host dummy exchange, in addition to firmware's dummy.
    write_all(port, b"\0")
    read_exact(port, 1)
    remaining = size
    while remaining:
        block = source.read(min(4096, remaining))
        if not block:
            raise ValueError("Input file changed or ended during transfer")
        result = bytearray()
        for value in block:
            write_all(port, bytes([value]))
            result.extend(read_exact(port, 1))
        target.write(result)
        remaining -= len(block)


def read_header(source):
    raw = source.read(HEADER.size)
    if len(raw) != HEADER.size:
        raise ValueError("Truncated .puf header")
    magic, signature, size = HEADER.unpack(raw)
    if magic != MAGIC:
        raise ValueError("Invalid .puf magic; expected PUF1")
    if size > MAX_SIZE or os.fstat(source.fileno()).st_size != HEADER.size + size:
        raise ValueError("Ciphertext length does not match the .puf header")
    return signature, size


def process_file(port, source_path, output_path, decrypt=False):
    """Write a complete new output; preserve the input and existing outputs."""
    source_path, output_path = Path(source_path), Path(output_path)
    if source_path.resolve() == output_path.resolve():
        raise ValueError("Input and output must be different files")
    if output_path.exists():
        raise FileExistsError(f"Output already exists: {output_path}")
    if not output_path.parent.is_dir():
        raise ValueError(f"Output directory does not exist: {output_path.parent}")

    temporary = None
    try:
        with source_path.open("rb") as source:
            if decrypt:
                signature, size = read_header(source)
                state, _ = authenticate(port, signature)
                if state == 1:
                    # First auth after boot enrolls regardless of claimed ID.
                    state, _ = authenticate(port, signature)
                if state != 2:
                    raise ValueError("FPGA rejected this file's signature")
                header = b""
            else:
                size = os.fstat(source.fileno()).st_size
                if size > MAX_SIZE:
                    raise ValueError("File is too large for the firmware's byte count")
                state, signature = authenticate(port)
                if state != 1:
                    raise ValueError("FPGA is already enrolled; use reset-enrollment before a new encryption session")
                header = HEADER.pack(MAGIC, signature, size)

            # Stage beside the output so publishing does not cross filesystems.
            with tempfile.NamedTemporaryFile(mode="wb", dir=output_path.parent,
                                             prefix=".xorpuf-", delete=False) as target:
                temporary = Path(target.name)
                target.write(header)
                transform(port, source, target, size)
                if source.read(1):
                    raise ValueError("Input file grew during transfer")
                target.flush()
                os.fsync(target.fileno())

        # Exclusive creation also protects against an output appearing mid-transfer.
        created = False
        try:
            with output_path.open("xb") as output:
                created = True
                with temporary.open("rb") as staged:
                    shutil.copyfileobj(staged, output)
                output.flush()
                os.fsync(output.fileno())
        except BaseException:
            if created:
                output_path.unlink(missing_ok=True)
            raise
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    LOG.info("%s → %s (%s bytes)", source_path, output_path, size)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", required=True, help="UART port, e.g. COM9")
    parser.add_argument("--baud", type=int, default=9600)
    parser.add_argument("--timeout", type=float, default=5.0, help="UART timeout in seconds")
    commands = parser.add_subparsers(dest="command", required=True)
    for action in ("encrypt", "decrypt"):
        command = commands.add_parser(action, help=f"{action.capitalize()} one file; keep the input")
        command.add_argument("input", type=Path)
        command.add_argument("output", type=Path)
    commands.add_parser("reset-enrollment", help="Explicitly clear the FPGA enrollment state")
    args = parser.parse_args(argv)
    if args.baud <= 0 or args.timeout <= 0:
        parser.error("--baud and --timeout must be positive")
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    try:
        import serial
    except ImportError:
        LOG.error("Install the host dependency: python -m pip install -r host/requirements.txt")
        return 1
    try:
        # Configure control lines before opening, as in the historical host.
        with closing(serial.Serial(port=None, baudrate=args.baud, timeout=args.timeout,
                                   write_timeout=args.timeout)) as port:
            port.dtr = False
            port.rts = False
            port.port = args.port
            port.open()
            time.sleep(2)
            port.reset_input_buffer()
            if args.command == "reset-enrollment":
                reset_enrollment(port)
                LOG.info("Enrollment cleared")
            else:
                process_file(port, args.input, args.output, args.command == "decrypt")
        return 0
    except (OSError, ValueError, TimeoutError, serial.SerialException) as error:
        LOG.error("%s", error)
        return 1
    except KeyboardInterrupt:
        LOG.info("Interrupted; input file preserved")
        return 130


if __name__ == "__main__":
    sys.exit(main())
