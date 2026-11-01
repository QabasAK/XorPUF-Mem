# Recovered implementation and open issues

## Source selection

Sources were recovered from `Desktop/vitis_USB_1`, `Desktop/EncDec_SW`, and `Desktop/IJSRP - PUFs`. No file matching HWSW was found in the indexed Desktop search. `docs/source-manifest.json` records each copied file and SHA-256 checksum. Desktop originals were not modified.

`host/allHW.py` uses the same command bytes as `firmware/src/main.c`. The original repo's `main.py` explicitly describes itself as older; it uses a different request format. Keep these revisions separate.

The Vivado project's generated `ipshared/c207/hdl/xor_enc_dec.v` implements a counter-based table reader. That is the source in `hardware/rtl/xor_enc_dec.v`. The loose IP repository contains a different two-layer LFSR engine, preserved under `hardware/experimental/`. The cached version is evidence of a generated project revision, not proof that the handoff or bitstream contains identical logic. The XSA is retained from the Vitis platform, without modification.

## UART protocol

All multi-byte integers below are big-endian.

| Command | Request after command byte | Reply |
| --- | --- | --- |
| `0xFF` | None | `0xFF`, clears firmware enrollment |
| `0x01` | 4-byte claimed signature | State `1` + 4-byte signature for initial enrollment; state `2` for match; state `3` for rejection |
| `0x03` | 4-byte byte count followed by a byte-at-a-time request/reply stream | One transformed byte per input byte |

The firmware resets the engine and performs one internal dummy stream exchange. The host also counts and sends one dummy byte, discarding its reply. Preserve both until their alignment is checked against the actual bitstream. The host `.puf` format is `PUF1` (4 bytes), signature (4 bytes), original length (4 bytes), then ciphertext. Earlier scripts use other headers despite sharing the magic value.

## Findings requiring confirmation

1. **Two different XOR engines.** The generated engine uses a 10-bit counter and BRAM address `((byte_cnt >> 2) % 100) * 4`, selecting a byte from each 32-bit word. The counter wraps at 1024 bytes. The loose IP uses an LFSR and two XOR layers. Firmware writes `1` then `0` to control offset zero; the loose IP interprets upper bits as a seed, yielding a zero LFSR seed. Do not substitute that IP into the historical build without validating it.
2. **Response-table provenance.** The recovered firmware's 100 response words are exactly `(index + 1) * 0x045D9F3B mod 2^32`. Although its header names a UCI dataset, that comment alone does not establish that these values came from measured CRPs. The earlier repo contains a different header and a dataset conversion script referring to a missing spreadsheet. Confirm the actual experiment table before claiming reproduction of paper statistics.
3. **Policy enforcement differs across sources.** Firmware handles enrollment decisions directly. It initializes an input GPIO but does not read it in its command loop. `0x03` processing is accepted independently of authentication state. The separate RTL FSM should not be described as enforcing every firmware data transfer on the evidence of these files alone.
4. **Signature matching is not USB identity verification.** Firmware compares the claimed header signature to a hash computed from the compiled response table. The host does not provide a USB hardware identifier. A copied matching header can pass this comparison.
5. **Enrollment persistence needs verification.** Variables use a `.noinit` section, but the supplied linker script does not explicitly define that section. Retention across resets and power cycles is unverified. The host resets enrollment at each startup.
6. **Host file handling.** The host handles root-level files, removes plaintext after encryption, accepts logical-disk creation events without a removable-drive filter, and does not validate every short header/read. It should be exercised only with copied test files until hardened.
7. **RTL interfaces.** The cached engine samples the unsynchronized AXI control bit for counter reset despite declaring synchronizer registers. The experimental engine pulses output valid without retaining it under backpressure. Full AXI-Lite and stream behavior needs simulation before reuse outside the original setup.
8. **Build recovery.** The original project references an external `puf_init.coe` that was not found at the referenced location. Firmware loads BRAM at boot. No verified external pin constraints or portable project recreation script were recovered in this source set. Reusing the XSA and rebuilding from RTL are distinct validation tasks.

## Maintained host CLI

`host/xorpuf.py` is the maintained entry point. The unchanged `host/allHW.py` remains a provenance reference. The CLI exposes explicit single-file operations, retains inputs, refuses output overwrites, stages transfers, and checks serial replies and file lengths. It does not reset enrollment on startup or print plaintext. It preserves the original wire protocol, including both dummy exchanges. No firmware or cryptographic algorithm changes were made. A fresh-board decrypt performs the initial enrollment exchange and then authenticates the file signature again; a rejection creates no output. Enrollment state changes cannot be rolled back if a later transfer fails.

After a mid-transfer UART error, reinitialize the FPGA before retrying: the firmware has no framed transport or cancel command to resynchronize an incomplete transfer. Mocked protocol/file-safety tests cover host behavior; hardware compatibility remains unverified.

## Validation performed during recovery

Copied source hashes were checked against Desktop originals. Python files were parsed without executing USB watchers or touching serial ports. The XSA archive was checked for corruption, and the block-design JSON was parsed. The response-table arithmetic pattern was checked across all 100 words. No FPGA programming, firmware compilation, timing rerun, physical PUF measurement, or USB encryption was performed.

The historical reports match the paper's 1,996 logic LUTs, 2,138 total LUTs, and 2,212 registers. This correspondence helps identify the project but does not establish which RTL/table revision produced each reported experiment.
