# XorPUF-Mem

Implementation materials for **Lightweight Memory Obfuscation Using PUF-Based XOR Encryption**, accepted at AEECT.

Authors: Qabas Alkaissi, Selen Qarajeh, Jana Falah, and Enas Abulibdeh, Princess Sumaya University for Technology.

The prototype connects a Windows USB file handler to an Artix-7 FPGA over UART. MicroBlaze firmware handles enrollment commands, loads a response table into BRAM, and streams bytes through a hardware XOR engine. USB storage is attached to the PC; the FPGA receives bytes over UART.

## Implementation files

| Path | Contents |
| --- | --- |
| `host/allHW.py` | Recovered Windows host program for the hardware XOR command protocol |
| `firmware/src/` | MicroBlaze application and linker/build configuration recovered from `vitis_USB_1` |
| `hardware/rtl/` | XOR engine cached by the Vivado project, plus USB policy FSM |
| `hardware/bd/design_1.bd` | Original Vivado block design |
| `hardware/export/` | Hardware handoff used by the recovered Vitis platform |
| `hardware/experimental/` | Different, LFSR-based IP repository snapshot; compatibility is unverified |
| `reports/` | Existing Vivado placement, power, and timing reports |
| `docs/design_1.pdf` | Existing system diagram |
| `EncDec_SW/`, `vitis_USB.zip` | Earlier repository artifacts, retained for history; do not mix their protocols with the recovered firmware |

Read [implementation notes](docs/IMPLEMENTATION.md) before running. The recovered files contain multiple revisions; this release preserves their provenance and does not claim a newly verified FPGA build.

## Tools and setup

The recovered project targets the Nexys A7-100T (`xc7a100tcsg324-1`) and was built using Vivado/Vitis 2025.2. The host uses Python on Windows, PySerial, and WMI, with UART configured at 9600 baud. The original host selects `COM9`; change `PORT` for your board.

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r host/requirements.txt
```

In Vitis, create a platform from `hardware/export/design_1_wrapper_XOR2.xsa`, select `microblaze_0` and a standalone domain, then create an empty C application and import the recovered firmware sources. Regenerate the BSP and review the linker memory map. Build and program the board using that platform's hardware configuration. No board execution has been performed for this recovery.

The original host runs with `.venv\Scripts\python host/allHW.py`. It automatically resets enrollment and watches for inserted logical disks. **It deletes original files after writing `.puf` files. Use a disposable USB drive with copied test files only.** The script is preserved unchanged to avoid silently changing the historical protocol.

For a source rebuild in Vivado, use the block design and custom RTL, but first reconcile the two IP versions described in the implementation notes. A portable, validated full build script and verified external pin constraints are not yet included.

## Existing implementation results

The recovered reports list 2,138 total LUTs (3.37%), including 1,996 logic LUTs (3.15%); 2,212 registers (1.74%); and 18 BRAM tiles (13.33%). These are historical results, not measurements of a new build. See the reports for timing and power assumptions.

## Scope

This is a research memory-obfuscation prototype. The recovered firmware uses a compiled response table rather than a physical arbiter PUF. Table provenance and the relationship between source revisions and paper experiments need confirmation. The cached engine repeats table-derived XOR bytes and provides no cryptographic integrity protection. Statistical ciphertext tests alone do not establish cryptographic security.
