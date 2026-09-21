# 學生手冊 —— FANUC Modbus 版比賽程式

本手冊依目前 `contest_2026_v10_FANUC_modbus` 專案程式整理。

> **先記住一句話：**
> - **A 通道：問「這是什麼顏色？」** → `DO[1] → R[1] → DO[2]`
> - **B 通道：問「這個顏色在哪裡？」** → `DO[3] → PR[1] → DO[4]`
>
> FANUC 版的 A、B 通道都使用 **Ethernet / Modbus TCP**。正式比賽不需要 Raspberry Pi GPIO ↔ Robot 的實體 Relay 配線。

---

## 0. 先進入專案資料夾

壓縮檔內目前的正式資料夾名稱是：

```bash
cd ~/Desktop/contest_2026_v10_FANUC
```

如果你自己為了版本管理把資料夾改成：

```text
contest_2026_v10_FANUC_modbus
```

則改用：

```bash
cd ~/Desktop/contest_2026_v10_FANUC_modbus
```

**只改資料夾名稱即可。程式正式檔名仍要維持：**

```text
arm_link.py
pi_gpio_controller.py
main_contest.py
io_test.py
arm_link_test_fanuc.py
```

不要把正式執行檔改成 `arm_link_modbus.py` 或 `arm_link_0917.py`，因為 `main_contest.py` 使用的是：

```python
import arm_link
```

---

## 1. 兩個通道在做什麼

| 通道 | 用途 | Robot 發出請求 | Raspberry Pi 回傳 | 完成確認 |
|---|---|---|---|---|
| **A** | 辨識放置板物件顏色 | `DO[1] COLOR_REQ` | `R[1]` 顏色代碼 | `DO[2] COLOR_ACK` |
| **B** | 取得隨機位置板物件座標 | `DO[3] COORD_REQ` | `PR[1]` X/Y 座標 | `DO[4] COORD_ACK` |

### A 通道

Robot 把物件夾到固定辨識位置後：

```text
Robot DO[1] ON
      ↓
Raspberry Pi 投票辨識 3 秒
      ↓
寫 R[1] 顏色代碼
      ↓
再等 1 秒
      ↓
Raspberry Pi 將 DO[2] ON
      ↓
Robot 讀取 R[1]
      ↓
Robot 將 DO[1] OFF
```

目前預設：

```text
red   → R[1] = 1
blue  → R[1] = 2
green → R[1] = 3
失敗  → R[1] = 7，DO[2] 不會 ON
```

### B 通道

主程式啟動時會先拍一張隨機位置板快照，把所有物件的像素位置換算成 Robot X/Y。

Robot 要一件座標時：

```text
Robot DO[3] ON
      ↓
arm_link.py 轉成 GET
      ↓
main_contest.py 依 PICK_ORDER 找下一件
      ↓
寫入 PR[1]
      ↓
Raspberry Pi 將 DO[4] ON
      ↓
Robot 讀取 PR[1]
      ↓
Robot 將 DO[3] OFF
      ↓
Raspberry Pi 將 DO[4] OFF
```

**每次新的 B 通道請求都必須讓 `DO[3]` 經過 OFF → ON。** 不能一直保持 ON，否則不會產生下一次 GET。

---

## 2. FANUC Modbus 對照

目前 `arm_link.py` 的設定：

| FANUC 資料 | Modbus | Pymodbus 位址 | 用途 |
|---|---|---:|---|
| `DO[1]` | Coil | 0 | A 通道 COLOR_REQ |
| `DO[2]` | Coil | 1 | A 通道 COLOR_ACK |
| `DO[3]` | Coil | 2 | B 通道 COORD_REQ |
| `DO[4]` | Coil | 3 | B 通道 COORD_ACK |
| `R[1]` | Holding Register | 0 | A 通道顏色代碼 |
| `PR[1]` | Holding Registers | 1～12 | B 通道 X/Y/Z/W/P/R |

Robot 端依廠商通訊設定文件確認：

```text
Port#1 IP                    192.168.0.1
$SNPX_PARAM.$NUM_MODBUS      1
$SNPX_PARAM.$MODBUS_ADR      1
DO[1-4]                      RACK 0 / SLOT 0 / START 1
$SNPX_ASG[1]                 R[1], ADDRESS 1
$SNPX_ASG[2]                 PR[1], ADDRESS 2, SIZE 12, MULTIPLY 0
```

修改 Robot 通訊設定後依文件要求重新開機。

---

## 3. 為什麼 `pi_gpio_controller.py` 還有 Relay 程式？

這是 FANUC Modbus 版最容易混淆的地方。

`pi_gpio_controller.py` 是四家共用的母版，因此檔案裡仍保留：

```text
GPIO 17 / 27 / 22 / 23 → R1～R4 Relay
GPIO 26                 → READY
```

也保留原本的：

```python
PiGPIOController.ready()
PiGPIOController.send()
PiGPIOController.send_fail()
PiGPIOController.all_off()
PiGPIOController.cleanup()
```

但是 FANUC 的 `arm_link.py` 載入時會把這些方法換成 Modbus 版本：

```text
原本 ready()     → 讀 Raspberry Pi GPIO 26
FANUC ready()    → Modbus 讀 DO[1]

原本 send()      → 控制 R1～R4 Relay
FANUC send()     → Modbus 寫 R[1]、DO[2]
```

也就是：

```text
main_contest.py
      │
      │ 呼叫 PiGPIOController.ready() / send()
      ▼
PiGPIOController 共同介面
      │
      │ FANUC arm_link.py 執行時替換方法
      ▼
Modbus TCP
      │
      ▼
FANUC Robot
```

因此：

- `pi_gpio_controller.py` **仍保留實體配線程式碼**。
- FANUC 的 `main_contest.py` 正式執行時 **A 通道實際使用 Modbus TCP，不使用 Relay**。
- A、B 兩個通道共用 `arm_link.py` 裡同一個 Modbus TCP client，並用 lock 排隊讀寫。
- FANUC 比賽系統只需要 Ethernet 網路連線即可完成 A、B 通道交握。

### `io_test.py` 的特別注意事項

目前 `io_test.py` 會先建立 `PiGPIOController()`，之後才透過 `main_contest` 載入 `arm_link.py` 完成方法替換。

因此在真正的 Raspberry Pi 上，如果 GPIO 函式庫存在，**啟動 `io_test.py` 的早期仍可能先初始化一次 GPIO 腳位**；後續 `ready()`、`send()`、`cleanup()` 才會改走 Modbus。

FANUC 不需要接 Relay 才能測試，但若 GPIO 17、27、22、23 已接到其他硬體，測試前要特別留意。

---

## 4. 學生主要要設定的四個地方

| # | 檔案 | 設定 | 用途 |
|---|---|---|---|
| 1 | `affine_transform.py` | `PIXELS` | 相機像素取樣點 |
| 2 | `affine_transform.py` | `ARMS` 與 `fit()` | Robot X/Y 與仿射轉換公式 |
| 3 | `main_contest.py` | `PICK_ORDER` | B 通道要求座標的顏色順序 |
| 4 | `pi_gpio_controller.py` | `IO_CODES` / `FAIL_CODE` | A 通道顏色代碼 |

### 顏色名稱一定要一致

下面三個地方必須完全相同，而且建議全部小寫：

```text
vision_profiles.json
main_contest.py → PICK_ORDER
pi_gpio_controller.py → IO_CODES
```

例如：

```text
red
blue
green
```

`Red`、`RED`、`red ` 都是不同的名稱。

### PICK_ORDER 範例

```python
PICK_ORDER = ["red", "blue", "green"]
```

表示 B 通道：

```text
第 1 次 DO[3] ON → 回 red 的座標
第 2 次 DO[3] ON → 回 blue 的座標
第 3 次 DO[3] ON → 回 green 的座標
```

同色兩件可以重複：

```python
PICK_ORDER = ["red", "red", "blue"]
```

---

## 5. 第一次安裝套件

樹莓派先接可上網的 Wi-Fi：

```bash
pip install -r requirements_pi.txt --break-system-packages
```

目前 requirements 包含：

```text
numpy>=2.0.2
opencv-python>=4.11.0.86
rpi-lgpio（ARM Raspberry Pi）
pymodbus>=3.10,<4
```

FANUC `arm_link.py` 使用 `device_id=`，因此不要任意把 pymodbus 換成較舊版本。

---

## 6. 賽前準備：照這個順序做

### Step 0：確認網路

範例：

```text
FANUC Robot     192.168.0.1
Raspberry Pi    192.168.0.50
Subnet Mask     255.255.255.0
Modbus TCP      Port 502
```

測試：

```bash
ping 192.168.0.1
```

有 Reply 再繼續。

---

### Step 1：調整每個顏色 HSV

```bash
python3 vision_tuner.py
```

將物件放到鏡頭下，調整 H / S / V 範圍，使 mask 主要只留下目標物件。

常用按鍵：

```text
s = 儲存目前顏色
n = 載入已存顏色修改
q = 離開
```

顏色名稱請使用和 `PICK_ORDER`、`IO_CODES` 相同的小寫名稱。

---

### Step 2：取得像素 ↔ Robot 座標取樣點

```bash
python3 affine_sample_tool.py
```

建議流程：

```text
1. 放一件 B 通道物件
2. 畫面偵測到中心十字
3. SPACE 鎖定像素位置
4. Jog Robot 夾爪尖端到相同物理位置
5. 按 c
6. 輸入示教器 User Frame 的 X,Y
7. 換位置重複
```

取樣建議：

```text
至少 3 點
不可共線
建議四角 + 中間，共 5 點以上
盡量鋪滿實際使用區域
```

按 `p` 會印出：

```python
PIXELS = [...]
ARMS = [...]
```

把兩份資料抄進 `affine_transform.py`。

---

### Step 3：驗證仿射轉換

```bash
python3 affine_transform.py
```

正常會印出：

```text
X = ...*cx + ...*cy + ...
Y = ...*cx + ...*cy + ...
```

若出現：

```text
LinAlgError: Singular matrix
```

通常代表：

```text
取樣點太少
取樣點共線
或作答公式寫錯
```

---

### Step 4：填 `PICK_ORDER`、`IO_CODES`

`main_contest.py`：

```python
PICK_ORDER = ["red", "blue", "green"]
```

`pi_gpio_controller.py`：

```python
IO_CODES = {
    "red":   (0, 0, 1),
    "blue":  (0, 1, 0),
    "green": (0, 1, 1),
}

FAIL_CODE = (1, 1, 1)
```

FANUC 版會將三個 bit 轉成：

```text
R[1] = R2×4 + R3×2 + R4
```

---

### Step 5：測 FANUC Modbus 基本通訊

```bash
python3 arm_link.py
```

正常會看到：

```text
=== arm_link 連線檢查: 192.168.0.1:502 ===
[1/2] TCP 連線 ... OK
[2/2] Modbus 讀 DO[1]~DO[4] ... OK
```

接著程式會連續顯示：

```text
DO[1]=OFF  DO[2]=OFF  DO[3]=OFF  DO[4]=OFF
```

在示教器切換 DO[1]～DO[4]，Raspberry Pi 顯示必須跟著變。

---

### Step 6：測 A 通道

```bash
python3 io_test.py
```

按鍵：

```text
1～9 = 直接送 IO_CODES 第 1～9 個顏色
f    = 送失敗碼
0    = 清除訊號
r    = 把目前鏡頭看到的顏色立即送出
q    = 離開
```

確認 FANUC：

```text
R[1] 正確
DO[2] 正常 ON/OFF
```

要測和比賽相同的完整 A 流程：

```text
1. 把物件放到固定辨識位置
2. FANUC DO[1] ON
3. Raspberry Pi 投票 3 秒
4. R[1] 寫入顏色
5. 約第 4 秒 DO[2] ON
6. Robot 讀 R[1]
7. Robot DO[1] OFF
```

目前成功訊號會讓 `DO[2]` 保持 `HOLD_SEC = 7` 秒後自動清除。

辨識失敗時：

```text
R[1] = 7
DO[2] 不會 ON
FAIL_HOLD_SEC = 10 秒後 R[1] 清 0
```

依目前 `docs/a_channel_flow.txt`，Robot TP 等 `DO[2]` 可使用約 8 秒 timeout，逾時後再讀 `R[1]` 判斷是否為 7。

---

### Step 7：測 B 通道

```bash
python3 arm_link_test_fanuc.py
```

這支測試：

```text
不開相機
不做顏色辨識
不做仿射轉換
只測 DO[3] / DO[4] / PR[1]
```

測試：

```text
1. DO[3] OFF、DO[4] OFF
2. FANUC DO[3] ON
3. Raspberry Pi 寫 FAKE_TARGETS 下一組 X/Y 到 PR[1]
4. Raspberry Pi DO[4] ON
5. 在 DATA → Position Reg 確認 PR[1]
6. FANUC DO[3] OFF
7. Raspberry Pi DO[4] OFF
8. 再次 DO[3] ON 測下一組
```

`FAKE_TARGETS` 必須填安全可達位置；若 Robot TP 會實際用 PR[1] 移動，測試座標會真的被執行。

---

## 7. 第一次完整整合測試

A、B 單獨測試都成功後：

```bash
python3 main_contest.py --practice
```

### 啟動時的順序非常重要

先：

```text
1. B 通道物件全部放好
2. Robot 移出相機畫面
3. 相機位置固定，不再移動
4. 執行 main_contest.py --practice
```

程式會先進入：

```text
[main] 階段一: 拍快照 (手臂勿在畫面內)
```

並印出：

```text
[b] 快照完成, 共 3 件:
    #0 red      像素(...) → 手臂(...)
    #1 blue     像素(...) → 手臂(...)
    #2 green    像素(...) → 手臂(...)
```

先確認：

```text
物件數量正確
顏色正確
換算出的 X/Y 合理
```

之後會看到：

```text
[arm] 已連上 FANUC Modbus 192.168.0.1:502
[main] === 階段二: 可以按手臂了 (192.168.0.1:502)  [練習模式] ===
```

**一定要看到「階段二」後，才啟動 Robot 比賽程式。**

### 練習模式畫面按鍵

```text
r = 重新拍 B 通道快照
c = B 通道取用順序歸零
q = 離開
```

`--practice` 模式下，`PICK_ORDER` 用完會自動從頭再來。

---

## 8. `main_contest.py` 同時怎麼跑 A、B？

主迴圈概念是：

```python
a.step(frame)

for cmd in link.poll():
    link.send(b.handle(cmd))
```

也就是程式每一圈同時：

```text
A：看 DO[1] 是否要求顏色辨識
B：看 DO[3] 是否要求下一件座標
```

所以正式比賽不需要同時開：

```text
io_test.py
arm_link_test_fanuc.py
```

這兩支只用來賽前測試。

正式比賽只執行：

```bash
python3 main_contest.py --no-ui
```

---

## 9. Robot TP 交握重點

### A 通道 TP 概念

```text
移到固定辨識位置
↓
DO[1] = ON
↓
WAIT DO[2] = ON（依目前流程可設約 8 秒 timeout）
↓
成功：讀 R[1]
失敗 timeout：讀 R[1] 是否為 7
↓
DO[1] = OFF
↓
下一件前確認 DO[2] 已回 OFF
```

`DO[1]` 一定要放回 OFF，因為 `ChannelA` 會進入 `WAIT_RELEASE`，只有看到 DO[1] OFF 才接受下一件。

### B 通道 TP 概念

```text
DO[3] = ON
↓
WAIT DO[4] = ON
↓
讀 PR[1]
↓
DO[3] = OFF
↓
WAIT DO[4] = OFF
↓
下一次請求
```

目前 Python 寫入 PR[1]：

```text
X = 視覺換算 X
Y = 視覺換算 Y
Z = 0
W = 0
P = 0
R = 0
```

因此 Python 目前主要提供 **X/Y 平面座標**。Robot 真正運動時需要的 Z 高度與姿態，請由 TP 程式依實際治具、User Frame 與夾取方式安全處理，不要未確認就直接把收到的 PR[1] 當完整六軸運動姿態使用。

如果 `PICK_ORDER` 已用完，正式模式會：

```text
PR[1] 全部寫 0
DO[4] ON
```

Robot 可以用 `X=0、Y=0` 判斷「沒有下一件」。

---

## 10. 正式比賽

確認前面測試都通過後：

```text
1. 確認網路正常
2. 確認相機固定
3. B 通道物件放好
4. Robot 移出相機畫面
5. 啟動 Raspberry Pi 主程式
6. 等「階段二」
7. 再啟動 FANUC TP 比賽程式
```

正式指令：

```bash
python3 main_contest.py --no-ui
```

正常啟動範例：

```text
[main] 顏色: ['red', 'blue', 'green']  夾取順序: ['red', 'blue', 'green'] ...
[io] a 通道走 Modbus: DO[1] → R[1] / DO[2] (192.168.0.1:502)
[camera] index 0 開啟, 解析度 1280x720
[main] 階段一: 拍快照 (手臂勿在畫面內)
[b] 快照完成, 共 3 件:
    ...
[arm] 已連上 FANUC Modbus 192.168.0.1:502
[main] === 階段二: 可以按手臂了 (192.168.0.1:502) ===
```

比賽結束後：

```text
Ctrl + C
```

---

## 11. 常見問題

| 現象 | 可能原因 | 處理方式 |
|---|---|---|
| `ping` 不到 Robot | IP / Subnet / 網路線 | 確認 Pi 與 Robot 同網段 |
| TCP 502 逾時 | 網路或 Robot IP 錯 | 先確認 `ping` 與 `ROBOT_IP` |
| TCP 被拒絕 | Modbus server 未開 | 檢查 `$NUM_MODBUS=1`，修改後重新開機 |
| `arm_link.py` 讀不到 DO | I/O mapping 錯 | 確認 `DO[1-4] / RACK 0 / SLOT 0 / START 1` |
| `ModuleNotFoundError: pymodbus` | 套件沒裝 | 重新執行 requirements 安裝 |
| `read_coils() got an unexpected keyword argument...` | pymodbus 太舊 | 使用 `pymodbus>=3.10,<4` |
| A 通道沒有 `[a] 收到 ready` | Pi 沒讀到 DO[1] | 先跑 `python3 arm_link.py` 看 DO[1] |
| A 有辨識但 DO[2] 不 ON | 判為失敗或 R[1] 寫入失敗 | 看終端 `[a]`、`[io]` 訊息 |
| A 一直辨識不到 | HSV / min_area / 物件位置 | 用 `vision_tuner.py`、`io_test.py` 重調 |
| B DO[3] ON 沒反應 | DO[4] 尚未 OFF、DO[3] 沒重新 OFF→ON、mapping 問題 | 先用 `arm_link_test_fanuc.py` 重測 |
| DO[4] ON 但 PR[1] 錯 | SNPX PR mapping / word order | 確認 ADDRESS 2 / SIZE 12 / MULTIPLY 0 |
| `[b] 注意: PICK_ORDER 有 ... 但快照沒有` | 顏色名稱錯或快照沒辨識到 | 檢查三處名稱、HSV、物件是否被遮住 |
| `LinAlgError: Singular matrix` | 取樣不足 / 共線 / 公式錯 | 重新取點並驗算 affine |
| 相機解析度不是 1280×720 | Camera mode 不一致 | 修正相機設定後重新取 affine 點位 |
| B 座標整體偏掉 | 相機位置改變 | 相機固定後重新取 affine 點位 |
| PICK_ORDER 用完一直回 0 | 正式模式正常結束 | 練習時改用 `--practice` |

---

## 12. 比賽前快速檢查表

- [ ] Raspberry Pi 與 FANUC Robot `ping` 正常
- [ ] TCP Port 502 正常
- [ ] `python3 arm_link.py` 可看到 DO[1]～DO[4] 正確變化
- [ ] `io_test.py` 可完成 `DO[1] → R[1] → DO[2]`
- [ ] `arm_link_test_fanuc.py` 可完成 `DO[3] → PR[1] → DO[4]`
- [ ] `vision_profiles.json` 顏色辨識正確
- [ ] `PIXELS` / `ARMS` 已重新取樣並驗算
- [ ] `PICK_ORDER` 正確
- [ ] `IO_CODES` 正確
- [ ] 三處顏色名稱完全一致
- [ ] 相機解析度 1280×720
- [ ] 相機位置固定
- [ ] B 通道快照時 Robot 已移出畫面
- [ ] `main_contest.py --practice` 已完成 A+B 整合測試
- [ ] 正式比賽使用 `python3 main_contest.py --no-ui`
- [ ] 看到「階段二」後才啟動 Robot TP 程式

---

## 13. 最重要的五句話

> **1. A 通道：`DO[1] ON → 辨識顏色 → R[1] → DO[2] ON → Robot 讀完後 DO[1] OFF`。**

> **2. B 通道：`DO[3] ON → PR[1] X/Y → DO[4] ON → Robot 讀完後 DO[3] OFF`。**

> **3. FANUC A、B 都走同一條 Ethernet / Modbus TCP，不需要 Relay 配線。**

> **4. `pi_gpio_controller.py` 的實體 GPIO 程式仍保留，但 FANUC `arm_link.py` 會在執行時把主要方法替換成 Modbus 版本。**

> **5. 正式比賽一定要等主程式顯示「階段二：可以按手臂了」後，才啟動 Robot。**
