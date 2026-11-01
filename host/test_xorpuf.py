"""Protocol and file-safety checks; no FPGA or serial dependency required."""

import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import xorpuf


class FakePort:
    def __init__(self, replies):
        self.replies = bytearray(replies)
        self.written = bytearray()

    def read(self, count):
        result = bytes(self.replies[:1])  # Exercise fragmented reads.
        del self.replies[:1]
        return result

    def write(self, data):
        self.written.extend(data[:1])  # Exercise short writes too.
        return min(1, len(data))

    def flush(self):
        pass


class HostTests(unittest.TestCase):
    def test_serial_fragmentation_and_timeout(self):
        self.assertEqual(xorpuf.read_exact(FakePort(b"abcd"), 4), b"abcd")
        with self.assertRaises(TimeoutError):
            xorpuf.read_exact(FakePort(b"a"), 2)

    @patch("xorpuf.time.sleep")
    def test_transform_preserves_wire_protocol(self, _sleep):
        port, target = FakePort(b"\0XYZ"), io.BytesIO()
        xorpuf.transform(port, io.BytesIO(b"abc"), target, 3)
        self.assertEqual(port.written, b"\x03\0\0\0\x04\0abc")
        self.assertEqual(target.getvalue(), b"XYZ")

    def test_encrypt_decrypt_and_preserve_original(self):
        with tempfile.TemporaryDirectory() as directory, patch("xorpuf.time.sleep"):
            root = Path(directory)
            original, encrypted, recovered = [root / name for name in ("a", "a.puf", "b")]
            original.write_bytes(b"abc")
            port = FakePort(b"\x01SIGN\0XYZ")
            xorpuf.process_file(port, original, encrypted)
            self.assertEqual(encrypted.read_bytes(), b"PUF1SIGN\0\0\0\x03XYZ")
            # A fresh boot enrolls first, then checks the claimed signature.
            port = FakePort(b"\x01SIGN\x02\0abc")
            xorpuf.process_file(port, encrypted, recovered, decrypt=True)
            self.assertEqual(recovered.read_bytes(), original.read_bytes())
            self.assertTrue(port.written.startswith(b"\x01SIGN\x01SIGN\x03"))

    def test_invalid_header_and_rejection_leave_no_output(self):
        with tempfile.TemporaryDirectory() as directory:
            source, output = Path(directory) / "a.puf", Path(directory) / "out"
            for data in (b"PUF1", b"NOPEsign\0\0\0\0", b"PUF1sign\0\0\0\x02x"):
                source.write_bytes(data)
                port = FakePort(b"")
                with self.assertRaises(ValueError):
                    xorpuf.process_file(port, source, output, decrypt=True)
                self.assertFalse(port.written)
                self.assertFalse(output.exists())
            source.write_bytes(b"PUF1sign\0\0\0\0")
            with self.assertRaisesRegex(ValueError, "rejected"):
                xorpuf.process_file(FakePort(b"\x03"), source, output, decrypt=True)
            self.assertFalse(output.exists())

    def test_failed_transfer_cleans_up_and_existing_output_is_preserved(self):
        with tempfile.TemporaryDirectory() as directory, patch("xorpuf.time.sleep"):
            root = Path(directory)
            source, output = root / "a", root / "out"
            source.write_bytes(b"abc")
            with self.assertRaises(TimeoutError):
                xorpuf.process_file(FakePort(b"\x01SIGN\0X"), source, output)
            self.assertEqual(list(root.iterdir()), [source])
            output.write_bytes(b"keep")
            port = FakePort(b"")
            with self.assertRaises(FileExistsError):
                xorpuf.process_file(port, source, output)
            self.assertEqual(output.read_bytes(), b"keep")
            self.assertFalse(port.written)


if __name__ == "__main__":
    unittest.main()
