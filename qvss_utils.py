"""
qvss_utils.py
=============
Shared utilities for the QVSS scheme.
Imported by encoding_eba.ipynb, decoding_verification.ipynb,
and decoding_verification_robustness.ipynb.

Functions cover:
  - Classical helpers  (parity, entropy, metrics, correlation)
  - NEQR quantum gates (encode_neqr, add_qpa, add_eba)
  - Circuit builders   (build_encoding_circuit,
                        build_share_qpa_eba_circuit,
                        build_decoding_circuit)
  - Result parsers     (parse_encoding_results,
                        parse_qpa_eba_counts,
                        parse_recovery)
  - Classical decode   (classical_decode, extract_secret_nibble)
  - Auth comparators   (compare_parity_maps, compare_eba_maps)
"""

import math
import numpy as np

# ─────────────────────────────────────────────────────────────────────
# CONSTANTS
# ─────────────────────────────────────────────────────────────────────
BITS = 8   # intensity bits per pixel (NEQR uses 8)


# ─────────────────────────────────────────────────────────────────────
# POSITION HELPERS
# ─────────────────────────────────────────────────────────────────────

def get_npos(rows, cols):
    """Return (npy, npx, npos) for an image of shape rows×cols."""
    npy = max(1, math.ceil(math.log2(rows))) if rows > 1 else 1
    npx = max(1, math.ceil(math.log2(cols))) if cols > 1 else 1
    return npy, npx, npy + npx


def parse_position(cpos_val, npy, npx, rows, cols):
    """
    Decode a classical register integer value into (y, x) pixel coords.
    pos register layout: pos[0..npy-1] = Y bits, pos[npy..npy+npx-1] = X bits
    Returns (None, None) if out-of-bounds.
    """
    y = cpos_val & ((1 << npy) - 1)
    x = (cpos_val >> npy) & ((1 << npx) - 1)
    if y >= rows or x >= cols:
        return None, None
    return y, x


# ─────────────────────────────────────────────────────────────────────
# CLASSICAL HELPERS
# ─────────────────────────────────────────────────────────────────────

def to_bits(v, n):
    """Return list of n bits of integer v (LSB first)."""
    return [(v >> i) & 1 for i in range(n)]


def classical_parity(val):
    """XOR of all 8 bits of val."""
    p = 0
    for b in range(8):
        p ^= (val >> b) & 1
    return p


def image_entropy(img):
    """Shannon entropy in bits for a uint8 image."""
    hist, _ = np.histogram(img.flatten(), bins=256, range=(0, 255))
    p = hist / (img.size + 1e-12)
    return float(-np.sum(p * np.log2(p + 1e-10)))


def calc_metrics(orig, rec):
    """
    Return dict with MSE, PSNR (dB), SSIM, and px_mismatch
    between two uint8 images of the same shape.
    """
    orig_f = orig.astype(float)
    rec_f  = rec.astype(float)
    mse    = float(np.mean((orig_f - rec_f) ** 2))
    psnr   = 10.0 * np.log10(255.0 ** 2 / mse) if mse > 0 else float('inf')
    C1, C2 = (0.01 * 255) ** 2, (0.03 * 255) ** 2
    m1, m2 = orig_f.mean(), rec_f.mean()
    s1, s2 = orig_f.var(),  rec_f.var()
    s12    = float(np.mean((orig_f - m1) * (rec_f - m2)))
    ssim   = ((2*m1*m2 + C1) * (2*s12 + C2)) / ((m1**2 + m2**2 + C1) * (s1 + s2 + C2))
    return {
        'MSE':         mse,
        'PSNR':        psnr,
        'SSIM':        float(ssim),
        'px_mismatch': int(np.sum(orig != rec)),
    }


def correlation_coefficient(img, direction='horizontal'):
    """
    Pearson correlation coefficient of adjacent pixels.
    direction: 'horizontal' | 'vertical' | 'diagonal'
    """
    f = img.astype(float)
    if direction == 'horizontal':
        a, b = f[:, :-1].flatten(), f[:, 1:].flatten()
    elif direction == 'vertical':
        a, b = f[:-1, :].flatten(), f[1:, :].flatten()
    elif direction == 'diagonal':
        a, b = f[:-1, :-1].flatten(), f[1:, 1:].flatten()
    else:
        raise ValueError(f"Unknown direction: {direction}")
    num = np.sum((a - a.mean()) * (b - b.mean()))
    den = np.sqrt(np.sum((a - a.mean()) ** 2) * np.sum((b - b.mean()) ** 2))
    return float(num / den) if den > 1e-12 else 0.0


# ─────────────────────────────────────────────────────────────────────
# QUANTUM GATE BUILDERS  (add to an existing QuantumCircuit)
# ─────────────────────────────────────────────────────────────────────

def encode_neqr(qc, img, intensity_qubits, pos_qubits,
                rows, cols, npy, npx, bits=8):
    """
    NEQR encoding: for each pixel (y,x) with value v, apply
    multi-controlled-X gates to set intensity qubits when the
    position register matches (y,x).
    """
    for y in range(rows):
        for x in range(cols):
            pixel_val  = int(img[y, x])
            pixel_bits = to_bits(pixel_val, bits)
            pos_y      = to_bits(y, npy)
            pos_x      = to_bits(x, npx)
            for bit_idx, bit_val in enumerate(pixel_bits):
                if bit_val == 1:
                    # Flip pos qubits where the address bit is 0
                    for i, p in enumerate(pos_y):
                        if not p:
                            qc.x(pos_qubits[i])
                    for i, p in enumerate(pos_x):
                        if not p:
                            qc.x(pos_qubits[npy + i])
                    # Multi-controlled-X: set intensity bit
                    qc.mcx(list(pos_qubits), intensity_qubits[bit_idx])
                    # Unflip
                    for i, p in enumerate(pos_y):
                        if not p:
                            qc.x(pos_qubits[i])
                    for i, p in enumerate(pos_x):
                        if not p:
                            qc.x(pos_qubits[npy + i])


def add_qpa(qc, share_regs, qpa_ancilla_regs, bits=8):
    """
    QPA: Quantum Parity Authentication.
    qpa_anc_i = Si[0] XOR Si[1] XOR ... XOR Si[7]  (8 CNOT per share, 24 total).
    """
    for s_reg, anc_reg in zip(share_regs, qpa_ancilla_regs):
        for b in range(bits):
            qc.cx(s_reg[b], anc_reg[0])


def add_eba(qc, share_regs, eba_anc_regs, eba_tag_regs):
    """
    EBA: Entanglement-Based Authentication (C7 circuit).
    Per share Si:
      H(anc_i)            -> superposition
      CNOT(anc_i, tag_i)  -> Bell state |Phi+>
      CNOT(Si[7], tag_i)  -> entangle MSB with Bell pair
    Verification: MSB==0 => anc==tag (corr); MSB==1 => anc!=tag (anti-corr).
    Adversarial measurement collapses Bell state => correlation drops to ~50%.
    """
    for s_reg, anc_reg, tag_reg in zip(share_regs, eba_anc_regs, eba_tag_regs):
        qc.h(anc_reg[0])
        qc.cx(anc_reg[0], tag_reg[0])
        qc.cx(s_reg[7],   tag_reg[0])


# ─────────────────────────────────────────────────────────────────────
# CIRCUIT BUILDERS
# ─────────────────────────────────────────────────────────────────────

def build_encoding_circuit(secrets, covers, rows, cols, n_secrets=2):
    """
    Build the full NEQR + Code1 + QPA + EBA encoding circuit.

    Parameters
    ----------
    secrets  : list of n_secrets uint8 arrays (rows×cols)
    covers   : list of (n_secrets+1) uint8 arrays (rows×cols)
    rows, cols : image dimensions (must be powers of 2)
    n_secrets  : number of secret images (default 2)

    Returns
    -------
    qc : QuantumCircuit
    """
    from qiskit import QuantumCircuit, QuantumRegister, ClassicalRegister

    npy, npx, npos = get_npos(rows, cols)
    n_covers = n_secrets + 1   # C1, C2, C3

    # ── Quantum registers ─────────────────────────────────────────────
    pos     = QuantumRegister(npos, 'pos')
    G_regs  = [QuantumRegister(BITS, f'G{i+1}') for i in range(n_secrets)]
    C_regs  = [QuantumRegister(BITS, f'C{i+1}') for i in range(n_covers)]
    S1      = QuantumRegister(BITS, 'S1')
    S2      = QuantumRegister(BITS, 'S2')
    S3      = QuantumRegister(BITS, 'S3')
    QPA     = [QuantumRegister(1, f'qpa{i+1}')     for i in range(3)]
    EBA_anc = [QuantumRegister(1, f'eba_anc{i+1}') for i in range(3)]
    EBA_tag = [QuantumRegister(1, f'eba_tag{i+1}') for i in range(3)]

    # ── Classical registers ───────────────────────────────────────────
    c_pos     = ClassicalRegister(npos, 'cpos')
    c_S1      = ClassicalRegister(BITS, 'cS1')
    c_S2      = ClassicalRegister(BITS, 'cS2')
    c_S3      = ClassicalRegister(BITS, 'cS3')
    c_qpa     = [ClassicalRegister(1, f'cqpa{i+1}')     for i in range(3)]
    c_eba_anc = [ClassicalRegister(1, f'c_eba_anc{i+1}') for i in range(3)]
    c_eba_tag = [ClassicalRegister(1, f'c_eba_tag{i+1}') for i in range(3)]

    # ── Assemble circuit ──────────────────────────────────────────────
    qc = QuantumCircuit(pos)
    for g in G_regs: qc.add_register(g)
    for c in C_regs: qc.add_register(c)
    qc.add_register(S1); qc.add_register(S2); qc.add_register(S3)
    for q in QPA:       qc.add_register(q)
    for q in EBA_anc:   qc.add_register(q)
    for q in EBA_tag:   qc.add_register(q)
    qc.add_register(c_pos)
    qc.add_register(c_S1); qc.add_register(c_S2); qc.add_register(c_S3)
    for c in c_qpa:     qc.add_register(c)
    for c in c_eba_anc: qc.add_register(c)
    for c in c_eba_tag: qc.add_register(c)

    # ── Phase 1: H on position register ──────────────────────────────
    qc.h(pos)
    qc.barrier(label='H')

    # ── Phase 2: NEQR encode secrets and covers ───────────────────────
    for i in range(n_secrets):
        encode_neqr(qc, secrets[i], list(G_regs[i]), list(pos), rows, cols, npy, npx)
        qc.barrier(label=f'G{i+1}')
    for i in range(n_covers):
        encode_neqr(qc, covers[i], list(C_regs[i]), list(pos), rows, cols, npy, npx)
        qc.barrier(label=f'C{i+1}')

    # ── Phase 3: Code 1 share generation ─────────────────────────────
    # S1[LSB4] = G1[LSB4] XOR G2[LSB4]
    for b in range(4):
        qc.cx(G_regs[0][b], S1[b])
        qc.cx(G_regs[1][b], S1[b])
    # S1[MSB4] = C1[MSB4]
    for b in range(4, 8):
        qc.cx(C_regs[0][b], S1[b])
    qc.barrier(label='S1')

    # S2[LSB4] = S1[MSB4] XOR G1[MSB4]
    for b in range(4):
        qc.cx(S1[b + 4], S2[b])
        qc.cx(G_regs[0][b + 4], S2[b])
    # S2[MSB4] = C2[MSB4]
    for b in range(4, 8):
        qc.cx(C_regs[1][b], S2[b])
    qc.barrier(label='S2')

    # S3[LSB4] = S1[MSB4] XOR S2[MSB4] XOR G2[MSB4]
    for b in range(4):
        qc.cx(S1[b + 4], S3[b])
        qc.cx(S2[b + 4], S3[b])
        qc.cx(G_regs[1][b + 4], S3[b])
    # S3[MSB4] = C3[MSB4]
    for b in range(4, 8):
        qc.cx(C_regs[2][b], S3[b])
    qc.barrier(label='S3')

    # ── Phase 4: QPA ──────────────────────────────────────────────────
    add_qpa(qc, [S1, S2, S3], QPA)
    qc.barrier(label='QPA')

    # ── Phase 5: EBA ──────────────────────────────────────────────────
    add_eba(qc, [S1, S2, S3], EBA_anc, EBA_tag)
    qc.barrier(label='EBA')

    # ── Phase 6: Measure ──────────────────────────────────────────────
    qc.measure(pos, c_pos)
    qc.measure(S1, c_S1); qc.measure(S2, c_S2); qc.measure(S3, c_S3)
    for i in range(3):
        qc.measure(QPA[i][0],     c_qpa[i][0])
        qc.measure(EBA_anc[i][0], c_eba_anc[i][0])
        qc.measure(EBA_tag[i][0], c_eba_tag[i][0])

    return qc


def build_share_qpa_eba_circuit(shares_dict, rows, cols):
    """
    Build a decode-side verification circuit:
    NEQR-encode the received shares + QPA parity chain + EBA Bell check.
    Used at decode time to verify share integrity and detect eavesdropping.

    Bitstring register order (last registered = leftmost in split):
      c_eba_tag3 c_eba_tag2 c_eba_tag1
      c_eba_anc3 c_eba_anc2 c_eba_anc1
      cqpa3 cqpa2 cqpa1
      cS3 cS2 cS1 cpos
    Total: 13 space-separated parts.
    """
    from qiskit import QuantumCircuit, QuantumRegister, ClassicalRegister

    npy, npx, npos = get_npos(rows, cols)

    pos = QuantumRegister(npos, 'pos')
    S1  = QuantumRegister(BITS,  'S1')
    S2  = QuantumRegister(BITS,  'S2')
    S3  = QuantumRegister(BITS,  'S3')
    QPA     = [QuantumRegister(1, f'qpa{i+1}')     for i in range(3)]
    EBA_anc = [QuantumRegister(1, f'eba_anc{i+1}') for i in range(3)]
    EBA_tag = [QuantumRegister(1, f'eba_tag{i+1}') for i in range(3)]

    c_pos     = ClassicalRegister(npos, 'cpos')
    c_S1      = ClassicalRegister(BITS, 'cS1')
    c_S2      = ClassicalRegister(BITS, 'cS2')
    c_S3      = ClassicalRegister(BITS, 'cS3')
    c_qpa     = [ClassicalRegister(1, f'cqpa{i+1}')      for i in range(3)]
    c_eba_anc = [ClassicalRegister(1, f'c_eba_anc{i+1}') for i in range(3)]
    c_eba_tag = [ClassicalRegister(1, f'c_eba_tag{i+1}') for i in range(3)]

    qc = QuantumCircuit(pos, S1, S2, S3)
    for q in QPA:       qc.add_register(q)
    for q in EBA_anc:   qc.add_register(q)
    for q in EBA_tag:   qc.add_register(q)
    qc.add_register(c_pos)
    qc.add_register(c_S1); qc.add_register(c_S2); qc.add_register(c_S3)
    for c in c_qpa:     qc.add_register(c)
    for c in c_eba_anc: qc.add_register(c)
    for c in c_eba_tag: qc.add_register(c)

    qc.h(pos)
    qc.barrier(label='H')
    encode_neqr(qc, shares_dict['S1'], list(S1), list(pos), rows, cols, npy, npx)
    qc.barrier(label='S1')
    encode_neqr(qc, shares_dict['S2'], list(S2), list(pos), rows, cols, npy, npx)
    qc.barrier(label='S2')
    encode_neqr(qc, shares_dict['S3'], list(S3), list(pos), rows, cols, npy, npx)
    qc.barrier(label='S3')
    add_qpa(qc, [S1, S2, S3], QPA)
    qc.barrier(label='QPA')
    add_eba(qc, [S1, S2, S3], EBA_anc, EBA_tag)
    qc.barrier(label='EBA')

    qc.measure(pos, c_pos)
    qc.measure(S1, c_S1); qc.measure(S2, c_S2); qc.measure(S3, c_S3)
    for i in range(3):
        qc.measure(QPA[i][0],     c_qpa[i][0])
        qc.measure(EBA_anc[i][0], c_eba_anc[i][0])
        qc.measure(EBA_tag[i][0], c_eba_tag[i][0])

    return qc


def build_decoding_circuit(shares, rows, cols):
    """
    Build the Code 1 reverse logic recovery circuit.
    Recovers R1 (contains G1[MSB4]) and R2 (contains G2[MSB4]).
    """
    from qiskit import QuantumCircuit, QuantumRegister, ClassicalRegister

    npy, npx, npos = get_npos(rows, cols)

    pos   = QuantumRegister(npos, 'pos')
    S1    = QuantumRegister(BITS, 'S1')
    S2    = QuantumRegister(BITS, 'S2')
    S3    = QuantumRegister(BITS, 'S3')
    R1    = QuantumRegister(BITS, 'R1')
    R2    = QuantumRegister(BITS, 'R2')
    c_pos = ClassicalRegister(npos, 'cpos')
    c_R1  = ClassicalRegister(BITS, 'cR1')
    c_R2  = ClassicalRegister(BITS, 'cR2')

    qc = QuantumCircuit(pos, S1, S2, S3, R1, R2, c_pos, c_R1, c_R2)

    qc.h(pos)
    qc.barrier(label='H')
    encode_neqr(qc, shares['S1'], list(S1), list(pos), rows, cols, npy, npx)
    qc.barrier(label='S1')
    encode_neqr(qc, shares['S2'], list(S2), list(pos), rows, cols, npy, npx)
    qc.barrier(label='S2')
    encode_neqr(qc, shares['S3'], list(S3), list(pos), rows, cols, npy, npx)
    qc.barrier(label='S3')

    # Code 1 reverse:
    # R1[b]   = S1[b+4] XOR S2[b]               for b in 0-3  → R1[LSB4] = G1[MSB4]
    # R1[b+4] = S1[b]                            for b in 0-3  → R1[MSB4] = G1[LSB4]^G2[LSB4]
    for b in range(4):
        qc.cx(S1[b + 4], R1[b])
        qc.cx(S2[b],     R1[b])
    for b in range(4):
        qc.cx(S1[b], R1[b + 4])
    qc.barrier(label='R1')

    # R2[b]   = S1[b+4] XOR S2[b+4] XOR S3[b]  for b in 0-3  → R2[LSB4] = G2[MSB4]
    # R2[b]   = S3[b]                            for b in 4-7  → R2[MSB4] = C3[MSB4]
    for b in range(4):
        qc.cx(S1[b + 4], R2[b])
        qc.cx(S2[b + 4], R2[b])
        qc.cx(S3[b],     R2[b])
    for b in range(4, 8):
        qc.cx(S3[b], R2[b])
    qc.barrier(label='R2')

    qc.measure(pos, c_pos)
    qc.measure(R1, c_R1)
    qc.measure(R2, c_R2)

    return qc


# ─────────────────────────────────────────────────────────────────────
# RESULT PARSERS
# ─────────────────────────────────────────────────────────────────────

def parse_encoding_results(counts, rows, cols):
    """
    Parse counts from build_encoding_circuit.
    Bitstring (13 space-separated parts, Qiskit register order reversed):
      [0] c_eba_tag3  [1] c_eba_tag2  [2] c_eba_tag1
      [3] c_eba_anc3  [4] c_eba_anc2  [5] c_eba_anc1
      [6] cqpa3       [7] cqpa2       [8] cqpa1
      [9] cS3        [10] cS2        [11] cS1   [12] cpos

    Returns
    -------
    shares      : {'S1': arr, 'S2': arr, 'S3': arr}
    parity_maps : {'S1': arr, 'S2': arr, 'S3': arr}  (-1 = not yet seen)
    qpa_stats   : {'S1': {'correct': N, 'wrong': N}, ...}
    eba_stats   : {'S1': {'correct': N, 'wrong': N}, ...}
    """
    npy, npx, npos = get_npos(rows, cols)
    keys = ['S1', 'S2', 'S3']

    shares      = {k: np.zeros((rows, cols), np.uint8) for k in keys}
    parity_maps = {k: -np.ones((rows, cols), int)      for k in keys}
    qpa_stats   = {k: {'correct': 0, 'wrong': 0}       for k in keys}
    eba_stats   = {k: {'correct': 0, 'wrong': 0}       for k in keys}

    votes        = {(y, x): {k: {} for k in keys} for y in range(rows) for x in range(cols)}
    parity_votes = {(y, x): {k: {} for k in keys} for y in range(rows) for x in range(cols)}

    for bitstring, count in counts.items():
        parts = bitstring.split()
        if len(parts) != 13:
            continue

        # EBA: tag and anc per share (S1=index 2/5, S2=1/4, S3=0/3)
        eba_tag = [int(parts[2], 2), int(parts[1], 2), int(parts[0], 2)]  # S1,S2,S3
        eba_anc = [int(parts[5], 2), int(parts[4], 2), int(parts[3], 2)]  # S1,S2,S3
        qpa_meas= [int(parts[8], 2), int(parts[7], 2), int(parts[6], 2)]  # S1,S2,S3
        s_vals  = [int(parts[11],2), int(parts[10],2), int(parts[9], 2)]  # S1,S2,S3
        cpos    = int(parts[12], 2)

        y, x = parse_position(cpos, npy, npx, rows, cols)
        if y is None:
            continue

        for idx, sname in enumerate(keys):
            val = s_vals[idx]
            votes[(y, x)][sname][val] = votes[(y, x)][sname].get(val, 0) + count

            # QPA: measured parity must equal classical parity of measured share
            mp  = qpa_meas[idx]
            exp = classical_parity(val)
            if mp == exp:
                qpa_stats[sname]['correct'] += count
            else:
                qpa_stats[sname]['wrong'] += count
            parity_votes[(y, x)][sname][mp] = parity_votes[(y, x)][sname].get(mp, 0) + count

            # EBA: MSB==0 → anc==tag; MSB==1 → anc!=tag
            msb = (val >> 7) & 1
            correct_eba = (eba_anc[idx] == eba_tag[idx]) if msb == 0 \
                     else (eba_anc[idx] != eba_tag[idx])
            if correct_eba:
                eba_stats[sname]['correct'] += count
            else:
                eba_stats[sname]['wrong'] += count

    # Majority vote reconstruction
    for y in range(rows):
        for x in range(cols):
            for sname in keys:
                d = votes[(y, x)][sname]
                if d:
                    shares[sname][y, x] = max(d, key=d.get)
                d2 = parity_votes[(y, x)][sname]
                if d2:
                    parity_maps[sname][y, x] = max(d2, key=d2.get)

    return shares, parity_maps, qpa_stats, eba_stats


def parse_qpa_eba_counts(counts, rows, cols):
    """
    Parse counts from build_share_qpa_eba_circuit (decode-side verification).
    Same bitstring layout as parse_encoding_results (13 parts).
    Returns shares, parity_maps, qpa_stats, eba_stats.
    """
    # Identical layout — reuse encoding parser
    return parse_encoding_results(counts, rows, cols)


def parse_recovery(counts, rows, cols):
    """
    Parse counts from build_decoding_circuit.
    Bitstring (3 parts): cR2 cR1 cpos
    Returns {'R1': arr, 'R2': arr}
    """
    npy, npx, _ = get_npos(rows, cols)
    rec   = {k: np.zeros((rows, cols), np.uint8) for k in ['R1', 'R2']}
    votes = {(y, x): {k: {} for k in ['R1', 'R2']}
             for y in range(rows) for x in range(cols)}

    for bitstring, count in counts.items():
        parts = bitstring.split()
        if len(parts) < 3:
            continue
        cpos = int(parts[2], 2)
        y, x = parse_position(cpos, npy, npx, rows, cols)
        if y is None:
            continue
        for name, vstr in [('R1', parts[1]), ('R2', parts[0])]:
            val = int(vstr, 2)
            votes[(y, x)][name][val] = votes[(y, x)][name].get(val, 0) + count

    for y in range(rows):
        for x in range(cols):
            for name in ('R1', 'R2'):
                d = votes[(y, x)][name]
                if d:
                    rec[name][y, x] = max(d, key=d.get)
    return rec


# ─────────────────────────────────────────────────────────────────────
# CLASSICAL DECODE
# ─────────────────────────────────────────────────────────────────────

def classical_decode(shares, rows, cols):
    """
    Apply Code 1 reverse logic to share arrays (no quantum circuit).
    Algebraically identical to build_decoding_circuit measurement output.

    R1[LSB4] = S1[MSB4] XOR S2[LSB4]   → = G1[MSB4]  (verified)
    R1[MSB4] = S1[LSB4]                 → = G1[LSB4] XOR G2[LSB4]
    R2[LSB4] = S1[MSB4] XOR S2[MSB4] XOR S3[LSB4]  → = G2[MSB4]
    R2[MSB4] = S3[MSB4]                 → = C3[MSB4]
    """
    S1 = shares['S1'].astype(np.uint16)
    S2 = shares['S2'].astype(np.uint16)
    S3 = shares['S3'].astype(np.uint16)
    R1 = np.zeros((rows, cols), np.uint16)
    R2 = np.zeros((rows, cols), np.uint16)

    for b in range(4):
        R1 |= (((S1 >> (b + 4)) & 1) ^ ((S2 >> b) & 1)) << b
        R1 |= ((S1 >> b) & 1) << (b + 4)

    for b in range(4):
        R2 |= (((S1 >> (b + 4)) & 1) ^ ((S2 >> (b + 4)) & 1) ^ ((S3 >> b) & 1)) << b
    for b in range(4, 8):
        R2 |= ((S3 >> b) & 1) << b

    return R1.astype(np.uint8), R2.astype(np.uint8)


def extract_secret_nibble(R1, R2):
    """
    Extract the correctly recovered MSB nibble and shift for display/comparison.
    R1[LSB4] = G1[MSB4]  →  display_G1 = (R1 & 0x0F) << 4
    R2[LSB4] = G2[MSB4]  →  display_G2 = (R2 & 0x0F) << 4
    """
    return ((R1 & 0x0F) << 4).astype(np.uint8), \
           ((R2 & 0x0F) << 4).astype(np.uint8)


# ─────────────────────────────────────────────────────────────────────
# AUTHENTICATION MAP COMPARATORS
# ─────────────────────────────────────────────────────────────────────

def compare_parity_maps(enc_parity, dec_parity, rows, cols, label=''):
    """
    Compare encoding-time vs decode-time parity maps pixel by pixel.
    Returns dict per share with match%, mismatch count, and tamper_map array.
    QPA tamper detection: mismatch at (y,x) means that pixel was tampered.
    """
    results = {}
    for sname in ['S1', 'S2', 'S3']:
        ep = np.array(enc_parity[sname])
        dp = dec_parity[sname]
        valid = (ep >= 0) & (dp >= 0)
        if valid.any():
            match      = int(np.sum(ep[valid] == dp[valid]))
            total      = int(valid.sum())
            mismatch   = total - match
            tamper_map = np.where(valid & (ep != dp), 1, 0).astype(np.uint8)
            match_pct  = 100.0 * match / total
            status     = 'AUTHENTIC' if mismatch == 0 else f'TAMPERED ({mismatch} pixels)'
            print(f'  {sname} [{label}]: {match}/{total} match '
                  f'({match_pct:.2f}%)  -> {status}')
            results[sname] = {
                'match':      match,
                'mismatch':   mismatch,
                'total':      total,
                'match_pct':  match_pct,
                'tamper_map': tamper_map,
            }
        else:
            results[sname] = {'match': 0, 'mismatch': 0, 'total': 0,
                              'match_pct': 0.0,
                              'tamper_map': np.zeros((rows, cols), np.uint8)}
    return results


def compare_eba_maps(enc_eba_map, dec_shares, rows, cols, label=''):
    """
    Compare encoding-time MSB map (eba_map) vs MSB of received shares.
    EBA tamper detection: if MSB changed, that pixel was (MSB-level) tampered.
    Returns dict per share with detection stats and tamper_map.
    """
    results = {}
    for sname in ['S1', 'S2', 'S3']:
        enc_msb = enc_eba_map[sname]                        # 0/1 per pixel
        dec_msb = ((dec_shares[sname] >> 7) & 1).astype(int)
        tamper_map = (enc_msb != dec_msb).astype(np.uint8)
        detected   = int(tamper_map.sum())
        total      = rows * cols
        det_pct    = 100.0 * detected / total
        status     = 'CLEAN' if detected == 0 else f'MSB TAMPERED ({detected} pixels)'
        print(f'  {sname} [{label}]: {detected}/{total} MSB changes '
              f'({det_pct:.2f}%)  -> {status}')
        results[sname] = {
            'detected':    detected,
            'total':       total,
            'det_pct':     det_pct,
            'tamper_map':  tamper_map,
        }
    return results


def eba_accuracy(eba_stats):
    """Return per-share EBA accuracy percentage from eba_stats dict."""
    acc = {}
    for sname, st in eba_stats.items():
        total = st['correct'] + st['wrong']
        acc[sname] = 100.0 * st['correct'] / total if total > 0 else 0.0
    return acc


# ─────────────────────────────────────────────────────────────────────
# TAMPERING UTILITIES  (for robustness study)
# ─────────────────────────────────────────────────────────────────────

def apply_tampering(shares, pct, mode, target, rows, cols, seed=42):
    """
    Tamper copies of shares.

    Parameters
    ----------
    shares  : {'S1': arr, 'S2': arr, 'S3': arr}
    pct     : float  percentage of pixels to tamper (0–100)
    mode    : 'msb' | 'lsb' | 'random' | 'full'
    target  : 'S1_only' | 'S3_only' | 'all'
    seed    : random seed for reproducibility

    Returns
    -------
    tampered : dict  (modified copies)
    masks    : dict  boolean arrays  (which pixels were tampered per share)
    """
    np.random.seed(seed)
    tampered = {k: v.copy() for k, v in shares.items()}
    masks    = {k: np.zeros((rows, cols), bool) for k in shares}

    targets_list = {
        'S1_only': ['S1'],
        'S3_only': ['S3'],
        'all':     ['S1', 'S2', 'S3'],
    }[target]

    for sname in targets_list:
        img  = tampered[sname].copy()
        mask = np.random.random((rows, cols)) < (pct / 100.0)
        masks[sname] = mask
        if mode == 'msb':
            img[mask] ^= 0x80
        elif mode == 'lsb':
            img[mask] ^= 0x01
        elif mode == 'random':
            positions    = np.argwhere(mask)
            bits_to_flip = np.random.randint(0, 8, len(positions))
            for (y, x), b in zip(positions, bits_to_flip):
                img[y, x] ^= (1 << b)
        elif mode == 'full':
            img[mask] ^= 0xFF
        tampered[sname] = img

    return tampered, masks
