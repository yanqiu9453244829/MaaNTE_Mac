#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
maante_gui.py - MaaNTE macOS GUI Frontend
Tkinter-based task controller that mirrors MaaXUI functionality on macOS.

Usage:
    python3 maante_gui.py       # macOS
    (or via ./run_macos.sh)

Hotkeys:
    F10 - Start tasks
    F11 - Stop tasks
"""

from __future__ import annotations

import sys
import os
import json
import threading
import queue
import subprocess
import traceback
import time
import uuid
from pathlib import Path
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox

# ---------------------------------------------------------------------------
# Project path setup  (maante_gui.py lives at project root)
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent
AGENT_DIR    = PROJECT_ROOT / "agent"
CONFIG_DIR   = PROJECT_ROOT / "config"
INTERFACE_FILE    = PROJECT_ROOT / "interface.json"
MACOS_CONFIG_FILE = CONFIG_DIR   / "mxu-MaaNTE-macos.json"
MACOS_CONFIG_TMPL = CONFIG_DIR   / "mxu-MaaNTE-macos-template.json"
RESOURCE_PATH     = str(PROJECT_ROOT / "resource" / "base")
DEBUG_DIR         = str(PROJECT_ROOT / "debug")

for _p in (str(AGENT_DIR), str(PROJECT_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
APP_TITLE    = "MaaNTE macOS v1.3.1 | 異環小助手"
HOTKEY_START = "<F10>"
HOTKEY_STOP  = "<F11>"

STATUS_IDLE     = "待機"
STATUS_RUNNING  = "運行中"
STATUS_ERROR    = "錯誤"

LOG_FONT = ("Menlo", 10) if sys.platform == "darwin" else ("Consolas", 10)
LOG_BG   = "#1e1e1e"
LOG_FG   = "#d4d4d4"
LOG_TAGS = {
    "ERROR": "#f48771",
    "WARN":  "#cca700",
    "INFO":  "#9cdcfe",
    "TASK":  "#4ec9b0",
    "FATAL": "#f44747",
    "Agent": "#ce9178",
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_json(path: Path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_interface() -> dict:
    data = _load_json(INTERFACE_FILE)
    tasks = list(data.get("task", []))
    for rel in data.get("import", []):
        try:
            imp = _load_json(PROJECT_ROOT / rel)
            if isinstance(imp, list):
                # File is a bare list of task objects
                tasks.extend(imp)
            elif isinstance(imp, dict):
                # File is {"task": [...], "option": {...}} format (standard PI format)
                sub = imp.get("task", [])
                if isinstance(sub, list):
                    tasks.extend(sub)
                elif sub:
                    tasks.append(sub)
        except Exception:
            pass
    data["_all_tasks"] = tasks
    return data


def load_locales(lang: str = "zh_tw") -> dict:
    _map = {
        "zh_tw": "resource/locales/interface/zh_tw.json",
        "zh_cn": "resource/locales/interface/zh_cn.json",
        "en_us": "resource/locales/interface/en_us.json",
    }
    try:
        return _load_json(PROJECT_ROOT / _map.get(lang, _map["zh_tw"]))
    except Exception:
        return {}


def tr(key: str, loc: dict) -> str:
    if isinstance(key, str) and key.startswith("$"):
        return loc.get(key[1:], key)
    return str(key) if key else ""


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

_DEFAULT_CFG = {
    "version": "1.0",
    "instances": [{
        "id": "macos-default",
        "name": "macOS 實例",
        "controllerName": "MacOS",
        "resourceName": "官服",
        "tasks": [],
    }],
    "settings": {"language": "zh-TW", "autoRunOnLaunch": False},
}


def load_config() -> dict:
    CONFIG_DIR.mkdir(exist_ok=True)
    for src in (MACOS_CONFIG_FILE, MACOS_CONFIG_TMPL):
        if src.exists():
            try:
                return _load_json(src)
            except Exception:
                pass
    _save_config(_DEFAULT_CFG)
    return dict(_DEFAULT_CFG)


def _save_config(cfg: dict) -> None:
    CONFIG_DIR.mkdir(exist_ok=True)
    with open(MACOS_CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Thread-safe log queue
# ---------------------------------------------------------------------------

class LogQueue:
    def __init__(self):
        self._q: queue.Queue[str] = queue.Queue(maxsize=4000)

    def put(self, msg: str) -> None:
        try:
            self._q.put_nowait(msg)
        except queue.Full:
            pass

    def drain(self) -> list:
        out = []
        try:
            while True:
                out.append(self._q.get_nowait())
        except queue.Empty:
            pass
        return out


# ---------------------------------------------------------------------------
# Task Runner
# ---------------------------------------------------------------------------

class TaskRunner:
    """
    Manages the MaaFramework pipeline on a background thread.
    All maafw calls happen here; GUI never touches maafw directly.
    """

    def __init__(self, lq: LogQueue):
        self._lq         = lq
        self._thread     = None
        self._stop_evt   = threading.Event()
        self._tasker_ref = None   # set during _run for stop() to use
        self._status_cb  = None

    def set_status_callback(self, cb):
        self._status_cb = cb

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self, window_id: int, task_names: list) -> None:
        if self.is_running():
            self._log("[WARN] 已有任務在運行，請先停止")
            return
        self._stop_evt.clear()
        self._tasker_ref = None
        self._thread = threading.Thread(
            target=self._run, args=(window_id, task_names),
            daemon=True, name="MaaNTE-Runner",
        )
        self._thread.start()

    def stop(self) -> None:
        self._log("[INFO] 收到停止信號...")
        self._stop_evt.set()
        t = self._tasker_ref
        if t is not None:
            try:
                t.post_stop()
            except Exception:
                pass

    def _log(self, msg: str) -> None:
        self._lq.put(msg)

    def _set_status(self, s: str) -> None:
        if self._status_cb:
            self._status_cb(s)

    def _run(self, window_id: int, task_names: list) -> None:
        controller   = None
        tasker       = None
        resource     = None
        agent_client = None
        agent_proc   = None

        try:
            self._set_status(STATUS_RUNNING)

            # Step 1: Import maafw (validate environment)
            self._log("[INFO] 載入 MaaFramework 模組...")
            try:
                from maa.resource import Resource
                from maa.tasker import Tasker
                from maa.agent_client import AgentClient  # maa/agent_client.py (top-level)
            except ImportError as e:
                self._log(f"[ERROR] 無法導入 maafw: {e}")
                self._log("[ERROR] 請執行: pip install -r requirements-macos.txt")
                self._set_status(STATUS_ERROR)
                return

            # Step 2: AgentClient — create FIRST to get the identifier (socket_id)
            # The identifier is then passed to the agent subprocess so it knows where to connect.
            self._log("[INFO] 建立 AgentClient (取得 socket identifier)...")
            try:
                agent_client = AgentClient()
                socket_id = agent_client.identifier
                if not socket_id:
                    self._log("[ERROR] AgentClient 無法取得 identifier")
                    self._set_status(STATUS_ERROR)
                    return
                self._log(f"[INFO] AgentClient identifier: {socket_id[:16]}... ✓")
            except Exception as e:
                self._log(f"[ERROR] AgentClient 建立失敗: {e}")
                self._log(traceback.format_exc())
                self._set_status(STATUS_ERROR)
                return

            # Step 3: Controller
            self._log(f"[INFO] 連接遊戲窗口 id={window_id}...")
            try:
                from platform.macos.controller import MacOSAdaptedController
                controller = MacOSAdaptedController(window_id)
                if not controller.connect():
                    self._log("[ERROR] Controller 連接失敗，請確認遊戲已打開")
                    self._set_status(STATUS_ERROR)
                    return
                self._log("[INFO] Controller 連接成功 ✓")
            except Exception as e:
                self._log(f"[ERROR] Controller 失敗: {e}")
                self._log(traceback.format_exc())
                self._set_status(STATUS_ERROR)
                return

            # Step 4: Resource
            self._log("[INFO] 載入 resource/base...")
            try:
                from maa.resource import Resource
                resource = Resource()
                resource.post_bundle(RESOURCE_PATH).wait()
                if not resource.loaded:
                    self._log("[ERROR] Resource 載入失敗")
                    self._set_status(STATUS_ERROR)
                    return
                self._log("[INFO] Resource 載入成功 ✓")
            except Exception as e:
                self._log(f"[ERROR] Resource 失敗: {e}")
                self._log(traceback.format_exc())
                self._set_status(STATUS_ERROR)
                return

            # Step 5: AgentClient.bind(resource) — links custom actions to this resource
            self._log("[INFO] 綁定 AgentClient 到 Resource...")
            try:
                ok = agent_client.bind(resource)
                if not ok:
                    self._log("[WARN] AgentClient.bind() 返回 False，Custom Action 可能不可用")
                else:
                    self._log("[INFO] AgentClient.bind() 成功 ✓")
            except Exception as e:
                self._log(f"[WARN] AgentClient.bind() 失敗 (非致命): {e}")

            # Step 6: Tasker
            self._log("[INFO] 初始化 Tasker...")
            try:
                from maa.tasker import Tasker
                Tasker.set_log_dir(DEBUG_DIR)
                tasker = Tasker()
                tasker.bind(resource, controller)
                if not tasker.inited:
                    self._log("[ERROR] Tasker 初始化失敗")
                    self._set_status(STATUS_ERROR)
                    return
                # Save recognition debug screenshots to debug/ so we can verify
                # that the frame adapter is delivering the correct 1280x720 frames.
                tasker.set_debug_mode(True)
                tasker.set_save_draw(True)
                self._tasker_ref = tasker
                self._log("[INFO] Tasker 初始化成功 ✓ (debug截圖已啟用→debug/)")
            except Exception as e:
                self._log(f"[ERROR] Tasker 失敗: {e}")
                self._log(traceback.format_exc())
                self._set_status(STATUS_ERROR)
                return

            # Step 7: Agent subprocess — pass the identifier so AgentServer knows where to connect
            self._log("[INFO] 啟動 Agent 子進程...")
            try:
                venv_py = PROJECT_ROOT / ".venv" / "bin" / "python3"
                python  = str(venv_py) if venv_py.exists() else sys.executable
                agent_proc = subprocess.Popen(
                    [python, "-u", str(AGENT_DIR / "main.py"), socket_id],
                    cwd=str(PROJECT_ROOT),
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    text=True, encoding="utf-8", errors="replace", bufsize=1,
                )
                threading.Thread(
                    target=self._fwd_output, args=(agent_proc,),
                    daemon=True, name="AgentStdout",
                ).start()
                time.sleep(2.0)
                if agent_proc.poll() is not None:
                    self._log(f"[ERROR] Agent 提前退出 rc={agent_proc.returncode}")
                    self._set_status(STATUS_ERROR)
                    return
                self._log(f"[INFO] Agent pid={agent_proc.pid} ✓")
            except Exception as e:
                self._log(f"[ERROR] Agent 啟動失敗: {e}")
                self._log(traceback.format_exc())
                self._set_status(STATUS_ERROR)
                return

            # Step 8: Execute tasks
            for task_name in task_names:
                if self._stop_evt.is_set():
                    self._log("[INFO] 任務已被使用者停止")
                    break
                self._log(f"\n[TASK] ▶ 執行：{task_name}")
                try:
                    job = tasker.post_task(task_name)
                    job.wait()
                    if job.succeeded:
                        self._log(f"[TASK] ✓ {task_name} 完成")
                    else:
                        self._log(f"[TASK] ✗ {task_name} 失敗/未命中")
                except Exception as e:
                    self._log(f"[ERROR] 任務 {task_name}: {e}")
                    self._log(traceback.format_exc())

            self._log("\n[INFO] 所有任務執行完畢")

        except Exception as e:
            self._log(f"[FATAL] 未預期錯誤: {e}")
            self._log(traceback.format_exc())
            self._set_status(STATUS_ERROR)

        finally:
            # Teardown in safe order: stop tasker -> terminate agent proc -> release client
            self._log("[INFO] 正在清理資源...")
            self._tasker_ref = None
            _quiet(lambda: tasker.post_stop() if tasker else None)
            time.sleep(0.2)
            if agent_proc and agent_proc.poll() is None:
                _quiet(lambda: agent_proc.terminate())
                try:
                    agent_proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    _quiet(lambda: agent_proc.kill())
            # CRITICAL: never call __del__ explicitly on maafw objects.
            # MaaAgentClientDestroy (and other native destructors) must only run
            # once — via Python GC when the reference count drops to zero.
            # Calling __del__ explicitly AND then del = double-free = SIGSEGV.
            tasker       = None
            resource     = None
            controller   = None
            agent_client = None
            self._log("[INFO] 清理完成")
            self._set_status(STATUS_IDLE)



    def _fwd_output(self, proc: subprocess.Popen) -> None:
        try:
            for line in proc.stdout:
                self._lq.put(f"[Agent] {line.rstrip()}")
        except Exception:
            pass


def _quiet(fn):
    try:
        fn()
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Window enumeration
# ---------------------------------------------------------------------------

def enumerate_windows() -> list:
    try:
        from maa.toolkit import Toolkit
        result = []
        for w in Toolkit.find_desktop_windows():
            wid = getattr(w, "hwnd", 0)
            if hasattr(wid, "value"):
                wid = wid.value
            result.append({
                "id":         int(wid or 0),
                "title":      getattr(w, "window_name", "") or "",
                "class_name": getattr(w, "class_name", "")  or "",
            })
        return result
    except Exception:
        return []


def find_game_window(wins: list):
    import re
    pat = re.compile(r"^\s*(異環|异环|NTE).*$", re.IGNORECASE)
    for w in wins:
        if "com.pwrd.yh" in w["class_name"] or "yh.ios" in w["class_name"]:
            return w
    for w in wins:
        if pat.search(w["title"]):
            return w
    for w in wins:
        t = w["title"]
        if "異環" in t or "异环" in t or "NTE" in t:
            return w
    return None


# ---------------------------------------------------------------------------
# GUI Application
# ---------------------------------------------------------------------------

class App(tk.Tk):

    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.minsize(860, 580)
        self.resizable(True, True)

        self._lq       = LogQueue()
        self._runner   = TaskRunner(self._lq)
        self._runner.set_status_callback(self._on_status_thread)
        self._windows  = []
        self._sel_win  = None
        self._tvars    = {}   # task_name -> BooleanVar

        try:
            self._iface = load_interface()
        except Exception as exc:
            messagebox.showerror("錯誤", f"無法讀取 interface.json:\n{exc}")
            self._iface = {"_all_tasks": []}

        self._loc = load_locales("zh_tw")
        self._cfg = load_config()

        self._build_ui()
        self._restore_config()

        self.bind(HOTKEY_START, lambda _: self._on_start())
        self.bind(HOTKEY_STOP,  lambda _: self._on_stop())
        self._poll_log()
        self.after(500, self._refresh_windows)

    # ── Build UI ─────────────────────────────────────────────────────────────

    def _build_ui(self):
        self.columnconfigure(0, weight=2, minsize=340)
        self.columnconfigure(1, weight=3, minsize=420)
        self.rowconfigure(0, weight=1)

        left  = ttk.Frame(self, padding=8)
        right = ttk.Frame(self, padding=8)
        left.grid( row=0, column=0, sticky="nsew")
        right.grid(row=0, column=1, sticky="nsew")
        left.columnconfigure(0, weight=1)
        left.rowconfigure(2, weight=1)
        right.columnconfigure(0, weight=1)
        right.rowconfigure(0, weight=1)

        self._build_window_panel(left)
        self._build_control_panel(left)
        self._build_task_panel(left)
        self._build_log_panel(right)

    def _build_window_panel(self, p):
        f = ttk.LabelFrame(p, text="🎮  遊戲窗口", padding=6)
        f.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        f.columnconfigure(0, weight=1)

        self._win_var   = tk.StringVar(value="— 未選擇 —")
        self._win_combo = ttk.Combobox(f, textvariable=self._win_var, state="readonly")
        self._win_combo.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        self._win_combo.bind("<<ComboboxSelected>>", self._on_win_sel)

        ttk.Button(f, text="刷新", width=6, command=self._refresh_windows
                   ).grid(row=0, column=1)

        self._win_info = tk.StringVar()
        ttk.Label(f, textvariable=self._win_info, foreground="gray",
                  font=("TkDefaultFont", 9)
                  ).grid(row=1, column=0, columnspan=2, sticky="w")

    def _build_control_panel(self, p):
        f = ttk.LabelFrame(p, text="⚙️  控制", padding=6)
        f.grid(row=1, column=0, sticky="ew", pady=(0, 6))
        f.columnconfigure(0, weight=1)
        f.columnconfigure(1, weight=1)

        self._status_var = tk.StringVar(value=f"狀態：{STATUS_IDLE}")
        ttk.Label(f, textvariable=self._status_var,
                  font=("TkDefaultFont", 11, "bold")
                  ).grid(row=0, column=0, columnspan=2, sticky="w")

        self._btn_start = ttk.Button(f, text="▶  啟動  (F10)", command=self._on_start)
        self._btn_stop  = ttk.Button(f, text="■  停止  (F11)", command=self._on_stop,
                                     state="disabled")
        self._btn_start.grid(row=1, column=0, sticky="ew", padx=(0, 4), pady=(6, 0))
        self._btn_stop.grid( row=1, column=1, sticky="ew",              pady=(6, 0))

    def _build_task_panel(self, p):
        f = ttk.LabelFrame(p, text="📋  任務列表", padding=6)
        f.grid(row=2, column=0, sticky="nsew")
        f.columnconfigure(0, weight=1)
        f.rowconfigure(0, weight=1)

        canvas = tk.Canvas(f, highlightthickness=0)
        vsb    = ttk.Scrollbar(f, orient="vertical", command=canvas.yview)
        inner  = ttk.Frame(canvas)
        self._task_inner = inner

        inner.bind("<Configure>",
                   lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=inner, anchor="nw")
        canvas.configure(yscrollcommand=vsb.set)
        canvas.grid(row=0, column=0, sticky="nsew")
        vsb.grid(   row=0, column=1, sticky="ns")

        def _wheel(e):
            d = -1*(e.delta//120) if e.delta else (-1 if e.num==4 else 1)
            canvas.yview_scroll(d, "units")
        canvas.bind("<MouseWheel>", _wheel)
        canvas.bind("<Button-4>",   _wheel)
        canvas.bind("<Button-5>",   _wheel)

        self._fill_tasks()

        bf = ttk.Frame(f)
        bf.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(4, 0))
        ttk.Button(bf, text="全選",   width=7,
                   command=lambda: self._set_all(True) ).pack(side="left", padx=2)
        ttk.Button(bf, text="全不選", width=7,
                   command=lambda: self._set_all(False)).pack(side="left", padx=2)

    def _fill_tasks(self):
        for w in self._task_inner.winfo_children():
            w.destroy()
        self._tvars.clear()

        IS_MACOS = sys.platform == "darwin"
        WIN32_CTRL = {"Win32", "Win32-Front"}

        seen_groups = set()
        row = 0
        for task in self._iface.get("_all_tasks", []):
            name = task.get("name", "")
            if not name:
                continue

            # group is a list e.g. ["Daily"] — take first element
            grp_raw = task.get("group", [])
            grp = grp_raw[0] if isinstance(grp_raw, list) and grp_raw else (
                grp_raw if isinstance(grp_raw, str) else "")

            label = tr(task.get("label", name), self._loc) or name

            # Controller compatibility: tasks with only Win32 entries can't run on macOS
            ctrl_list = task.get("controller", [])
            win32_only = bool(ctrl_list) and all(c in WIN32_CTRL for c in ctrl_list)
            macos_disabled = IS_MACOS and win32_only

            if grp and grp not in seen_groups:
                seen_groups.add(grp)
                glabel = self._loc.get(f"group.{grp}.label", grp)
                ttk.Label(self._task_inner,
                          text=f"── {glabel} ──",
                          foreground="#888", font=("TkDefaultFont", 9)
                          ).grid(row=row, column=0, sticky="w", padx=4, pady=(8, 1))
                row += 1

            var = tk.BooleanVar(value=False)
            self._tvars[name] = var

            display_label = f"{label}  (僅 Windows)" if macos_disabled else label
            cb = ttk.Checkbutton(self._task_inner, text=display_label, variable=var)
            if macos_disabled:
                cb.config(state="disabled")
                var.set(False)
            cb.grid(row=row, column=0, sticky="w", padx=16)
            row += 1

    def _build_log_panel(self, p):
        f = ttk.LabelFrame(p, text="📝  日誌", padding=6)
        f.grid(row=0, column=0, sticky="nsew")
        f.columnconfigure(0, weight=1)
        f.rowconfigure(0, weight=1)

        self._log = scrolledtext.ScrolledText(
            f, wrap="word", font=LOG_FONT,
            state="disabled",
            background=LOG_BG, foreground=LOG_FG,
            insertbackground="white",
        )
        self._log.grid(row=0, column=0, sticky="nsew")
        for tag, colour in LOG_TAGS.items():
            self._log.tag_config(tag, foreground=colour)

        bf = ttk.Frame(f)
        bf.grid(row=1, column=0, sticky="ew", pady=(4, 0))
        ttk.Button(bf, text="清除日誌", command=self._clear_log).pack(side="right")

    # ── Event handlers ────────────────────────────────────────────────────────

    def _refresh_windows(self):
        self._lq.put("[INFO] 掃描窗口...")
        threading.Thread(target=lambda: self.after(
            0, self._update_wins, enumerate_windows()
        ), daemon=True).start()

    def _update_wins(self, wins: list):
        self._windows = wins
        self._win_combo["values"] = [(w["title"] or "(no title)")[:60] for w in wins]
        self._lq.put(f"[INFO] 發現 {len(wins)} 個窗口")
        game = find_game_window(wins)
        if game:
            self._win_combo.current(wins.index(game))
            self._on_win_sel()
            self._lq.put(f"[INFO] 自動選取：{game['title']}")
        elif wins:
            self._lq.put("[WARN] 未找到異環窗口，請手動選擇或先打開遊戲")

    def _on_win_sel(self, _=None):
        idx = self._win_combo.current()
        if 0 <= idx < len(self._windows):
            w = self._windows[idx]
            self._sel_win = w
            self._win_info.set(f"id={w['id']}  {w['class_name'][:40]}")
        else:
            self._sel_win = None
            self._win_info.set("")

    def _on_start(self):
        if self._runner.is_running():
            return
        if not self._sel_win:
            messagebox.showwarning("未選擇窗口", "請先選擇遊戲窗口（或點擊「刷新」）")
            return
        tasks = [n for n, v in self._tvars.items() if v.get()]
        if not tasks:
            messagebox.showwarning("未選擇任務", "請至少勾選一個任務")
            return
        self._lq.put(f"[INFO] 啟動任務：{', '.join(tasks)}")
        self._runner.start(self._sel_win["id"], tasks)
        self._save_config()

    def _on_stop(self):
        if self._runner.is_running():
            self._runner.stop()

    def _on_status_thread(self, s: str):
        self.after(0, self._apply_status, s)

    def _apply_status(self, s: str):
        self._status_var.set(f"狀態：{s}")
        running = (s == STATUS_RUNNING)
        self._btn_start.config(state="disabled" if running else "normal")
        self._btn_stop.config( state="normal"   if running else "disabled")

    def _set_all(self, val: bool):
        for v in self._tvars.values():
            v.set(val)

    # ── Log polling ───────────────────────────────────────────────────────────

    def _poll_log(self):
        msgs = self._lq.drain()
        if msgs:
            self._log.config(state="normal")
            for msg in msgs:
                tag = next((t for t in LOG_TAGS if f"[{t}]" in msg), None)
                self._log.insert("end", msg + "\n", tag)
            self._log.see("end")
            self._log.config(state="disabled")
        self.after(120, self._poll_log)

    def _clear_log(self):
        self._log.config(state="normal")
        self._log.delete("1.0", "end")
        self._log.config(state="disabled")

    # ── Config ────────────────────────────────────────────────────────────────

    def _restore_config(self):
        insts = self._cfg.get("instances", [])
        if not insts:
            return
        saved = {t["taskName"]: t for t in insts[0].get("tasks", [])}
        for name, var in self._tvars.items():
            if name in saved:
                var.set(bool(saved[name].get("enabled", False)))

    def _save_config(self):
        cfg = load_config()
        if not cfg.get("instances"):
            cfg["instances"] = [_DEFAULT_CFG["instances"][0].copy()]
        cfg["instances"][0]["tasks"] = [
            {"id": n[:7], "taskName": n, "enabled": v.get(), "optionValues": {}}
            for n, v in self._tvars.items() if v.get()
        ]
        _save_config(cfg)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
