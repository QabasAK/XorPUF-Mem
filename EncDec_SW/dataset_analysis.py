import pandas as pd
import numpy as np

# Sorry for hardcoding the path
file_path = r"C:\Users\walki\OneDrive\Desktop\test_5xor_128dim.xlsx"

print("Loading first 10,000 rows...")
df = pd.read_excel(file_path, header=None, nrows=10000)

challenges = df.iloc[:, :-1].values
responses  = df.iloc[:, -1].values
responses_bin = (responses == 1).astype(int)

print(f"Loaded: {len(responses_bin)} CRPs")

# Metrics
bit_aliasing = responses_bin.mean()
print(f"Bit-aliasing: {bit_aliasing:.4f} (ideal = 0.5000)")

d1 = responses_bin[:5000]
d2 = responses_bin[5000:]
hd = np.mean(d1 != d2)
print(f"Uniqueness (approx): {hd:.4f} (ideal = 0.5000)")

np.random.seed(42)
noise = np.random.random(len(responses_bin)) < 0.02
noisy = responses_bin ^ noise.astype(int)
reliability = 1 - np.mean(responses_bin != noisy)
print(f"Reliability (simulated): {reliability:.4f} (ideal > 0.9500)")

# Generating puf_data.h from real data i guesssss
sample_challenges = challenges[:100]
sample_responses  = responses[:100]

def bits_to_uint32(bits):
    val = 0
    for i in range(32):
        if bits[i] == 1:
            val |= (1 << (31 - i))
    return val

def response_to_uint32(resp_val, challenge_bits):
    base = bits_to_uint32(challenge_bits)
    if resp_val == -1:
        base = ~base & 0xFFFFFFFF
    return base

with open("puf_data.h", "w") as f:
    f.write("#ifndef PUF_DATA_H\n#define PUF_DATA_H\n\n")
    f.write("// Source: UCI XOR Arbiter PUF Dataset (5XOR, 128-bit)\n")
    f.write("// Reference: UCI ML Repository, Dataset ID 463\n\n")
    f.write("unsigned int puf_challenges[100] = {\n")
    for i, bits in enumerate(sample_challenges):
        val = bits_to_uint32(bits)
        f.write(f"    0x{val:08X},")
        if (i + 1) % 5 == 0:
            f.write("\n")
    f.write("};\n\n")
    f.write("unsigned int puf_responses[100] = {\n")
    for i, (bits, resp) in enumerate(zip(sample_challenges, sample_responses)):
        val = response_to_uint32(resp, bits)
        f.write(f"    0x{val:08X},")
        if (i + 1) % 5 == 0:
            f.write("\n")
    f.write("};\n\n#endif\n")

print("\nDone! puf_data.h generated.")
print("\n── Metrics ──")
print(f"  Bit-aliasing : {bit_aliasing:.4f}")
print(f"  Uniqueness   : {hd:.4f}")
print(f"  Reliability  : {reliability:.4f}")