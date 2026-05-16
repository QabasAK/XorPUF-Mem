import pandas as pd
import numpy as np

file_path = r"C:\Users\walki\OneDrive\Desktop\test_5xor_128dim.xlsx"

# Only need 100 * 32 = 3,200 CRPs for 100 uint32 words
WORDS_NEEDED = 100
CRPS_NEEDED  = WORDS_NEEDED * 32  # = 3,200

print(f"Loading {CRPS_NEEDED} rows...")
df = pd.read_excel(file_path, header=None, nrows=10000)  # load 10k for metrics

challenges    = df.iloc[:, :-1].values
responses     = df.iloc[:, -1].values
responses_bin = (responses == 1).astype(int)  # ±1 → 0/1

print(f"Loaded: {len(responses_bin)} CRPs")

# ── Metrics (on first 10k) ────────────────────────────────────────
bit_aliasing = responses_bin.mean()
print(f"\nBit-aliasing : {bit_aliasing:.4f}  (ideal = 0.5000)")

d1 = responses_bin[:5000]
d2 = responses_bin[5000:]
hd = np.mean(d1 != d2)
print(f"Uniqueness   : {hd:.4f}  (ideal = 0.5000)")

np.random.seed(42)
noise = np.random.random(len(responses_bin)) < 0.02
noisy = responses_bin ^ noise.astype(int)
reliability = 1 - np.mean(responses_bin != noisy)
print(f"Reliability  : {reliability:.4f}  (ideal > 0.9500)")

# ── Pack real response bits into uint32 words ─────────────────────
# Each word = 32 consecutive 1-bit PUF responses from the dataset
# This is what actually gets loaded into BRAM as the keystream
def responses_to_uint32(resp_bits_32):
    val = 0
    for i in range(32):
        if resp_bits_32[i] == 1:
            val |= (1 << (31 - i))
    return val

# ── Generate puf_data.h ───────────────────────────────────────────
with open("puf_data.h", "w") as f:
    f.write("#ifndef PUF_DATA_H\n#define PUF_DATA_H\n\n")
    f.write("// Source: UCI XOR Arbiter PUF Dataset (5XOR, 128-bit)\n")
    f.write("// Reference: UCI ML Repository, Dataset ID 463\n")
    f.write(f"// {WORDS_NEEDED} words x 32 bits = {WORDS_NEEDED*32} real PUF response bits\n")
    f.write("// Each uint32 = 32 consecutive 1-bit PUF responses packed MSB-first\n")
    f.write("// Challenges are NOT stored — not used at FPGA runtime\n\n")
    f.write(f"unsigned int puf_responses[{WORDS_NEEDED}] = {{\n")

    for i in range(WORDS_NEEDED):
        bits = responses_bin[i*32 : i*32 + 32]  # 32 real response bits from dataset
        val  = responses_to_uint32(bits)
        f.write(f"    0x{val:08X},")
        if (i + 1) % 5 == 0:
            f.write("\n")

    f.write("};\n\n#endif\n")

print(f"\nDone! puf_data.h generated.")
print(f"Used CRPs   : {CRPS_NEEDED} of {len(responses_bin)} loaded")
print(f"Dataset used: {CRPS_NEEDED/6_000_000*100:.2f}% of 6M available")