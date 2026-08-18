# MaaNTE macOS (Apple Silicon ARM64) 代码审计报告

> **目标**：在 Apple Silicon (arm64) macOS 上运行 MaaNTE，使用 macOS 原生体系控制《异环》（NTE），保持原有 Pipeline、Resource、Tasker、AgentServer、MaaFramework 业务逻辑不变，将 Windows-specific 依赖抽象隔离并提供 macOS 后端适配。
> **审计日期**：2026-08-18  
> **审计范围**：`agent/`、`config/`、`maafw/`、`thirdparty/`、`resource/`、`interface.json`、`requirements.txt` 全量文件

---

## 目录
1. [项目总体架构与启动链分析](#1-项目总体架构与启动链分析)
2. [代码依赖审计分类清单 (A ~ F)](#2-代码依赖审计分类清单)
   - [A. Windows-specific Imports & Native APIs](#a-windows-specific-imports--native-apis)
   - [B. MaaFramework 调用点与生命周期](#b-maaframework-调用点与生命周期)
   - [C. Controller 创建、注册与初始化位置](#c-controller-创建注册与初始化位置)
   - [D. 关键抽象边界分析 (Screenshot / Mouse / Keyboard / Window / Hotkey)](#d-关键抽象边界分析)
   - [E. Launcher 与运行时环境依赖](#e-launcher-与运行时环境依赖)
   - [F. 硬编码 Windows 路径、文件与二进制资产](#f-硬编码-windows-路径文件与二进制资产)
3. [各模块移植评估与标记清单 [REUSE] / [ADAPTER] / [REWRITE] / [UNKNOWN]](#3-各模块移植评估与标记清单)
4. [核心数据流分析 (Windows vs macOS)](#4-核心数据流分析)
5. [目标架构设计 (Backend & Adapter 模式)](#5-目标架构设计)
6. [macOS 技术选型与权限模型](#6-macos-技术选型与权限模型)
7. [分阶段移植执行路线图 (PHASE 0 ~ PHASE 12)](#7-分阶段移植执行路线图)

---

## 1. 项目总体架构与启动链分析

### 1.1 总体启动链
- **启动层**：宿主 UI（如 MXU / MFAA 或 CLI 脚本）读取 `interface.json`，配置 Controller、Resource 与子进程启动参数（`agent.child_exec`、`agent.child_args`）。
- **进程层**：宿主启动 `python agent/main.py <socket_id>`，并通过环境变量（`PI_CONTROLLER`、`PI_RESOURCE`、`PI_CLIENT_NAME` 等）向 Python 传递配置。
- **服务层**：`agent/main.py` 调用 `AgentServer.start_up(socket_id)` 启动 RPC 通信，加载 `custom` 下所有自定义动作（`CustomAction`）。
- **调度层**：MaaFramework Tasker 读取 `resource/tasks/*.json` 和 `resource/base/pipeline/*.json` 执行自动化流水线。
- **控制层**：Tasker 通过 Controller 执行截图、点击、按键等原子交互。

### 1.2 关键架构发现
- **Agent 架构纯粹**：业务核心（`agent/main.py`、`agent/custom/action/`）是标准的 MaaFramework AgentServer 模式，通过 RPC（Socket）与宿主客户端（MXU / MFAA / 自定义客户端）通信。
- **Pipeline 完全跨平台**：`resource/base/pipeline/` 与 `resource/tasks/` 中的 JSON 描述文件是声明式的，不包含操作系统 API，完全依赖底层 Controller 提供的 `screencap`、`click`、`key_down`、`key_up` 等基础原子指令。
- **MaaFramework 官方原生支持 macOS**：MaaFramework 5.x（`maafw==v5.10.4`）在 macOS 上原生内置了 `MacOSController`（基于 ScreenCaptureKit 截图与 CGEvent 键鼠输入）、`PlayCoverController`、`CustomController` 以及 `Toolkit.find_desktop_windows`、`Toolkit.macos_check_permission`。

---

## 2. 代码依赖审计分类清单

### A. Windows-specific Imports & Native APIs

| 文件路径 | 涉及 Windows API / 库 | 用途说明 | 影响度 |
| :--- | :--- | :--- | :--- |
| `agent/utils/win32_process.py` | `ctypes.windll.user32` (`GetWindowRect`, `GetClientRect`, `EnumWindows`, `SetWindowPos`, `ShowWindow`, `SetProcessDPIAware`, `GetWindowTextW`, `GetClassNameW` 等), `kernel32` (`CreateToolhelp32Snapshot`, `Process32FirstW`, `Process32NextW`, `Sleep`) | 查找游戏窗口、获取客户端尺寸、窗口缩放、DPI 调整、进程快照枚举 | **重度 (需完全隔离并为 macOS 提供适配器)** |
| `agent/main.py` | `ctypes.windll.shell32.IsUserAnAdmin` | 管理员权限检测 | **低 (macOS 上替换为平台权限/无感知处理)** |
| `agent/main.py` | `utils.win32_process.find_window_by_process`, `get_client_size` | 启动时检测游戏窗口分辨率（1280x720）并警告 | **中 (需调用统一的 Window Backend)** |
| `agent/custom/action/auto_piano/maa_keyboard.py` | `ctypes.windll.user32` (`PostMessageW`, `SendMessageW`, `MapVirtualKeyW`, `FindWindowW`, `WM_KEYDOWN`, `WM_KEYUP`, `WM_ACTIVATE`) | 自动弹琴：独立绕过 Controller 直接向 Win32 HWND 发送虚拟按键和硬件扫描码 | **高 (需抽象为键盘后端，优先走 Controller 或 macOS CGEvent)** |
| `agent/custom/action/MapTeleport/teleport_to_point.py` | `ctypes.windll.user32.GetCursorPos`, `WindowFromPoint`, `ScreenToClient`, `wintypes.POINT` | 地图传送：获取当前鼠标在游戏客户区内的绝对坐标 | **中 (需抽象为鼠标坐标获取适配器)** |
| `agent/custom/action/auto_f_scroll.py` | `ctypes.windll.user32.GetAsyncKeyState`, `mouse_event` (`MOUSEEVENTF_WHEEL`) | 物理长按 F 键连点与滚轮下滚 | **中 (需提供 macOS 物理按键监听/滚轮适配器或纯 Controller 方案)** |
| `agent/custom/action/pinkpaw/pinkpaw_core3.py` | `ctypes.windll.user32.SendInput`, `_INPUT`, `_KEYBDINPUT`, `_MOUSEINPUT`, `MapVirtualKeyW` | 粉爪行动：`DirectInputSender` 高性能低延迟直发键盘/鼠标输入 | **中 (已有 controller 优雅回退，macOS 可用 CGEvent/Controller 适配)** |
| `agent/custom/action/pinkpaw/pinkpaw_common.py` | `sys.platform == "win32"` 判断并引入 `win32_process` | 窗口分辨率自适应导入保护 | **低 (已具备条件分支，需接入统一 Window 适配器)** |
| `agent/custom/action/Common/resize_game_window.py` | `utils.win32_process.ensure_game_window_resolution` | 自定义动作：调整游戏窗口至 1280x720 | **中 (需接入统一 Window 适配器)** |
| `agent/custom/action/DatasetCollection/autonomous_driving_dataset_recorder.py` | `ctypes.windll.user32.GetAsyncKeyState` | 自动驾驶数据集采集：监听物理 WASD 按键状态记录标签 | **低 (属于辅助录制工具，macOS 可用 pynput/Quartz 监听)** |
| `agent/custom/action/SoundTrigger/SoundListener.py` | `ctypes.windll.ole32.CoInitialize(None)`, `soundcard` | 声音闪避监听：WASAPI 系统内录/音频采集 | **低 (特定玩法组件，Windows COM 初始化在 macOS 上需跳过)** |

---

### B. MaaFramework 调用点与生命周期

MaaFramework 在本项目中主要通过官方 Python 绑定 `maafw`（即 `maa.*` 命名空间）调用。

| 模块 / 类 | 调用位置 | 用途与生命周期 |
| :--- | :--- | :--- |
| `maa.agent.agent_server.AgentServer` | `agent/main.py:509-534`, `agent/custom/action/**` | **生命周期核心**：<br>1. `@AgentServer.custom_action("action_name")` 装饰器注册所有自定义动作；<br>2. `AgentServer.start_up(socket_id)` 启动 RPC 代理服务端；<br>3. `AgentServer.join()` 阻塞监听；<br>4. `AgentServer.shut_down()` 优雅退出。 |
| `maa.tasker.Tasker` | `agent/main.py:510, 514` | 全局日志目录设置 `Tasker.set_log_dir("./debug")`；在 CustomAction 中通过 `context.tasker` 访问 `stopping` 状态与 `controller` 实例。 |
| `maa.context.Context` | `agent/custom/action/**` | CustomAction 运行上下文，提供：<br>- `context.run_task(node_name, pipeline_override)`<br>- `context.run_action(node_name, pipeline_override)`<br>- `context.run_recognition(node_name, frame)`<br>- `context.run_recognition_direct(type, param, frame)`<br>- `context.tasker.controller` 获取控制器句柄。 |
| `maa.custom_action.CustomAction` | `agent/custom/action/**` | 自定义动作基类，所有业务动作继承自 `CustomAction` 并实现 `run(self, context, argv) -> CustomAction.RunResult`。 |
| `maa.pipeline.*` (`JOCR`, `JRecognitionType`) | `agent/custom/action/MapTeleport/teleport_to_point.py` | 动态构建 MaaFramework Pipeline Recognition 对象进行直接识别。 |
| `maa.controller.*` | `agent/custom/action/**` | 控制器操作：<br>- `controller.post_screencap().wait()`<br>- `controller.cached_image`<br>- `controller.post_touch_down`, `post_touch_move`, `post_touch_up`<br>- `controller.post_click`, `post_click_key`, `post_key_down`, `post_key_up`<br>- `controller.post_swipe`, `post_relative_move` |
| `maa.toolkit.Toolkit` | 内置支持 | `Toolkit.find_desktop_windows()`、`Toolkit.macos_check_permission()`、`Toolkit.macos_request_permission()`。 |

---

### C. Controller 创建、注册与初始化位置

1. **宿主 / UI 端注册 (`interface.json`)**：
   - 宿主程序读取 `interface.json` 的 `controller` 列表。
   - 目前仅定义了 `Win32`、`Win32-Front`、`Win32-Background`、`CloudGame-Front`（类型均为 `Win32`）。
   - **移植需求**：必须在 `interface.json` 中增加 `MacOS` 控制器配置（类型 `MacOS`，包含 `title_regex`、`screencap`、`input`）。

2. **环境变量注入 (`PI_CONTROLLER`)**：
   - 宿主连接控制器后，通过环境变量 `PI_CONTROLLER` 传递控制器配置 JSON 给 Python 子进程。
   - `agent/utils/pienv.py` 中已经解析 `Win32Config` 与 `MacOSConfig`。

3. **AgentServer / Tasker 端绑定**：
   - AgentServer 与客户端建立连接后，MaaFramework 核心根据 `PI_CONTROLLER` 实例化对应的 Controller 原生对象。
   - 在 Python `CustomAction.run(context, argv)` 中，通过 `context.tasker.controller` 即可无缝获取该 Controller。

---

### D. 关键抽象边界分析

| 子系统 | 当前实现 (Windows) | 抽象边界定义与存在的问题 | macOS 适配方案 |
| :--- | :--- | :--- | :--- |
| **Window Discovery & Bounds** | `utils/win32_process.py`<br>- `EnumWindows`<br>- `GetWindowRect`<br>- `GetClientRect` | **边界模糊**：多处直接 `from utils.win32_process import ...`，硬编码 `"HTGame.exe"` 进程名。<br>macOS 下无 HWND 和 Win32 进程模型。 | **建立 `platform/window_manager.py` 抽象**：<br>- macOS Backend 使用 CoreGraphics `CGWindowListCopyWindowInfo` / `NSWorkspace` 枚举窗口。<br>- 支持根据 App 名称（如 `"异环"`、`"NTE"`、`"PlayCover"`）获取 `CGWindowID` 与实际窗口 Bounds。 |
| **Screenshot** | 1. MaaFramework Win32 Controller (`PrintWindow` / `BitBlt` / `FramePool`)<br>2. `context.tasker.controller.post_screencap()` | **标准良好**：绝大多数动作统一走 `controller.post_screencap()`，仅依赖 `cached_image` (BGR NumPy 数组)。 | **直接复用 MaaFramework `MacOSController`**（底层基于 macOS 12.3+ 原生高性能 `ScreenCaptureKit`，或回退 `CGWindowListCreateImage`）。 |
| **Mouse Input** | 1. `controller.post_touch_*` / `post_click`<br>2. `pinkpaw_core3.py` 的 `SendInput`<br>3. `teleport_to_point.py` 的 `GetCursorPos` | **部分泄露**：部分代码绕过 Controller 使用 Win32 `SendInput` 和 `GetCursorPos` 获取鼠标绝对位置。 | 1. 业务逻辑统一优先走 `controller`；<br>2. 为 `GetCursorPos` 提供抽象：macOS 下使用 Quartz `CGEventGetLocation(CGEventCreate(NULL))` 并转换到窗口坐标。 |
| **Keyboard Input** | 1. `controller.post_key_down/up`<br>2. `maa_keyboard.py` (Win32 `PostMessageW`)<br>3. `auto_f_scroll.py` (`GetAsyncKeyState`) | **部分泄露**：钢琴模块和 F键连点模块直接调用 Win32 键盘消息。 | 1. 弹琴模块 `MaaKeyboardBridge` 改为使用 Controller 或 macOS Quartz `CGEventCreateKeyboardEvent`；<br>2. 物理按键状态监听使用 macOS 原生 `CGEventTap` 或 `pynput`。 |
| **Hotkey** | `config/mxu-MaaNTE.json` 中的 `hotkeys` (F10/F11) | 由外层 UI 客户端或全局热键监听驱动。 | macOS 下由 UI 客户端或 `pynput` / Carbon Global Hotkey 监听。 |

---

### E. Launcher 与运行时环境依赖

| 组件 | Windows 现状 | macOS 需求与适配 |
| :--- | :--- | :--- |
| **可执行文件** | `MaaNTE.exe`（PE x86_64 二进制） | macOS 无法运行 `.exe`。在第一阶段直接通过 macOS 终端 / Python 脚本启动；后续打包为 macOS `.app` 或跨平台 UI。 |
| **子进程启动配置** | `interface.json`: `"child_exec": "./python/python.exe"` | macOS 上需适配为当前 Python 解释器（如 `python3`、`.venv/bin/python3`）。 |
| **虚拟环境管理** | `agent/main.py:ensure_venv_and_relaunch_if_needed()` | 已有 Linux/POSIX 分支（寻找 `bin/python3`），只需补充 Darwin 平台识别。 |
| **依赖离线包** | `deps/*.whl` (Windows amd64 wheels) | macOS 需使用在线 pip 安装或提供 `macosx_11_0_arm64.whl`。 |

---

### F. 硬编码 Windows 路径、文件与二进制资产

| 资产文件 / 路径 | 类型 | 处理策略 |
| :--- | :--- | :--- |
| `maafw/*.dll` | Windows DLLs | **macOS 不需要**。通过 `pip install maafw` 安装 macOS arm64 原生 `.dylib`。 |
| `thirdparty/nte_coordinate_api.cp312-win_amd64.pyd` | Windows CPython 扩展 | **macOS 无法加载**。Navi 模块设计已包含自动回退到图像视觉定位 `map_locator.py`，保持安全回退。 |
| `thirdparty/pyarmor_runtime_000000/pyarmor_runtime.pyd` | Windows 加密运行时 | **macOS 无法加载**。开源源码运行无需该文件。 |
| `requirements.txt` 中的 `onnxruntime-directml` | Windows 专有库 | **替换为 `onnxruntime`**（macOS arm64 原生支持 CPU 与 Apple CoreML）。 |
| `requirements.txt` 中的 `pktmon-interface` | Windows 专有网络监听库 | **标记可选依赖**，macOS 上禁用或使用标准 pcap。 |
| `requirements.txt` 中的 `soundcard` | 音频库 | 在 macOS 上如无需音频闪避可作为可选依赖。 |

---

## 3. 各模块移植评估与标记清单

- `[REUSE]`：无需修改，直接复用
- `[ADAPTER]`：需抽象或封装平台适配器
- `[REWRITE]`：必须针对 macOS 重新编写
- `[UNKNOWN]`：依赖外部运行环境，需进一步实机验证

| 模块 / 路径 | 分类 | 说明 |
| :--- | :---: | :--- |
| `agent/main.py` | `[ADAPTER]` | 虚拟环境重拉起逻辑适配 macOS；移除 Windows 管理员独占检查；分辨率检测接入平台窗口适配器。 |
| `agent/utils/logger.py` | `[REUSE]` | 纯 Python 标准 logging / loguru 实现，完全跨平台。 |
| `agent/utils/i18n.py` | `[REUSE]` | 纯 Python JSON 本地化解析，完全跨平台。 |
| `agent/utils/maafocus.py` | `[REUSE]` | 基于 MaaFramework Context 的 Focus 通信协议，完全跨平台。 |
| `agent/utils/screen.py` | `[REUSE]` | 基准分辨率（1280x720）坐标转换算法，完全跨平台。 |
| `agent/utils/pienv.py` | `[REUSE]` | 已内置 `MacOSConfig` 等 PI v2.5.0 数据结构，完全跨平台。 |
| `agent/utils/win32_process.py` | `[REWRITE]` | 保留 Windows 实现，新增 `platform/macos/window.py` 并在上层提供统一的 `window_manager` 抽象。 |
| `agent/custom/action/Common/resize_game_window.py` | `[ADAPTER]` | 将直接引用 `win32_process` 改为调用统一 `window_manager`。 |
| `agent/custom/action/Common/click.py` | `[REUSE]` | 标准 MaaFramework Controller 操作。 |
| `agent/custom/action/Common/alt_click.py` | `[REUSE]` | 标准 MaaFramework Controller 操作。 |
| `agent/custom/action/Common/enable_node.py` | `[REUSE]` | 标准 MaaFramework Context 操作。 |
| `agent/custom/action/Common/utils.py` | `[REUSE]` | OpenCV 模板匹配与 Controller 点击封装，完全跨平台。 |
| `agent/custom/action/Movement/character_move.py` | `[REUSE]` | 标准 MaaFramework Controller 按键操作。 |
| `agent/custom/action/Movement/mouse_move.py` | `[REUSE]` | 标准 MaaFramework Controller 相对移动操作。 |
| `agent/custom/action/AutoCoffee/*` | `[REUSE]` | 纯 Pipeline / Context / OpenCV 动作。 |
| `agent/custom/action/AutoFish/*` | `[REUSE]` | 纯 Pipeline / Context / OpenCV 动作。 |
| `agent/custom/action/BagelSpam/*` | `[REUSE]` | 纯 Pipeline / Context 动作。 |
| `agent/custom/action/Furniture/*` | `[REUSE]` | 纯 Pipeline / Context 动作。 |
| `agent/custom/action/MapTeleport/check_teleport_required.py` | `[REUSE]` | 纯算法与 JSON 数据解析。 |
| `agent/custom/action/MapTeleport/teleport_to_point.py` | `[ADAPTER]` | 仅 `_get_cursor_pos()` 获取鼠标位置需抽象平台适配。 |
| `agent/custom/action/pinkpaw/pinkpaw_core3.py` | `[ADAPTER]` | `DirectInputSender` 增加 macOS 原生 CGEvent 后端（或走 Controller）。 |
| `agent/custom/action/pinkpaw/pinkpaw_common.py` | `[ADAPTER]` | 窗口自适应调用接入统一 `window_manager`。 |
| `agent/custom/action/auto_piano/maa_keyboard.py` | `[REWRITE]` | 抽象 `KeyboardBridge`，提供 macOS Quartz CGEvent / Controller 实现。 |
| `agent/custom/action/auto_piano/player.py` | `[REUSE]` | 纯 MIDI 调度算法。 |
| `agent/custom/action/auto_piano/midi_processor.py` | `[REUSE]` | 基于 `mido` 的跨平台 MIDI 解析。 |
| `agent/custom/action/auto_f_scroll.py` | `[ADAPTER]` | 物理 F 键监听和滚轮注入通过平台适配器抽象。 |
| `agent/custom/action/Navi/angle_predictor.py` | `[ADAPTER]` | ONNX 运行时适配 macOS arm64 CPU / CoreML Execution Provider。 |
| `agent/custom/action/Navi/coordinate_position.py` | `[REUSE]` | 在 macOS 上优雅回退到 `map_locator.py` 视觉定位，无需修改。 |
| `agent/custom/action/Navi/local_route_navigation.py` | `[REUSE]` | 纯算法与导航状态机。 |
| `agent/custom/action/Navi/online_map_navigation_action.py` | `[REUSE]` | 纯算法与网络地图协议。 |
| `agent/custom/action/SoundTrigger/SoundListener.py` | `[ADAPTER]` | 去除 Windows OLE 初始化，macOS 上做条件支持或优雅跳过。 |
| `interface.json` | `[ADAPTER]` | 添加 macOS Controller 配置节点；适配 `child_exec`。 |
| `requirements.txt` | `[ADAPTER]` | 分离 Windows 独占包（`onnxruntime-directml`、`pktmon-interface`），提供 macOS 兼容依赖。 |
| `resource/tasks/*.json` | `[REUSE]` | 全部任务定义完全跨平台，禁止修改。 |
| `resource/base/pipeline/*.json` | `[REUSE]` | 全部 Pipeline 节点完全跨平台，禁止修改。 |

---

## 4. 核心数据流分析

### 4.1 截图数据流 (Screenshot)
- **Windows**: `Game Window (UnrealWindow HWND)` $ightarrow$ `MaaWin32ControlUnit` (PrintWindow/BitBlt) $ightarrow$ `MaaControllerCachedImage` $ightarrow$ `cv2 BGR ndarray` $ightarrow$ `CustomAction / Pipeline`
- **macOS**: `Game Window (CGWindowID)` $ightarrow$ `MaaMacOSControlUnit` (ScreenCaptureKit / CGWindowListCreateImage) $ightarrow$ `MaaControllerCachedImage` $ightarrow$ `cv2 BGR ndarray` $ightarrow$ `CustomAction / Pipeline`
- **结论**：上层数据流完全一致，无需改动任何图像识别逻辑。

### 4.2 键盘数据流 (Keyboard)
- **Windows**: `Tasker / Pipeline` $ightarrow$ `Controller.post_key_down(vk)` $ightarrow$ `Win32 PostMessage / SendInput` $ightarrow$ `Game Window`
- **macOS**: `Tasker / Pipeline` $ightarrow$ `Controller.post_key_down(vk)` $ightarrow$ `MaaMacOSControlUnit` (`CGEventPost` / `PostToPid`) $ightarrow$ `Game Window`
- **注意**：部分绕过 Controller 的模块（如 `auto_piano`、`pinkpaw_core3`）需接入 `platform/input_sender.py` 统一分发。

### 4.3 鼠标数据流 (Mouse)
- **Windows**: `Tasker / Pipeline` $ightarrow$ `Controller.post_touch_* / post_click` $ightarrow$ `Win32 SendMessage / Seize` $ightarrow$ `Game Window`
- **macOS**: `Tasker / Pipeline` $ightarrow$ `Controller.post_touch_* / post_click` $ightarrow$ `MaaMacOSControlUnit` (`CGEventPost` 鼠标事件) $ightarrow$ `Game Window`

### 4.4 窗口发现数据流 (Window Discovery)
- **Windows**: `find_window_by_process("HTGame.exe")` $ightarrow$ `EnumWindows` $ightarrow$ `HWND` $ightarrow$ `GetClientRect`
- **macOS**: `find_window("异环" / "NTE")` $ightarrow$ `CGWindowListCopyWindowInfo` / `NSWorkspace` $ightarrow$ `CGWindowID` $ightarrow$ `Window Bounds`

---

## 5. 目标架构设计

采用 **Backend / Adapter 架构**，对业务层完全隐藏底层操作系统差异：

```
MaaNTE
├── Agent
│   ├── main.py (平台无关入口)
│   ├── Tasker / AgentServer (MaaFramework RPC)
│   └── custom/action/ (业务 CustomAction)
│
├── Platform Layer (新增抽象层 agent/platform/)
│   ├── __init__.py (统一平台检测与工厂接口)
│   ├── base.py (抽象基类: WindowManager, InputAdapter, ScreenAdapter)
│   │
│   ├── windows/ (Windows 原生实现)
│   │   ├── __init__.py
│   │   ├── window.py (从 agent/utils/win32_process.py 桥接)
│   │   └── input.py (Win32 SendInput / PostMessage)
│   │
│   └── macos/ (macOS 原生实现)
│       ├── __init__.py
│       ├── window.py (CoreGraphics / NSWorkspace)
│       ├── input.py (Quartz CGEvent)
│       └── permissions.py (ScreenCapture / Accessibility 权限检查)
│
├── MaaFramework Core
│   ├── Win32Controller (Windows)
│   └── MacOSController / CustomController (macOS)
│
└── Resource / Pipeline / Tasks (100% 保持原有逻辑)
```

---

## 6. macOS 技术选型与权限模型

### 6.1 技术选型
1. **窗口发现与管理 (`agent/platform/macos/window.py`)**:
   - `Quartz.CGWindowListCopyWindowInfo`: 枚举窗口、获取 `kCGWindowNumber` (CGWindowID)、`kCGWindowOwnerName`、`kCGWindowBounds`。
   - `AppKit.NSWorkspace`: 获取运行中应用 PID 与前台激活（`activateWithOptions:`）。
2. **截图 (`Screenshot`)**:
   - 优先直接使用 MaaFramework 原生 `MacOSController` 的 `ScreenCaptureKit`。
   - 备选/独立调试工具使用 `Quartz.CGWindowListCreateImage`。
3. **输入模拟 (`Input`)**:
   - 优先使用 MaaFramework 原生 `MacOSController`。
   - 物理按键/独立注入使用 `Quartz.CGEventCreateKeyboardEvent`、`Quartz.CGEventCreateMouseEvent`、`Quartz.CGEventPost`。
4. **Retina 坐标与缩放**:
   - macOS 逻辑点（Points）与物理像素（Pixels）比例通常为 1:2。
   - 所有坐标在 `platform/macos` 中统一缩放到以 1280x720 为基准的逻辑坐标系，严禁在任务 JSON 中硬编码乘 2。

### 6.2 权限要求
macOS 运行所需的系统权限（通过系统设置授权）：
- **屏幕录制权限 (Screen Recording)**：用于截取游戏画面（ScreenCaptureKit）。
- **辅助功能权限 (Accessibility)**：用于模拟全局鼠标与键盘事件（CGEventPost）。

---

## 7. 分阶段移植执行路线图

| 阶段 | 阶段名称 | 核心交付物与目标 | 验证方式 |
| :--- | :--- | :--- | :--- |
| **PHASE 0** | **代码审计 (当前)** | 输出 `docs/macos-port-audit.md`，完成全量依赖与调用链扫描。 | 静态审计完成并归档。 |
| **PHASE 1** | **MaaFramework macOS arm64 验证** | 验证 macOS 环境下 `import maafw`、`maa.controller.MacOSController` 原生库加载正常。 | `tests/macos/test_platform.py` |
| **PHASE 2** | **Agent 启动与虚拟环境适配** | 适配 `agent/main.py` 启动链、环境变量解析、移除 Windows 独占检查。 | 在 macOS 终端成功启动 `python agent/main.py` |
| **PHASE 3** | **macOS Window Discovery** | 实现 `agent/platform/macos/window.py`，支持定位游戏窗口并获取尺寸。 | `tests/macos/test_window.py` |
| **PHASE 4** | **macOS Screenshot** | 验证 `MacOSController` 截图与尺寸缩放。 | `tests/macos/test_screenshot.py` |
| **PHASE 5** | **macOS Keyboard Backend** | 实现并验证按键按下、抬起、单击及键盘桥接。 | `tests/macos/test_keyboard.py` |
| **PHASE 6** | **macOS Mouse Backend** | 实现并验证鼠标移动、点击、拖拽及坐标转换。 | `tests/macos/test_mouse.py` |
| **PHASE 7** | **Controller 集成与 interface.json** | 更新 `interface.json` 添加 MacOS 控制器描述，打通 AgentServer 与 Controller。 | AgentServer 成功挂载 MacOSController |
| **PHASE 8** | **最小 Pipeline 运行验证** | 运行最简 MaaFramework Pipeline 节点（如截图比对、点击）。 | 自动化 Pipeline 测试脚本 |
| **PHASE 9** | **已有任务全量测试** | 测试 Daily、Coffee、Fish、Teleport、PinkPaw 等已有任务。 | 各任务端到端运行 |
| **PHASE 10**| **Retina / DPI / 缩放精度调优** | 统一校验 Retina 屏幕下识别坐标与点击坐标精确对齐。 | `tests/macos/test_scaling.py` |
| **PHASE 11**| **Launcher / 脚本打包** | 提供 macOS 启动脚本（`MaaNTE.sh` 或 `.command`）与环境配置向导。 | 用户一键启动运行 |
| **PHASE 12**| **高级功能 (OpenClaw / 自动化工具)** | 评估可选网络与高级功能集成。 | 扩展功能验证 |

---
**PHASE 0 代码审计完成**。
