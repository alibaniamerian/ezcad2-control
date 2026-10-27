"""Explicit operator controls for the installed EZCAD2 Windows UI.

No SDK, hardware initialization, automatic marking, or global keyboard shortcuts.
"""
import argparse
import os
import ctypes
from ctypes import wintypes as W
from pathlib import Path
import sys
import time
import struct
import tkinter as tk
from tkinter import filedialog, messagebox

DEFAULT_EXE = os.environ.get("EZCAD2_EXE", str(Path("EzCad2.exe").resolve()))
LABELS = {"red": "Red(F1)", "mark": "Mark(F2)", "stop": "Stop"}


def validate_ezd(filename):
    path = Path(filename).resolve(strict=True)
    if not path.is_file() or path.suffix.lower() != ".ezd":
        raise ValueError("Select an existing .ezd file")
    return path


def is_open_menu(text):
    return text.split("\t")[0].replace("&", "").strip().rstrip(".\u2026").casefold() == "open"


def open_accelerator_commands(data):
    if len(data) % 8:
        raise ValueError("Invalid accelerator resource")
    # FVIRTKEY | FCONTROL; FNOINVERT and the final-entry flag are irrelevant.
    return {command for flags, key, command, _ in struct.iter_unpack("<HHHH", data)
            if key == ord("O") and flags & 0x1D == 0x09}


def read_open_command(executable):
    """Read Ctrl+O from PE resources as bytes; never execute/load the DLL or EXE."""
    data = Path(executable).read_bytes()
    try:
        pe = struct.unpack_from("<I", data, 60)[0]
        if data[pe:pe + 4] != b"PE\0\0":
            raise ValueError("Invalid PE signature")
        count = struct.unpack_from("<H", data, pe + 6)[0]
        size = struct.unpack_from("<H", data, pe + 20)[0]
        opt = pe + 24
        magic = struct.unpack_from("<H", data, opt)[0]
        if magic not in (0x10B, 0x20B):
            raise ValueError("Unsupported PE format")
        resource_rva = struct.unpack_from("<I", data, opt + (96 if magic == 0x10B else 112) + 16)[0]
        sections = [struct.unpack_from("<IIII", data, opt + size + i * 40 + 8)
                    for i in range(count)]
        def offset(rva):
            for virtual_size, va, raw_size, raw_pointer in sections:
                if va <= rva < va + max(virtual_size, raw_size):
                    return raw_pointer + rva - va
            raise ValueError("Resource outside PE sections")
        base = offset(resource_rva)
        commands = set()
        def visit(relative, keys=()):
            if len(keys) > 3:
                raise ValueError("Invalid resource tree")
            start = base + relative
            entries = sum(struct.unpack_from("<HH", data, start + 12))
            for i in range(entries):
                key, value = struct.unpack_from("<II", data, start + 16 + i * 8)
                if not keys and key != 9:  # RT_ACCELERATOR
                    continue
                if value & 0x80000000:
                    visit(value & 0x7FFFFFFF, keys + (key,))
                else:
                    rva, length = struct.unpack_from("<II", data, base + value)
                    pos = offset(rva)
                    commands.update(open_accelerator_commands(data[pos:pos + length]))
        visit(0)
        if len(commands) != 1:
            raise ValueError("No unique Ctrl+O command in executable resources")
        return commands.pop()
    except (struct.error, IndexError, RecursionError) as exc:
        raise ValueError("Could not read EZCAD2 accelerator resources") from exc


def choose_button(controls, action):
    candidates = [c for c in controls if c["class"].lower() == "button"
                  and c["text"].replace("&", "").strip() == LABELS[action]
                  and c["enabled"] and c["visible"]]
    if len(candidates) != 1:
        raise RuntimeError(f"Expected one available {LABELS[action]} button; found {len(candidates)}")
    return candidates[0]


class WindowsUI:
    def __init__(self, executable):
        if sys.platform != "win32":
            raise RuntimeError("Windows is required")
        self.exe = str(Path(executable).resolve()).casefold()
        self.u = ctypes.WinDLL("user32", use_last_error=True)
        self.k = ctypes.WinDLL("kernel32", use_last_error=True)
        self.callback_type = ctypes.WINFUNCTYPE(W.BOOL, W.HWND, W.LPARAM)
        signatures = {
            "EnumWindows": ([self.callback_type, W.LPARAM], W.BOOL),
            "EnumChildWindows": ([W.HWND, self.callback_type, W.LPARAM], W.BOOL),
            "GetWindowTextW": ([W.HWND, W.LPWSTR, ctypes.c_int], ctypes.c_int),
            "GetClassNameW": ([W.HWND, W.LPWSTR, ctypes.c_int], ctypes.c_int),
            "GetWindowThreadProcessId": ([W.HWND, ctypes.POINTER(W.DWORD)], W.DWORD),
            "IsWindowVisible": ([W.HWND], W.BOOL),
            "IsWindowEnabled": ([W.HWND], W.BOOL),
            "PostMessageW": ([W.HWND, W.UINT, W.WPARAM, W.LPARAM], W.BOOL),
            "GetMenu": ([W.HWND], W.HMENU),
            "GetSubMenu": ([W.HMENU, ctypes.c_int], W.HMENU),
            "GetMenuItemCount": ([W.HMENU], ctypes.c_int),
            "GetMenuItemID": ([W.HMENU, ctypes.c_int], W.UINT),
            "GetMenuState": ([W.HMENU, W.UINT, W.UINT], W.UINT),
            "GetMenuStringW": ([W.HMENU, W.UINT, W.LPWSTR, ctypes.c_int, W.UINT], ctypes.c_int),
            "GetDlgCtrlID": ([W.HWND], ctypes.c_int),
            "SendMessageTimeoutW": ([W.HWND, W.UINT, W.WPARAM, W.LPARAM, W.UINT, W.UINT,
                                     ctypes.POINTER(ctypes.c_size_t)], W.LPARAM),
        }
        for name, (args, result) in signatures.items():
            fn = getattr(self.u, name)
            fn.argtypes, fn.restype = args, result
        self.k.OpenProcess.argtypes = [W.DWORD, W.BOOL, W.DWORD]
        self.k.OpenProcess.restype = W.HANDLE
        self.k.QueryFullProcessImageNameW.argtypes = [W.HANDLE, W.DWORD, W.LPWSTR, ctypes.POINTER(W.DWORD)]
        self.k.QueryFullProcessImageNameW.restype = W.BOOL
        self.k.CloseHandle.argtypes = [W.HANDLE]
        self.k.CloseHandle.restype = W.BOOL

    def text(self, hwnd, class_name=False):
        buffer = ctypes.create_unicode_buffer(2048)
        fn = self.u.GetClassNameW if class_name else self.u.GetWindowTextW
        fn(hwnd, buffer, len(buffer))
        return buffer.value

    def process(self, hwnd):
        pid = W.DWORD()
        self.u.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        handle = self.k.OpenProcess(0x1000, False, pid.value)
        if not handle:
            return pid.value, ""
        try:
            buffer = ctypes.create_unicode_buffer(32768)
            size = W.DWORD(len(buffer))
            if not self.k.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
                return pid.value, ""
            return pid.value, str(Path(buffer.value).resolve()).casefold()
        finally:
            self.k.CloseHandle(handle)

    def enumerate(self, parent=None):
        items = []
        @self.callback_type
        def collect(hwnd, _):
            items.append(hwnd)
            return True
        if parent is None:
            self.u.EnumWindows(collect, 0)
        else:
            self.u.EnumChildWindows(parent, collect, 0)
        return items

    def snapshot(self):
        roots = []
        for hwnd in self.enumerate():
            if self.u.IsWindowVisible(hwnd):
                pid, path = self.process(hwnd)
                if path == self.exe:
                    roots.append((hwnd, pid))
        pids = {pid for _, pid in roots}
        if len(pids) != 1:
            raise RuntimeError("Open exactly one EZCAD2 instance at the configured path")
        controls = []
        for root, pid in roots:
            for hwnd in self.enumerate(root):
                controls.append(dict(hwnd=hwnd, root=root, pid=pid,
                                     text=self.text(hwnd), **{"class": self.text(hwnd, True)},
                                     enabled=bool(self.u.IsWindowEnabled(hwnd)),
                                     visible=bool(self.u.IsWindowVisible(hwnd))))
        return roots, controls

    def command(self, action, expected=None):
        roots, controls = self.snapshot()
        button = choose_button(controls, action)
        if not self.u.IsWindowEnabled(button["root"]):
            raise RuntimeError("Resolve the open EZCAD2 dialog first")
        title = self.text(button["root"])
        identity = (button["pid"], button["root"], button["hwnd"], title)
        if expected is not None and identity != expected:
            raise RuntimeError("EZCAD2 target changed; command cancelled")
        if action != "stop" and any(c["visible"] and c["text"].strip() == "Stop" for c in controls):
            raise RuntimeError("An operation is already active; use Stop first")
        return button, identity

    def click(self, action, expected):
        button, _ = self.command(action, expected)
        # BM_CLICK targets only this observed button, never the global F1/F2 keys.
        if not self.u.PostMessageW(button["hwnd"], 0x00F5, 0, 0):
            raise ctypes.WinError(ctypes.get_last_error())

    def load_file(self, filename):
        path = validate_ezd(filename)
        # The main window must be idle, with an available Red button.
        button, identity = self.command("red")
        target = button["root"]
        if not self.u.IsWindowEnabled(target):
            raise RuntimeError("Close the EZCAD2 dialog before loading a file")
        commands = []
        def scan(menu):
            for index in range(self.u.GetMenuItemCount(menu)):
                child = self.u.GetSubMenu(menu, index)
                if child:
                    scan(child)
                else:
                    buf = ctypes.create_unicode_buffer(256)
                    self.u.GetMenuStringW(menu, index, buf, len(buf), 0x400)
                    if is_open_menu(buf.value) and not self.u.GetMenuState(menu, index, 0x400) & 3:
                        commands.append(self.u.GetMenuItemID(menu, index))
        scan(self.u.GetMenu(target))
        if not commands:
            # EZCAD's owner-drawn menu can expose no readable labels.
            # Resolve its real Ctrl+O command from the installed binary instead.
            commands = [read_open_command(self.exe)]
        if len(commands) != 1:
            raise RuntimeError("Multiple File > Open commands found; no command sent")
        self.command("red", identity)
        if not self.u.PostMessageW(target, 0x111, commands[0], 0):
            raise ctypes.WinError(ctypes.get_last_error())
        return path, identity[0]

    def fill_open_dialog(self, path, pid):
        roots, _ = self.snapshot()
        matches = []
        for dialog, process_id in roots:
            if process_id != pid or self.text(dialog, True) != "#32770":
                continue
            # Never act on Save As or on a save-changes confirmation.
            if self.text(dialog).replace("&", "").strip().casefold() != "open":
                continue
            children = self.enumerate(dialog)
            edits = set()
            for child in children:
                cid = self.u.GetDlgCtrlID(child)
                cls = self.text(child, True).lower()
                if cid == 0x480 and cls == "edit":  # standard edt1
                    edits.add(child)
                if cid == 0x47c and cls in ("combobox", "comboboxex32"):  # cmb13
                    edits.update(h for h in self.enumerate(child) if self.text(h, True).lower() == "edit")
            edits = [h for h in edits if self.u.IsWindowVisible(h) and self.u.IsWindowEnabled(h)]
            opens = [h for h in children if self.u.GetDlgCtrlID(h) == 1
                     and self.text(h, True).lower() == "button"
                     and is_open_menu(self.text(h)) and self.u.IsWindowEnabled(h)]
            if len(edits) == len(opens) == 1:
                matches.append((edits[0], opens[0]))
        if not matches:
            return False
        if len(matches) != 1:
            raise RuntimeError("Multiple Open dialogs found; no file submitted")
        edit, button = matches[0]
        buffer = ctypes.create_unicode_buffer(str(validate_ezd(path)))
        result = ctypes.c_size_t()
        if not self.u.SendMessageTimeoutW(edit, 0x000C, 0, ctypes.addressof(buffer),
                                         2, 2000, ctypes.byref(result)) or not result.value:
            raise RuntimeError("Could not fill EZCAD2 filename field")
        if not self.u.PostMessageW(button, 0x00F5, 0, 0):
            raise ctypes.WinError(ctypes.get_last_error())
        return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exe", default=DEFAULT_EXE)
    args = parser.parse_args()
    ui = WindowsUI(args.exe)
    root = tk.Tk()
    root.title("EZCAD2 Control")
    root.geometry("560x440")
    status = tk.StringVar(value="Ready. No command sent.")
    tk.Label(root, text="EZCAD2 operator controls", font=("Segoe UI", 16)).pack(pady=12)
    tk.Label(root, text="Uses the current open design and its existing settings.").pack()
    buttons = []
    selected_file = tk.StringVar(value="No file selected")

    def load_file():
        filename = filedialog.askopenfilename(
            parent=root, title="Load EZCAD2 design", filetypes=[("EZCAD2 design", "*.ezd")])
        if not filename:
            return
        try:
            path, pid = ui.load_file(filename)
            selected_file.set(str(path))
            for button in buttons:
                button.config(state="disabled")
            status.set("Waiting for EZCAD2 Open dialog. Answer any save-changes prompt in EZCAD2.")
            deadline = time.monotonic() + 120
            def complete():
                try:
                    if ui.fill_open_dialog(path, pid):
                        status.set("File submitted to EZCAD2. Verify the loaded design there. No Mark sent.")
                    elif time.monotonic() < deadline:
                        root.after(400, complete)
                        return
                    else:
                        status.set("Open dialog not found / cancelled. No file submitted. Try Load again.")
                except (RuntimeError, OSError, ValueError) as exc:
                    status.set(str(exc))
                for button in buttons:
                    button.config(state="normal")
            root.after(400, complete)
        except (RuntimeError, OSError, ValueError) as exc:
            status.set(str(exc))
            messagebox.showerror("File not sent", str(exc))

    load_button = tk.Button(root, text="Load .ezd file...", command=load_file,
                            font=("Segoe UI", 12), width=30)
    load_button.pack(pady=8)
    buttons.append(load_button)
    tk.Label(root, textvariable=selected_file, wraplength=530).pack()

    def execute(action):
        for button in buttons:
            button.config(state="disabled")
        try:
            _, identity = ui.command(action)
            if action == "mark" and not messagebox.askyesno(
                    "Start physical laser marking?",
                    f"Current window: {identity[3]}\n\n"
                    "This starts actual laser marking with the current design and settings.\n"
                    "Confirm the workpiece and machine are ready. Start now?", default="no"):
                status.set("Mark cancelled. No command sent.")
                return
            ui.click(action, identity)
            status.set(f"{LABELS[action]} request posted. Verify EZCAD2 / machine.\n"
                       "This is not confirmation of physical completion.")
        except (RuntimeError, OSError) as exc:
            status.set(str(exc))
            messagebox.showerror("Command not sent", str(exc))
        finally:
            root.after(1000, lambda: [b.config(state="normal") for b in buttons])

    for action, label, color in (("red", "Red — preview", "#b71c1c"),
                                 ("stop", "Stop", "#333333"),
                                 ("mark", "Mark — physical laser", "#8b4500")):
        button = tk.Button(root, text=label, command=lambda a=action: execute(a),
                           fg=color, font=("Segoe UI", 12), width=30)
        button.pack(pady=5)
        buttons.append(button)
    tk.Label(root, textvariable=status, wraplength=490).pack(pady=8)
    tk.Label(root, text="Software Stop is not an emergency stop.", fg="#666666").pack()
    root.mainloop()


if __name__ == "__main__":
    main()
