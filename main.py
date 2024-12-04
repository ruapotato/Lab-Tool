#!/usr/bin/python3
import os
import sys
import cmd
import glob
import subprocess
import threading
import readline
import signal
from functools import wraps

class LabTool(cmd.Cmd):
    intro = '''Pinephone Lab Tool - USB Gadget and ISO Tool
Type help or ? to list commands.

Examples:
  lab> iso ubuntu.iso               # Select an ISO file
  lab> write /dev/sda              # Write ISO to USB drive
  lab> emulate start               # Share ISO over USB
  lab> keyboard start              # Start USB keyboard
  lab> status                      # Show current status
    '''
    prompt = 'lab> '
    
    def __init__(self):
        super().__init__()
        self.selected_iso = None
        self.usb_gadget_configured = False
        self.keyboard_active = False
        self.keyboard_thread = None
        self.emulating = False
        
        # Enable tab completion for file paths
        readline.set_completer_delims(' \t\n;')
        
        # Clean up any existing gadget config
        self.cleanup_gadget()
    
    def cleanup_gadget(self):
        """Safely clean up existing USB gadget configuration"""
        try:
            gadget_path = "/sys/kernel/config/usb_gadget/g1"
            if os.path.exists(gadget_path):
                # First disable the UDC
                try:
                    with open(f"{gadget_path}/UDC", "w") as f:
                        f.write("")
                except:
                    pass

                # Remove symlinks in reverse order
                for config in glob.glob(f"{gadget_path}/configs/*/"):
                    for f in glob.glob(f"{config}*"):
                        if os.path.islink(f):
                            os.unlink(f)

                # Remove the gadget directory structure
                subprocess.run(["rmdir", "-p", "--ignore-fail-on-non-empty", gadget_path])
                
            os.system("rmmod g_multi 2>/dev/null || true")
            os.system("modprobe libcomposite")
        except Exception as e:
            print(f"Note: Partial gadget config may exist: {e}")

    def require_root(func):
        """Decorator to check for root privileges"""
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            if os.geteuid() != 0:
                print("This command requires root privileges")
                return
            return func(self, *args, **kwargs)
        return wrapper
    
    def do_exit(self, arg):
        """Exit the lab tool"""
        if self.keyboard_active:
            self.do_keyboard('stop')
        if self.emulating:
            self.do_emulate('stop')
        self.cleanup_gadget()
        return True
        
    def do_EOF(self, arg):
        """Exit on Ctrl-D"""
        print()  # Add newline
        return self.do_exit(arg)
        
    def complete_iso(self, text, line, begidx, endidx):
        """Tab completion for ISO files"""
        if not text:
            completions = glob.glob('*.iso')
        else:
            completions = glob.glob(f'{text}*.iso')
        return completions
    
    def complete_device(self, text, line, begidx, endidx):
        """Tab completion for device paths"""
        if not text:
            completions = glob.glob('/dev/sd*')
        else:
            completions = glob.glob(f'/dev/sd{text}*')
        return completions
    
    def do_iso(self, arg):
        """Select an ISO file to work with
Usage: iso <path/to/file.iso>"""
        if not arg:
            if self.selected_iso:
                print(f"Currently selected ISO: {self.selected_iso}")
            else:
                print("No ISO file selected")
            return
            
        if not os.path.exists(arg):
            print(f"File not found: {arg}")
            return
            
        self.selected_iso = os.path.abspath(arg)
        print(f"Selected ISO: {self.selected_iso}")
    
    @require_root
    def do_write(self, arg):
        """Write the selected ISO to a device
Usage: write <device>
Example: write /dev/sda"""
        if not self.selected_iso:
            print("No ISO file selected. Use 'iso' command first.")
            return
            
        if not arg:
            print("No device specified")
            return
            
        if not os.path.exists(arg):
            print(f"Device not found: {arg}")
            return
            
        print(f"Writing {self.selected_iso} to {arg}")
        print("Press Ctrl+C to cancel")
        
        try:
            cmd = ['dd', f'if={self.selected_iso}', f'of={arg}', 'bs=4M', 'status=progress']
            subprocess.run(cmd)
            print("\nWrite completed successfully")
        except subprocess.CalledProcessError as e:
            print(f"\nError writing ISO: {e}")
        except KeyboardInterrupt:
            print("\nWrite cancelled")
    
    def configure_usb_gadget(self):
        """Configure USB gadget with HID and mass storage functions"""
        try:
            self.cleanup_gadget()
            
            gadget_path = "/sys/kernel/config/usb_gadget/g1"
            
            # Create gadget directory
            os.makedirs(gadget_path, exist_ok=True)
            os.chdir(gadget_path)
            
            # Set USB device parameters
            with open("idVendor", "w") as f:
                f.write("0x1f3a")  # Pine64
            with open("idProduct", "w") as f:
                f.write("0x1001")  # Generic USB device
            with open("bcdDevice", "w") as f:
                f.write("0x0100")
            with open("bcdUSB", "w") as f:
                f.write("0x0200")
            
            # Create strings
            os.makedirs("strings/0x409", exist_ok=True)
            with open("strings/0x409/serialnumber", "w") as f:
                f.write("pinephone123456")
            with open("strings/0x409/manufacturer", "w") as f:
                f.write("Pine64")
            with open("strings/0x409/product", "w") as f:
                f.write("Pinephone Lab Tool")
            
            # Setup HID keyboard
            os.makedirs("functions/hid.keyboard", exist_ok=True)
            with open("functions/hid.keyboard/protocol", "w") as f:
                f.write("1")
            with open("functions/hid.keyboard/subclass", "w") as f:
                f.write("1")
            with open("functions/hid.keyboard/report_length", "w") as f:
                f.write("8")
            
            # Write HID report descriptor
            report_desc = [
                0x05, 0x01,  # Usage Page (Generic Desktop)
                0x09, 0x06,  # Usage (Keyboard)
                0xA1, 0x01,  # Collection (Application)
                0x05, 0x07,  # Usage Page (Key Codes)
                0x19, 0xE0,  # Usage Minimum (224)
                0x29, 0xE7,  # Usage Maximum (231)
                0x15, 0x00,  # Logical Minimum (0)
                0x25, 0x01,  # Logical Maximum (1)
                0x75, 0x01,  # Report Size (1)
                0x95, 0x08,  # Report Count (8)
                0x81, 0x02,  # Input (Data, Variable, Absolute)
                0x95, 0x01,  # Report Count (1)
                0x75, 0x08,  # Report Size (8)
                0x81, 0x03,  # Input (Constant)
                0x95, 0x06,  # Report Count (6)
                0x75, 0x08,  # Report Size (8)
                0x15, 0x00,  # Logical Minimum (0)
                0x25, 0x65,  # Logical Maximum (101)
                0x05, 0x07,  # Usage Page (Key Codes)
                0x19, 0x00,  # Usage Minimum (0)
                0x29, 0x65,  # Usage Maximum (101)
                0x81, 0x00,  # Input (Data, Array)
                0xC0        # End Collection
            ]
            with open("functions/hid.keyboard/report_desc", "wb") as f:
                f.write(bytes(report_desc))
            
            # Setup mass storage
            os.makedirs("functions/mass_storage.0", exist_ok=True)
            
            # Create config
            os.makedirs("configs/c.1/strings/0x409", exist_ok=True)
            with open("configs/c.1/strings/0x409/configuration", "w") as f:
                f.write("Config 1: HID + Mass Storage")
            with open("configs/c.1/MaxPower", "w") as f:
                f.write("500")
            
            # Create symlinks
            os.symlink(f"{gadget_path}/functions/hid.keyboard", 
                      f"{gadget_path}/configs/c.1/hid.keyboard")
            os.symlink(f"{gadget_path}/functions/mass_storage.0",
                      f"{gadget_path}/configs/c.1/mass_storage.0")
            
            # Enable gadget
            udc = os.listdir("/sys/class/udc")[0]
            with open("UDC", "w") as f:
                f.write(udc)
            
            # Set permissions
            os.system("chmod 666 /dev/hidg0")
            
            self.usb_gadget_configured = True
            return True
            
        except Exception as e:
            print(f"Error configuring USB gadget: {e}")
            return False
    
    @require_root
    def do_emulate(self, arg):
        """Emulate selected ISO over USB
Usage: emulate [start|stop]"""
        if arg == 'stop':
            if self.emulating:
                try:
                    with open("/sys/kernel/config/usb_gadget/g1/functions/mass_storage.0/lun.0/file", "w") as f:
                        f.write("")
                    self.emulating = False
                    print("ISO emulation stopped")
                except Exception as e:
                    print(f"Error stopping emulation: {e}")
            return
            
        if not self.selected_iso:
            print("No ISO file selected. Use 'iso' command first.")
            return
            
        if not self.usb_gadget_configured:
            print("Configuring USB gadget...")
            if not self.configure_usb_gadget():
                return
        
        try:
            with open("/sys/kernel/config/usb_gadget/g1/functions/mass_storage.0/lun.0/file", "w") as f:
                f.write(self.selected_iso)
            self.emulating = True
            print(f"Emulating {os.path.basename(self.selected_iso)} over USB")
        except Exception as e:
            print(f"Error setting up ISO emulation: {e}")
    
    def keyboard_thread_func(self):
        """Thread for handling keyboard input"""
        os.system("stty -echo -icanon")
        try:
            while self.keyboard_active:
                char = sys.stdin.read(1)
                if char:
                    self.send_key(char)
        except Exception as e:
            print(f"Keyboard error: {e}")
        finally:
            os.system("stty echo icanon")
    
    def send_key(self, key_chr):
        """Send a single key press event"""
        NULL_CHAR = chr(0)
        
        try:
            if key_chr.isalpha():
                if key_chr.isupper():
                    # Shift + key for uppercase
                    self.write_hid_report(chr(32) + NULL_CHAR + chr(ord(key_chr.lower()) - 93) + NULL_CHAR * 5)
                else:
                    # Regular key for lowercase
                    self.write_hid_report(NULL_CHAR * 2 + chr(ord(key_chr) - 93) + NULL_CHAR * 5)
            elif key_chr in "1234567890":
                # Number keys
                self.write_hid_report(NULL_CHAR * 2 + chr(ord(key_chr) - 19) + NULL_CHAR * 5)
            elif key_chr == "\n":
                # Enter key
                self.write_hid_report(NULL_CHAR * 2 + chr(40) + NULL_CHAR * 5)
            elif key_chr == " ":
                # Space key
                self.write_hid_report(NULL_CHAR * 2 + chr(44) + NULL_CHAR * 5)
            
            # Release all keys
            self.write_hid_report(NULL_CHAR * 8)
            
        except Exception as e:
            print(f"Error sending key: {e}")
    
    def write_hid_report(self, report):
        """Write HID report to keyboard device"""
        try:
            with open('/dev/hidg0', 'rb+') as fd:
                fd.write(report.encode())
        except Exception as e:
            print(f"Error writing HID report: {e}")
    
    @require_root
    def do_keyboard(self, arg):
        """Start or stop virtual USB keyboard
Usage: keyboard [start|stop]"""
        if arg == "stop":
            if self.keyboard_active:
                self.keyboard_active = False
                if self.keyboard_thread:
                    self.keyboard_thread.join()
                print("Virtual keyboard stopped")
            return
            
        if not self.usb_gadget_configured:
            print("Configuring USB gadget...")
            if not self.configure_usb_gadget():
                return
        
        if not self.keyboard_active:
            self.keyboard_active = True
            print("Virtual keyboard started. Type to send keys, Ctrl+C to stop.")
            self.keyboard_thread = threading.Thread(target=self.keyboard_thread_func)
            self.keyboard_thread.daemon = True
            self.keyboard_thread.start()
    
    def do_status(self, arg):
        """Show current status of the lab tool"""
        print("Lab Tool Status:")
        print(f"Selected ISO: {self.selected_iso or 'None'}")
        print(f"USB Gadget Configured: {'Yes' if self.usb_gadget_configured else 'No'}")
        print(f"Keyboard Active: {'Yes' if self.keyboard_active else 'No'}")
        print(f"ISO Emulation: {'Active' if self.emulating else 'Inactive'}")

def main():
    """Main entry point"""
    if os.geteuid() != 0:
        print("This tool must be run as root", file=sys.stderr)
        sys.exit(1)
    
    # Handle Ctrl+C gracefully
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    
    # Start the command interpreter
    LabTool().cmdloop()

if __name__ == "__main__":
    main()
