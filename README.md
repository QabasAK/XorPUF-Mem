# XorPUF-Mem: Lightweight Memory Obfuscation Using PUF-Based XOR Encryption

An FPGA memory-obfuscation prototype combining a BRAM-backed PUF response table, a hardware XOR datapath, and a MicroBlaze command interface. A Python host sends file data over UART and stores the transformed output.

**Accepted at AEECT** · Qabas Alkaissi, Selen Qarajeh, Jana Falah, and Enas Abulibdeh

Department of Computer Engineering, Princess Sumaya University for Technology, Amman, Jordan

## Overview

The project explores lightweight memory protection on resource-constrained embedded systems. The paper describes an address-derived PUF keystream architecture and demonstrates a USB storage workflow on an Artix-7 FPGA using emulated PUF responses.

The implementation spans three parts:

- **Hardware:** a custom AXI-Stream XOR engine, BRAM response storage, and an RTL policy state machine.
- **Firmware:** a MicroBlaze application that loads the response table, handles enrollment commands, and transfers bytes through the XOR engine.
- **Software:** a Python CLI for file encryption, decryption, and communication with the board.

## System Architecture

<p align="center">
  <img src="docs/figures/architecture.png" alt="Paper architecture showing Python file I/O, MicroBlaze firmware, the policy FSM, BRAM response storage, and the AXI-Stream XOR engine" width="450">
</p>

*System architecture from the paper, Fig. 1.*

USB storage connects to the host PC. Python sends commands and data over UART; MicroBlaze moves the data through the FPGA's XOR engine and returns the output. The FPGA does not act as a USB host.

| Layer | Main source | Responsibility |
| --- | --- | --- |
| Hardware | [`hardware/rtl/`](hardware/rtl/) | XOR datapath and policy FSM |
| Firmware | [`firmware/src/main.c`](firmware/src/main.c) | UART commands, response-table loading, and stream transfers |
| Software | [`host/xorpuf.py`](host/xorpuf.py) | File handling, header validation, and serial communication |

## Obfuscation Datapath

Encryption and decryption use the same XOR operation:

$$ C_i = P_i \oplus K_i, \qquad P_i = C_i \oplus K_i $$

Here, $P_i$ is a plaintext byte, $C_i$ is its ciphertext byte, and $K_i$ is a byte selected from the response table. The counter-based XOR engine addresses BRAM words as:

$$ \text{BRAM address} = 4\left(\left\lfloor\frac{\text{byte count}}{4}\right\rfloor \bmod 100\right) $$

Each 32-bit response supplies four key bytes, selected from most significant to least significant. A reset restarts the stream; a dummy-byte exchange aligns the host with the firmware.

The paper also describes LFSR-based challenge expansion. Experimental LFSR IP is available under [`hardware/experimental/`](hardware/experimental/).

## Enrollment and Authentication

<p align="center">
  <img src="docs/figures/access-control.png" alt="Paper state machine with idle, enroll, decrypt, and reject states" width="450">
</p>

*Policy state machine from the paper, Fig. 2. E denotes enrollment status and M denotes a signature match in the transition description.*

| State | Output | Intended operation |
| --- | --- | --- |
| Idle | `00` | Wait for a request |
| Enroll / encrypt | `01` | Establish a session signature and encrypt data |
| Decrypt | `10` | Accept a matching signature and recover plaintext |
| Reject | `11` | Deny a mismatched signature |

The firmware compares a claimed signature against a hash of its compiled response table. The host checks the authentication response before requesting a transfer.

Encrypted files use a 12-byte header followed by ciphertext:

```text
Offset     0              4              8             12
           | PUF1         | Signature    | Byte length  | Ciphertext ...
           | 4 bytes      | 4 bytes      | 4 bytes      |
```

The signature and byte length use big-endian encoding.

## Results

Results reported in the paper are summarized below.

### Ciphertext statistics

The evaluation uses a 1,000,000-bit plaintext constructed from English letter-frequency-weighted sampling.

| Metric | Reported result |
| --- | --- |
| Plaintext Shannon entropy | 4.8442 bits/byte |
| Ciphertext Shannon entropy | 7.9987 bits/byte |
| Plaintext/ciphertext Pearson correlation | 0.0064 |
| Byte-distribution chi-square p-value | 0.915 |
| Ciphertext bit balance | 0.4998 |
| Bit flip rate between adjacent CRP indices | 50.06% |

<p align="center">
  <img src="docs/figures/ciphertext-distribution.png" alt="Ciphertext byte-frequency plot from the paper, with a uniform reference at 1/256 and chi-square p-value of 0.915" width="500">
</p>

*Ciphertext byte distribution from the paper, Fig. 6. The dashed line marks the uniform reference distribution.*

### FPGA implementation

Target: **Nexys A7-100T**, Artix-7 `xc7a100tcsg324-1`, using **Vivado / Vitis 2025.2**.

| Resource or metric | Result |
| --- | --- |
| Total LUTs | 2,138 / 63,400 (3.37%) |
| LUTs used as logic | 1,996 (3.15% of device LUTs) |
| Registers | 2,212 / 126,800 (1.74%) |
| Block RAM | 18 / 135 tiles (13.33%) |
| DSP slices | 0 |
| Primary clock | 100 MHz |
| Estimated total on-chip power | 0.235 W |
| Worst setup slack | +1.809 ns |
| Worst hold slack | +0.035 ns |

The [Vivado reports](reports/) provide utilization, power, and timing details. The paper reports ten successful repetitions of each functional scenario: enrollment, matching-signature decryption, and rejection.

## Running the Host

Use **Python 3.10+** and a board programmed with matching hardware and firmware. UART defaults to **9600 baud**.

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r host/requirements.txt

.venv\Scripts\python host/xorpuf.py --port COM9 reset-enrollment
.venv\Scripts\python host/xorpuf.py --port COM9 encrypt sample.txt sample.txt.puf
.venv\Scripts\python host/xorpuf.py --port COM9 decrypt sample.txt.puf recovered.txt
```

Replace `COM9` with the board's serial port. Input and output paths may point to a USB drive. The CLI keeps originals, refuses output overwrites, and removes staged files after a failed transfer. A new encryption session requires an explicit enrollment reset. After a mid-transfer timeout, reinitialize the FPGA before retrying because the firmware protocol has no cancellation or resynchronization command.

To rebuild the firmware, create a Vitis platform from [`hardware/export/design_1_wrapper_XOR2.xsa`](hardware/export/design_1_wrapper_XOR2.xsa), select `microblaze_0` with a standalone domain, and import [`firmware/src/`](firmware/src/) into an empty C application. Regenerate the BSP and review the linker memory map. Full RTL rebuild prerequisites are covered in the [implementation notes](docs/IMPLEMENTATION.md).

Host tests run without a board or installed serial dependencies:

```powershell
python -m unittest discover -s host -p test_xorpuf.py -v
```

## Repository Layout

```text
host/                  Python CLI, requirements, and host tests
firmware/src/          MicroBlaze C application and build configuration
hardware/rtl/          Counter-based XOR engine and policy FSM
hardware/bd/           Vivado block design
hardware/export/       Vitis hardware handoff (XSA)
hardware/experimental/ Separate LFSR-based IP revision
reports/               Vivado utilization, power, and timing reports
docs/                  Implementation notes, figures, and source manifest
EncDec_SW/             USB middleware and analysis scripts
vitis_USB.zip          Vitis workspace archive
```

## Scope and Limitations

The prototype emulates PUF responses in BRAM; physical PUF integration, environmental reliability, error correction, and side-channel resistance remain future work. The XOR construction does not provide integrity protection, and statistical randomness tests do not establish cryptographic security. Signature matching does not verify a USB drive's physical identity, and the firmware transfer command is not independently gated by authentication state.

See [implementation notes](docs/IMPLEMENTATION.md) for build details and [figure provenance](docs/figures/README.md) for the paper illustrations.
