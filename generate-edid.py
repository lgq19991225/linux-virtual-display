#!/usr/bin/env python3
"""Generate EDID binary for a given resolution and refresh rate.

Uses CVT-RB timings, includes standard/established timings and a
CEA-861 extension block (VICs, audio, HDMI vendor block).

Usage:
  python3 generate-edid.py [-w W] [-H H] [-r R] [-n NAME] [output]
  python3 generate-edid.py -w 1920 -H 1080 -r 60 edid.bin

Defaults: 1920x1080@60
"""

import argparse
import struct
import sys
import math


def cvt_rb_timings(width, height, refresh):
    h_front = 48
    h_sync  = 32
    h_back  = 80
    h_blank = h_front + h_sync + h_back
    h_total = width + h_blank

    v_front = 3
    v_sync  = 6
    v_back  = max(1, int((height - 200) / 400 * 6))
    v_blank = v_front + v_sync + v_back
    v_total = height + v_blank
    if v_total % 2:
        v_total += 1
        v_back  += 1
    v_blank = v_front + v_sync + v_back

    pixel_clock_10khz = int(math.ceil(h_total * v_total * refresh / 10000))

    him_mm = int(width  * 0.28)
    vim_mm = int(height * 0.28)

    return {
        'clock': pixel_clock_10khz,
        'ha':    width,   'hb':   h_blank,
        'va':    height,  'vb':   v_blank,
        'hso':   h_front, 'hsp':  h_sync,
        'vso':   v_front, 'vsp':  v_sync,
        'him':   him_mm,  'vim':  vim_mm,
    }


def dt_encode(t):
    dt = bytearray(18)
    struct.pack_into('<H', dt, 0, t['clock'])
    ha, hb = t['ha'], t['hb']
    va, vb = t['va'], t['vb']
    dt[2]  = ha & 0xFF
    dt[3]  = hb & 0xFF
    dt[4]  = ((ha >> 8) & 0x0F) << 4 | ((hb >> 8) & 0x0F)
    dt[5]  = va & 0xFF
    dt[6]  = vb & 0xFF
    dt[7]  = ((va >> 8) & 0x0F) << 4 | ((vb >> 8) & 0x0F)
    dt[8]  = t['hso'] & 0xFF
    dt[9]  = t['hsp'] & 0xFF
    dt[10] = ((t['vso'] & 0x0F) << 4) | (t['vsp'] & 0x0F)
    dt[11] = 0x00
    dt[12] = t['him'] & 0xFF
    dt[13] = t['vim'] & 0xFF
    dt[14] = ((t['him'] >> 8) & 0x0F) << 4 | ((t['vim'] >> 8) & 0x0F)
    dt[15] = 0
    dt[16] = 0
    dt[17] = 0x00
    return dt


def set_checksum(block):
    block[127] = (256 - (sum(block[:127]) % 256)) % 256


def make_std_timing(h_active, aspect, refresh):
    b1 = h_active // 8 - 31
    b2 = (aspect << 6) | (refresh - 60)
    return bytes([b1 & 0xFF, b2 & 0xFF])


def make_display_descriptor(tag, data):
    buf = bytearray(18)
    buf[3] = tag
    buf[4] = 0x00
    buf[5:5+len(data)] = data[:13]
    return buf


def make_base_edid(t, moniker=None):
    b = bytearray(128)

    b[0:8] = b'\x00\xFF\xFF\xFF\xFF\xFF\xFF\x00'

    mfr = (22 << 10) | (20 << 5) | 13
    struct.pack_into('>H', b, 8, mfr)

    struct.pack_into('<H', b, 10, 0x0001)
    b[12:16] = b'\x00\x00\x00\x00'
    b[16] = 1
    b[17] = 35
    b[18] = 1
    b[19] = 4

    b[20] = 0x80

    b[21] = max(1, min(255, t['him'] // 10))
    b[22] = max(1, min(255, t['vim'] // 10))

    b[23] = 0x78
    b[24] = 0x0E

    rx, ry = 655, 338
    gx, gy = 307, 614
    bx, by = 154,  61
    wx, wy = 320, 337

    b[25] = (rx >> 2) & 0xFF
    b[26] = ((ry >> 2) & 0xFC) | ((gx >> 8) & 0x03)
    b[27] = ((gx >> 2) & 0xFC) | ((gy >> 8) & 0x03)
    b[28] = ((gy >> 2) & 0xFC) | ((bx >> 8) & 0x03)
    b[29] = ((bx >> 2) & 0xFC) | ((by >> 8) & 0x03)
    b[30] = ((by >> 2) & 0xFC) | ((wx >> 8) & 0x03)
    b[31] = ((wx >> 2) & 0xFC) | ((wy >> 8) & 0x03)
    b[32] = ((wy >> 2) & 0xFC)
    b[33] = 0x00
    b[34] = 0x00

    b[35] = 0x0A
    b[36] = 0x30
    b[37] = 0x00

    std_modes = [
        (1680, 0, 60), (1440, 0, 60), (1280, 2, 60), (1400, 1, 60),
        (1600, 3, 60), (1280, 0, 60), (1368, 3, 60), (1280, 3, 60),
    ]
    for i, (w, asp, r) in enumerate(std_modes):
        b[38+i*2:40+i*2] = make_std_timing(w, asp, r)

    b[54:72] = dt_encode(t)

    name = moniker if moniker else '{}x{}'.format(t['ha'], t['va'])
    b[72:90] = make_display_descriptor(0xFC, name.encode() + b'\x0a')

    rr = bytearray(13)
    rr[0] = 40
    rr[1] = 120
    rr[2] = 15
    rr[3] = 160
    rr[4] = (t['clock'] + 500) // 1000
    rr[5] = 0x01
    b[90:108] = make_display_descriptor(0xFD, rr)

    b[108:126] = make_display_descriptor(0xFF, b'VM-2025-001\x0a')

    b[126] = 1

    set_checksum(b)
    return bytes(b)


def make_cea_extension():
    ext = bytearray(128)

    ext[0] = 0x02
    ext[1] = 0x03

    db = bytearray()

    vics = [16, 31, 32, 4, 19, 3]
    db.append((2 << 5) | len(vics))
    db.extend(vics)

    db.append((1 << 5) | 3)
    db.extend([0x09, 0x0E, 0x07])

    db.append((4 << 5) | 3)
    db.extend([0x01, 0x00, 0x00])

    db.append((3 << 5) | 6)
    db.extend([0x03, 0x0C, 0x00, 0x10, 0x00, 0x80])

    ext[2] = 4 + len(db)
    ext[3] = 0x07
    ext[4:4+len(db)] = db

    set_checksum(ext)
    return bytes(ext)


def main():
    ap = argparse.ArgumentParser(description='Generate EDID for virtual monitor')
    ap.add_argument('-w', '--width', type=int, default=1920,
                    help='Width (default: 1920)')
    ap.add_argument('-H', '--height', type=int, default=1080,
                    help='Height (default: 1080)')
    ap.add_argument('-r', '--refresh', type=int, default=60,
                    help='Refresh rate in Hz (default: 60)')
    ap.add_argument('-n', '--name', default=None,
                    help='Monitor name (default: WxH)')
    ap.add_argument('output', nargs='?',
                    help='Output file (default: stdout)')
    args = ap.parse_args()

    if args.width < 640 or args.height < 480:
        ap.error('Resolution too small (minimum 640x480)')

    t = cvt_rb_timings(args.width, args.height, args.refresh)
    t['target_refresh'] = args.refresh

    base = make_base_edid(t, moniker=args.name)
    edid = base + make_cea_extension()

    if args.output:
        with open(args.output, 'wb') as f:
            f.write(edid)
        print('EDID: {}x{}@{:d}Hz  ({} bytes) -> {}'.format(
            args.width, args.height, args.refresh, len(edid), args.output),
            file=sys.stderr)
    else:
        sys.stdout.buffer.write(edid)


if __name__ == '__main__':
    main()
