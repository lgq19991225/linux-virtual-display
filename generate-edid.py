#!/usr/bin/env python3
"""Generate EDID binary for a given resolution and refresh rate.

Usage:
  python3 generate-edid.py [--width W] [--height H] [--refresh R] [output]
  python3 generate-edid.py [-w W] [-h H] [-r R] [output]

Defaults: 1920x1080@60
"""

import argparse
import struct
import sys
import math


def cvt_rb_timings(width, height, refresh):
    """Compute CVT Reduced Blanking timing parameters."""
    h_front = 48
    h_sync = 32
    h_back = 80
    h_blank = h_front + h_sync + h_back
    h_total = width + h_blank

    v_front = 3
    v_sync = 6
    v_back = max(1, int((height - 200) / 400 * 6))
    # round up v back porch to make v_total even
    v_blank = v_front + v_sync + v_back
    v_total = height + v_blank
    if v_total % 2:
        v_total += 1
        v_back += 1
    v_blank = v_front + v_sync + v_back

    pixel_clock_10khz = int(math.ceil(h_total * v_total * refresh / 10000))

    him_mm = int(width * 0.28)
    vim_mm = int(height * 0.28)

    return {
        'clock': pixel_clock_10khz,
        'ha': width, 'hb': h_blank,
        'va': height, 'vb': v_blank,
        'hso': h_front, 'hsp': h_sync,
        'vso': v_front, 'vsp': v_sync,
        'him': him_mm, 'vim': vim_mm,
    }


def make_edid(t):
    """Build a 128-byte EDID blob from timing dict t."""
    edid = bytearray(128)

    # 0-7: Header
    edid[0:8] = b'\x00\xFF\xFF\xFF\xFF\xFF\xFF\x00'

    # 8-9: Manufacturer "VTM"
    mfr = (22 << 10) | (20 << 5) | 13
    struct.pack_into('>H', edid, 8, mfr)

    # 10-11: Product code
    struct.pack_into('<H', edid, 10, 0x0001)

    # 12-15: Serial
    edid[12:16] = b'\x00\x00\x00\x00'

    # 16-17: Week/Year
    edid[16] = 1
    edid[17] = 35

    # 18-19: EDID v1.4
    edid[18] = 1
    edid[19] = 4

    # 20: Digital input
    edid[20] = 0x80

    # 21-22: Screen size (cm)
    edid[21] = max(1, min(255, t['him'] // 10))
    edid[22] = max(1, min(255, t['vim'] // 10))

    # 23: Gamma 2.2
    edid[23] = 0x78

    # 24: Features
    edid[24] = 0x06

    # 25-34: Chromaticity (sRGB)
    rx, ry = 655, 338
    gx, gy = 307, 614
    bx, by = 154, 61
    wx, wy = 320, 337

    edid[25] = (rx >> 2) & 0xFF
    edid[26] = ((ry >> 2) & 0xFC) | ((gx >> 8) & 0x03)
    edid[27] = ((gx >> 2) & 0xFC) | ((gy >> 8) & 0x03)
    edid[28] = ((gy >> 2) & 0xFC) | ((bx >> 8) & 0x03)
    edid[29] = ((bx >> 2) & 0xFC) | ((by >> 8) & 0x03)
    edid[30] = ((by >> 2) & 0xFC) | ((wx >> 8) & 0x03)
    edid[31] = ((wx >> 2) & 0xFC) | ((wy >> 8) & 0x03)
    edid[32] = ((wy >> 2) & 0xFC)
    edid[33] = 0x00
    edid[34] = 0x00

    # 35-37: Established timings (none)
    edid[35:38] = b'\x00\x00\x00'

    # 38-53: Standard timings (all unused)
    for i in range(38, 54):
        edid[i] = 0x01

    # 54-71: Detailed timing #1
    dt1 = bytearray(18)
    struct.pack_into('<H', dt1, 0, t['clock'])
    ha, hb = t['ha'], t['hb']
    va, vb = t['va'], t['vb']
    hso, hsp = t['hso'], t['hsp']
    vso, vsp = t['vso'], t['vsp']
    him, vim = t['him'], t['vim']

    dt1[2] = ha & 0xFF
    dt1[3] = hb & 0xFF
    dt1[4] = ((ha >> 8) & 0x0F) << 4 | ((hb >> 8) & 0x0F)
    dt1[5] = va & 0xFF
    dt1[6] = vb & 0xFF
    dt1[7] = ((va >> 8) & 0x0F) << 4 | ((vb >> 8) & 0x0F)
    dt1[8] = hso & 0xFF
    dt1[9] = hsp & 0xFF
    dt1[10] = ((vso & 0x0F) << 4) | (vsp & 0x0F)
    dt1[11] = 0x00
    dt1[12] = him & 0xFF
    dt1[13] = vim & 0xFF
    dt1[14] = ((him >> 8) & 0x0F) << 4 | ((vim >> 8) & 0x0F)
    dt1[15] = 0
    dt1[16] = 0
    dt1[17] = 0x00
    edid[54:72] = dt1

    # 72-89: Monitor name
    md2 = bytearray(18)
    md2[0:5] = b'\x00\x00\x00\xFC\x00'
    name_str = f'{ha}x{va}'
    name = name_str.encode() + b'\x0a'
    md2[5:5+len(name)] = name
    edid[72:90] = md2

    # 90-107: Range limits
    md3 = bytearray(18)
    md3[0:5] = b'\x00\x00\x00\xFD\x00'
    h_total = ha + hb
    v_total = va + vb
    actual_mhz = t['clock'] * 10 / 1000
    md3[5] = 40
    md3[6] = 120
    md3[7] = 15
    md3[8] = 160
    md3[9] = min(255, (t['clock'] + 500) // 1000)  # 10MHz units
    md3[10] = 0x01
    edid[90:108] = md3

    # 108-125: Serial
    md4 = bytearray(18)
    md4[0:5] = b'\x00\x00\x00\xFF\x00'
    serial = b'VM-2025-001\x0a'
    md4[5:5+len(serial)] = serial
    edid[108:126] = md4

    # 126: Extension count
    edid[126] = 0

    # 127: Checksum
    edid[127] = (256 - (sum(edid[:127]) % 256)) % 256

    return bytes(edid)


def main():
    ap = argparse.ArgumentParser(description='Generate EDID for virtual monitor')
    ap.add_argument('-w', '--width', type=int, default=1920, help='Width (default: 1920)')
    ap.add_argument('-H', '--height', type=int, default=1080, help='Height (default: 1080)')
    ap.add_argument('-r', '--refresh', type=int, default=60, help='Refresh rate (default: 60)')
    ap.add_argument('output', nargs='?', help='Output file (default: stdout)')
    args = ap.parse_args()

    t = cvt_rb_timings(args.width, args.height, args.refresh)
    edid = make_edid(t)

    if args.output:
        with open(args.output, 'wb') as f:
            f.write(edid)
        print(f'EDID: {args.width}x{args.height}@{args.refresh}Hz -> {args.output}', file=sys.stderr)
    else:
        sys.stdout.buffer.write(edid)


if __name__ == '__main__':
    main()
