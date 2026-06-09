# Linux Virtual Display

Create a virtual display on headless Linux so SDDM + KRDP (KDE Remote Desktop) work without a physical monitor.

Based on [vyacheslavl's post](https://discuss.kde.org/t/how-to-create-a-virtual-monitor-display/2725/3).

Tested on Debian Testing + KDE Plasma 6.6.5 (Ryzen 5300U).

## Usage

```bash
# install (auto-detect DP first, then HDMI; default 1920x1080@60)
sudo bash setup-virtual-monitor.sh install

# custom resolution/refresh
sudo bash setup-virtual-monitor.sh install -r 2560x1440 -R 75

# specify connector
sudo bash setup-virtual-monitor.sh install -c DP-1 -r 3840x2160 -R 30

# uninstall
sudo bash setup-virtual-monitor.sh uninstall
```

## Files

| File | Description |
|------|-------------|
| `setup-virtual-monitor.sh` | Install/uninstall script |
| `generate-edid.py` | EDID generator (CVT-RB) |
| `prompt.txt` | Original manual guide reference |

## How it works

1. `generate-edid.py` creates a 256-byte EDID (base block + CEA-861 extension) with CVT-RB timings, standard/established timings, VICs, and audio support
2. `setup-virtual-monitor.sh` installs it to `/usr/lib/firmware/edid/` and adds `drm.edid_firmware` + `video=` parameters to GRUB
3. Connector auto-detection prioritizes DP (ideal: pick an unused port), falls back to HDMI
4. The trailing `e` in `video=<connector>:<WxH>@<Hz>e` forces the port to appear connected
5. Reboot to activate
