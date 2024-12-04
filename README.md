# Lab-Tool
USB tools for the Pinephone
Based on: https://bitbucket.org/hackersgame/iso_tools

# Use
`sudo ./main.py`
```
lab> iso <tab>
[shows available .iso files]
lab> iso ubuntu.iso
Selected ISO: /home/david/ubuntu.iso

lab> write /dev/sd<tab>
[shows available devices]
lab> write /dev/sda
Writing ubuntu.iso to /dev/sda...

lab> emulate start
Emulating ubuntu.iso over USB

lab> keyboard start
Virtual keyboard started. Type to send keys, Ctrl+C to stop.

lab> status
Lab Tool Status:
Selected ISO: /home/david/ubuntu.iso
USB Gadget Configured: Yes
Keyboard Active: Yes
ISO Emulation: Active
```
