# Quantum Visual Secret Sharing (QVSS)

> **A quantum-domain adaptation of the Kapadiya et al. (2018) visual secret sharing scheme, enhanced with Quantum Parity Authentication (QPA) and Entanglement-Based Authentication (EBA) using NEQR image representation.**

---

## Overview

This repository implements a novel **Quantum Visual Secret Sharing** scheme that:

1. **Adapts Kapadiya et al. (2018) "Code 1"** — a classical meaningful visual secret sharing scheme — into the quantum domain using the **Novel Enhanced Quantum Representation (NEQR)** of images.
2. **Adds Quantum Parity Authentication (QPA)** — pixel-level tamper detection using CNOT-based parity ancilla qubits.
3. **Adds Entanglement-Based Authentication (EBA)** — eavesdropping detection using Bell-pair entanglement on share MSBs.

The result is a scheme where **two secret images** are split into **three meaningful shares** that:
- Look like innocent cover images (high SSIM ~0.98–0.99 vs covers)
- Perfectly recover both secrets (PSNR = +∞ dB for the MSB nibble)
- Detect any pixel-level tampering (QPA accuracy = 100%)
- Detect any eavesdropping during transmission (EBA accuracy = 100%)

---

## Scheme Architecture

```
Inputs:   G1, G2  (secret images)    C1, C2, C3  (cover images)
                        │
                        ▼
           ┌─────────────────────────┐
           │   NEQR Encoding         │  ← pixels → quantum registers
           │   Code 1 Share Logic    │  ← nibble-XOR mixing
           │   QPA (8 CNOTs/share)   │  ← parity ancilla per pixel
           │   EBA (Bell pair/share) │  ← entangled MSB ancilla
           └────────────┬────────────┘
                        │
                        ▼
           S1, S2, S3  (meaningful quantum shares)
                        │
           ┌────────────▼────────────┐
           │   NEQR Decoding         │
           │   QPA Verification      │  ← parity map comparison
           │   EBA Verification      │  ← Bell correlation check
           │   Secret Recovery       │  ← reverse Code 1 XOR
           └─────────────────────────┘
                        │
                        ▼
           R1, R2  (recovered secrets, PSNR = +∞ dB for MSB nibble)
```

### Share Generation (Code 1 — nibble level)

| Share | LSB nibble [3:0]              | MSB nibble [7:4] |
|-------|-------------------------------|------------------|
| S1    | G1[3:0] ⊕ G2[3:0]            | C1[7:4]          |
| S2    | S1[7:4] ⊕ G1[7:4]            | C2[7:4]          |
| S3    | S1[7:4] ⊕ S2[7:4] ⊕ G2[7:4] | C3[7:4]          |

Secret recovery: `R1 = S2[3:0] ⊕ S1[7:4]` and `R2 = S3[3:0] ⊕ S1[7:4] ⊕ S2[7:4]`

---

## Repository Structure

```
quantum-visual-secret-sharing/
│
├── README.md                                    ← this file
├── requirements.txt                             ← pip dependencies
├── environment.yml                              ← conda alternative
├── LICENSE                                      ← MIT
├── .gitignore
│
├── qvss_utils.py                                ← core library (NEQR, Code1, QPA, EBA)
│
├── notebooks (run in this order):
│   ├── 00  2018_classical_encode.ipynb          ← classical Kapadiya baseline encoder
│   ├── 00  2018_classical_decoding.ipynb        ← classical baseline decoder
│   ├── 01  encoding_eba_bigger_images.ipynb     ← MAIN: quantum encode → neqr_shares_eba/
│   ├── 02  decoding_verification_bigger_images.ipynb      ← MAIN: QPA+EBA verify + statistics
│   ├── 02  decoding_verification_robustness_bigger_images.ipynb ← robustness sweep (61 conditions)
│   ├── 02  biggimages.ipynb                     ← quick classical decode of 256×256 patch output
│   ├── 03  quantum_circuit_verification.ipynb   ← generates 8 Qiskit circuit diagrams
│   └── 03  new_encoding.ipynb                   ← share generation schematic figure
│
├── data/
│   ├── secret_1.tif … secret_4.tif             ← secret images (grayscale)
│   └── cover_1.tif  … cover_5.tif              ← cover images (grayscale)
│
├── neqr_shares_eba/                             ← PRE-COMPUTED quantum outputs
│   ├── set_A/                                   ← 32×32 full quantum simulation
│   │   ├── S1.png, S2.png, S3.png              ← encoded shares
│   │   ├── parity_S1.npy … parity_S3.npy       ← QPA parity maps
│   │   ├── eba_S1.npy … eba_S3.npy             ← EBA MSB maps
│   │   ├── G1_original.png, G2_original.png    ← source secrets
│   │   ├── C1_original.png … C3_original.png   ← source covers
│   │   ├── meta.json                            ← encoding parameters
│   │   └── proof_summary.png                   ← visual verification figure
│   └── patch_256x256_set_A/                     ← 256×256 patch-mode demo
│       └── [same structure as set_A]
│
├── share_generation_schematic.png               ← scheme diagram figure
├── visual_pipeline.png                          ← end-to-end visual pipeline figure
├── my_research_figure.png                       ← paper-quality results figure
│
└── outdated_and_broken/                         ← archived deprecated files (do not use)
```

---

## Verified Results

These results are pre-computed and stored in `neqr_shares_eba/`. **You can verify them without re-running the quantum simulation** by running notebook `02`.

| Metric | Value | Notes |
|--------|-------|-------|
| Share pixel mismatches | **0 / 1,024** | 32×32 full mode |
| PSNR (MSB nibble recovery) | **+∞ dB** | Perfect lossless recovery |
| MSE (MSB nibble) | **0.0** | Zero error |
| QPA accuracy | **100%** | Tamper detection, 32×32 |
| EBA accuracy | **100%** | Eavesdrop detection, 32×32 |
| Share PSNR vs covers | **~31.5–31.9 dB** | Meaningful shares |
| Share SSIM vs covers | **~0.98–0.99** | Near-identical appearance |
| 256×256 patch — share mismatches | **0 / 65,536** | Patch-mode demo |

---

## Quick Start

### 1. Clone

```bash
git clone https://github.com/<your-username>/quantum-visual-secret-sharing.git
cd quantum-visual-secret-sharing
```

### 2. Set up the environment

**Option A — pip (recommended):**
```bash
python -m venv .venv

# Windows
.venv\Scripts\activate

# Linux / macOS
source .venv/bin/activate

pip install -r requirements.txt
```

**Option B — conda:**
```bash
conda env create -f environment.yml
conda activate qvss
```

### 3. Launch Jupyter

```bash
jupyter notebook
```

---

## Notebook Execution Order

> ⚠️ **Simulation time warning:** The 32×32 full quantum mode takes **~15–20 minutes** on a modern laptop CPU. The 256×256 patch mode takes **~80–90 minutes**. The pre-computed outputs in `neqr_shares_eba/` let you skip re-running and go straight to verification (notebook `02`).

### Stage 00 — Classical Baseline (optional, ~1 min)

| Notebook | What it does | Output |
|----------|-------------|--------|
| `2018_classical_encode.ipynb` | Encodes secrets/covers using the original Kapadiya (2018) scheme at 512×512 | `universal_share.png`, `participant_share_1.png`, `participant_share_2.png` |
| `2018_classical_decoding.ipynb` | Decodes classical shares | PSNR ~31.6 / 30.8 dB |

### Stage 01 — Quantum Encoding (~15–90 min)

| Notebook | What it does | Output |
|----------|-------------|--------|
| `encoding_eba_bigger_images.ipynb` | Full NEQR + Code1 + QPA + EBA quantum encoding | `neqr_shares_eba/set_A/` (32×32) or `patch_256x256_set_A/` (256×256) |

**Key configuration variables** (Cell 1):

```python
PATCH_MODE = False   # True → 256×256 visual demo, False → 32×32 full quantum
IMAGE_SETS = [{'label': 'A', 'secret1': 'secret_1.tif', ...}]
SHOTS = 8192         # simulator shots per pixel (affects accuracy vs speed)
```

### Stage 02 — Quantum Decoding + Verification (~15 min)

| Notebook | What it does | Output |
|----------|-------------|--------|
| `decoding_verification_bigger_images.ipynb` | QPA + EBA decode-side verification, secret recovery, full statistics | `neqr_recovered_bigimages/set_A/` with PSNR, SSIM, histograms, tamper plots |
| `decoding_verification_robustness_bigger_images.ipynb` | Robustness sweep across 61 tamper conditions (0–50% tampering × 3 modes × 4 targets) | `neqr_robustness_bigimages/robustness_results.csv` |
| `biggimages.ipynb` | Classical fast decode of 256×256 patch output | Recovered images at 256×256 |

### Stage 03 — Figures Only (~1 min)

| Notebook | What it does | Output |
|----------|-------------|--------|
| `quantum_circuit_verification.ipynb` | Renders 8 annotated Qiskit circuit diagrams | PNG circuit diagrams |
| `new_encoding.ipynb` | Generates share generation schematic figure | `share_generation_schematic.png` |

---

## Reproducing the Key Result (without re-running simulation)

The fastest way to verify the implementation:

1. **Install dependencies** (Step 2 above)
2. **Open** `decoding_verification_bigger_images.ipynb`
3. **Run all cells** — it loads pre-computed shares from `neqr_shares_eba/set_A/` and runs the decode-side quantum verification circuits
4. **Expected output:**
   ```
   [QPA] Accuracy: 100.00% (1024/1024 pixels correct parity)
   [EBA] S1=100.00%  S2=100.00%  S3=100.00%
   [Recovery] PSNR(G1)=+inf dB  PSNR(G2)=+inf dB  MSE=0.0
   Share mismatches: 0/1024
   ```

---

## Technical Details

### Quantum Simulator

- **Backend:** `mqt.ddsim` DDSIMProvider (`qasm_simulator`)  
- **Why not IBM Qiskit Aer?** `mqt.ddsim` uses decision-diagram–based simulation, which is significantly more memory-efficient for the NEQR circuit structure used here.

### NEQR Circuit Structure (per pixel)

- **Position register:** ⌈log₂(ROWS)⌉ + ⌈log₂(COLS)⌉ qubits (10 qubits for 32×32)
- **Intensity register:** 8 qubits (one per bit plane)
- **QPA ancilla:** 1 qubit per share (8 CNOT gates → parity)
- **EBA ancilla:** 1 qubit per share (Hadamard + CNOT Bell pair on MSB)
- **Total qubits for 32×32:** ~83 qubits
- **Circuit depth:** ~63,000 gates

### Image Sizes

| Mode | Size | Pixels | Approx. sim time |
|------|------|--------|-----------------|
| Full quantum | 32×32 | 1,024 | ~15–20 min |
| Patch demo | 256×256 (tiled) | 65,536 | ~80–90 min |
| Classical baseline | 512×512 | 262,144 | <1 min |

### Recovery Limitation

Code 1 losslessly recovers the **4 MSB nibble** of each secret. The 4 LSBs are zeroed in the display image (`G_disp = (R & 0x0F) << 4`). This is a property of the original Kapadiya (2018) scheme, not of the quantum adaptation.

---

## References

1. Kapadiya, M., et al. (2018). *"A Novel (2,3) Visual Secret Sharing Scheme."* — Classical baseline adapted here.
2. Zhang, Y., Lu, K., Gao, Y., & Wang, M. (2013). *"NEQR: A novel enhanced quantum representation of digital images."* Quantum Information Processing, 12(8), 2833–2860.
3. Bennett, C. H., & Brassard, G. (1984). *"Quantum cryptography: Public key distribution and coin tossing."* — Basis for QPA and EBA.

---

## License

MIT — see [LICENSE](LICENSE).

---

## Citation

If you use this code in your research, please cite:

```
@misc{qvss2026,
  title   = {Quantum Visual Secret Sharing with QPA and EBA},
  year    = {2026},
  url     = {https://github.com/<your-username>/quantum-visual-secret-sharing}
}
```
