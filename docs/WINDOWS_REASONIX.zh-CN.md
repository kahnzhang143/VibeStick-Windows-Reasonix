# VibeStick Windows + Reasonix

本版本让 M5Stack StickS3 在 Windows 上作为 Reasonix 语音遥控器和状态终端使用。

## 工作方式

```text
StickS3 麦克风
    │ 16 kHz / 16-bit PCM，Wi-Fi HTTP
    ▼
VibeStick Windows Bridge
    │ OpenAI 兼容 ASR 或本地转写命令
    ├─ 将文本粘贴到当前聚焦的 Reasonix 窗口
    └─ 读取受管 Reasonix Serve 的运行状态
          ▼
StickS3 显示 IDLE / RUNNING / APPROVAL / DONE / ERROR
```

StickS3 不会注册成 Windows 蓝牙麦克风。录音通过局域网发送给 Bridge，识别完成后通过 Win32 Unicode 键盘事件输入当前窗口，不会覆盖用户原有的剪贴板内容。

## 要求

- Windows 10 或 Windows 11
- Python 3.11+
- Node.js 20+
- Reasonix 1.x
- ESP-IDF 5.5.x，用于编译和烧录固件
- StickS3 与电脑连接到同一个 2.4 GHz 局域网
- 一个 OpenAI 兼容语音识别服务，或者本地转写命令

安装 Reasonix：

```powershell
npm install -g reasonix
reasonix --version
```

## 1. 初始化配置

在仓库根目录运行：

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\setup.ps1
```

脚本会：

- 从示例创建 `.env`
- 创建固件 secrets 文件
- 生成并同步 Bridge token
- 自动检测 Windows 局域网 IPv4
- 将默认 provider 设置为 `reasonix`

编辑：

```text
firmware\sticks3\include\vibe_stick_secrets.h
```

填写 2.4 GHz Wi-Fi：

```c
#define VIBE_STICK_WIFI_SSID "your-wifi"
#define VIBE_STICK_WIFI_PASSWORD "your-password"
```

确认 `VIBE_STICK_BRIDGE_HOST` 是 Windows 电脑的局域网 IPv4，而不是 `127.0.0.1`。

## 2. 配置语音识别

编辑仓库根目录的 `.env`。SiliconFlow 示例：

```env
VIBE_STICK_PROVIDER=reasonix
VIBE_STICK_ASR_PROVIDER=openai-compatible
VIBE_STICK_ASR_BASE_URL=https://api.siliconflow.cn/v1
VIBE_STICK_ASR_API_KEY=your-api-key
VIBE_STICK_ASR_MODEL=FunAudioLLM/SenseVoiceSmall
VIBE_STICK_ASR_LANGUAGE=zh
VIBE_STICK_RECORDING_USE_MAC_MIC=0
VIBE_STICK_AUTO_ENTER=0
```

`VIBE_STICK_AUTO_ENTER=0` 是安全默认值：识别文本只会进入输入框，由用户检查后提交。设置为 `1` 会在粘贴后自动按 Enter。

也可以使用本地转写命令：

```env
VIBE_STICK_TRANSCRIBE_CMD=C:\path\to\transcribe.cmd
```

## 3. 安装 Windows Bridge

```powershell
.\scripts\doctor.ps1
.\scripts\install.ps1
```

安装脚本创建当前用户的 `VibeStick Bridge` 计划任务，并立即启动。运行文件、日志和录音位于：

```text
%USERPROFILE%\.vibestick
```

首次监听 `0.0.0.0:8765` 时，Windows 防火墙可能询问是否允许访问。只允许专用网络，不要开放到公共网络。

开发时不安装计划任务：

```powershell
.\scripts\dev.ps1
```

## 4. 打开受管 Reasonix

```powershell
.\scripts\open-reasonix.ps1
```

Bridge 会启动：

```text
reasonix serve --addr 127.0.0.1:0 --auth token
```

Reasonix 只监听电脑本机，并使用随机 token。打开脚本读取本地端口和 token，然后启动浏览器。

为了让 StickS3 显示准确状态，请在这个受管 Reasonix 页面中执行任务。另一个独立的 Reasonix TUI 或 Desktop 进程不会自动把实时状态交给该 Serve 实例。

Bridge 使用以下 Reasonix 1.x 接口：

- `GET /runtime-states`
- `GET /status?runtime=1`
- `GET /pending-prompts`

状态映射：

| Reasonix | StickS3 |
|---|---|
| `idle` | `IDLE` |
| `queued` / `in_progress` / `executing` | `RUNNING` |
| `waiting_user` / pending prompt | `APPROVAL` |
| `completed` | `DONE` |
| `failed` / `protocol_failed` / `interrupted` | `ERROR` |

## 5. 编译和烧录 StickS3

打开 ESP-IDF PowerShell：

```powershell
cd firmware\sticks3
idf.py set-target esp32s3
idf.py -p COM5 build flash monitor
```

将 `COM5` 替换为设备管理器中显示的串口。

## 使用

1. 运行 `.\scripts\open-reasonix.ps1`。
2. 点击 Reasonix 输入框，使其获得焦点。
3. 长按 StickS3 正面按钮并说话。
4. 松开按钮。
5. Bridge 上传录音、执行转写，并将文本粘贴到 Reasonix。

StickS3 每两秒同步一次 Reasonix 状态。审批、完成和错误状态会显示并触发原项目已有的提醒逻辑。

## 排查

```powershell
.\scripts\doctor.ps1
```

主要日志：

```text
%USERPROFILE%\.vibestick\bridge.log
%USERPROFILE%\.vibestick\reasonix\serve.log
```

检查 Bridge：

```powershell
Invoke-RestMethod http://127.0.0.1:8765/health
Invoke-RestMethod http://127.0.0.1:8765/state
```

如果文字粘贴到错误窗口，请在松开 StickS3 按钮前确保 Reasonix 输入框仍然拥有焦点。

## 卸载

保留配置和录音：

```powershell
.\scripts\uninstall.ps1
```

同时删除 `%USERPROFILE%\.vibestick`：

```powershell
.\scripts\uninstall.ps1 -RemoveData
```
