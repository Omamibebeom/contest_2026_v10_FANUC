# FANUC 學生手冊 —— 比賽要改什麼、要做什麼

> 本手冊為 FANUC Robot + Raspberry Pi + Modbus TCP 版本。  
> 核心概念：**A 通道判斷「這是什麼顏色」；B 通道判斷「這個顏色在哪裡」。**

所有 Python 指令都在 Raspberry Pi 終端機執行。先進入競賽資料夾：

```bash
cd ~/Desktop/contest_2026_v10_FANUC
```

> 若實際資料夾名稱不同，請依現場路徑修改。

第一次使用前先裝套件（樹莓派要先接上可上網的 Wi-Fi，裝完再切回有線連手臂）：

```bash
pip install -r requirements_pi.txt --break-system-packages
```

---

## 零、先弄清楚系統架構

### 0-1 兩個通道

| 通道 | 物件位置 | FANUC Robot 做什麼 | Raspberry Pi 做什麼 | 回傳資料 |
|---|---|---|---|---|
| **A：顏色辨識** | 放置板，位置固定 | 夾起指定物件並移至相機辨識位置 | 辨識物件顏色 | `R[1]` 顏色代碼 |
| **B：座標辨識** | 隨機位置放置板 | 發出座標請求，取得位置後前往夾取 | 開場拍照，辨識物件並計算 Robot X/Y 座標 | `PR[1]` 目標座標 |

一句話記住：

- **A 通道：這是什麼顏色？**
- **B 通道：這個顏色在哪裡？**

---

## 一、FANUC ↔ Raspberry Pi Modbus TCP 訊號

### 1-1 訊號定義

| 訊號名稱 | FANUC 訊號 | Modbus | Pymodbus Address | 功能說明 |
|---|---|---|---:|---|
| **顏色請求 `COLOR_REQ`** | `DO[1]` | Coil | `0` | Robot 到達辨識位置後設為 ON，向 Raspberry Pi 發出顏色辨識請求 |
| **顏色確認 `COLOR_ACK`** | `DO[2]` | Coil | `1` | Raspberry Pi 完成辨識並寫入 `R[1]` 後設為 ON，表示顏色資料已準備完成 |
| **顏色代碼 `COLOR_DATA`** | `R[1]` | Holding Register | `0` | 儲存辨識結果，例如 Red=1、Blue=2、Green=3 |
| **座標請求 `COORD_REQ`** | `DO[3]` | Coil | `2` | Robot 需要下一個物件座標時設為 ON |
| **座標確認 `COORD_ACK`** | `DO[4]` | Coil | `3` | Raspberry Pi 完成 `PR[1]` 寫入後設為 ON，表示座標資料已準備完成 |
| **座標資料 `COORD_DATA`** | `PR[1]` | Holding Registers | 起始 `1`* | 儲存目標位置；X、Y 為辨識座標，Z/W/P/R 設為 0 |

\* 本文件以 **FANUC Holding Register 起始位址 2** 為目前設定；Pymodbus 為 0-based，因此 Python 起始位址為 `address=1`。

### 1-2 A 通道：顏色辨識交握

```text
FANUC Robot                          Raspberry Pi

COLOR_REQ ON  ────────────────────►  開始顏色辨識
                                      │
                                      ├─ 寫入 R[1] = 顏色代碼
                                      │
COLOR_ACK ON  ◄───────────────────────┘

Robot 讀取 R[1]
      │
COLOR_REQ OFF ────────────────────►

COLOR_ACK OFF ◄────────────────────
```

建議交握順序：

1. Robot 到達辨識位置。
2. Robot 將 `DO[1:COLOR_REQ]` 設為 ON。
3. Raspberry Pi 進行顏色辨識。
4. Raspberry Pi 將顏色代碼寫入 `R[1]`。
5. 寫入成功後，Raspberry Pi 將 `DO[2:COLOR_ACK]` 設為 ON。
6. Robot 等待 `COLOR_ACK=ON` 後讀取 `R[1]`。
7. Robot 將 `COLOR_REQ` 設為 OFF。
8. Raspberry Pi 將 `COLOR_ACK` 設為 OFF，完成一次交握。

### 1-3 B 通道：座標辨識交握

```text
FANUC Robot                          Raspberry Pi

COORD_REQ ON  ────────────────────►  取得下一個目標座標
                                      │
                                      ├─ 寫入 PR[1]
                                      │
COORD_ACK ON  ◄───────────────────────┘

Robot 使用 PR[1]
      │
COORD_REQ OFF ────────────────────►

COORD_ACK OFF ◄────────────────────
```

建議交握順序：

1. Robot 將 `DO[3:COORD_REQ]` 設為 ON。
2. Raspberry Pi 收到請求後，依 `PICK_ORDER` 找到下一個目標。
3. Raspberry Pi 將目標座標寫入 `PR[1]`。
4. 寫入成功後，將 `DO[4:COORD_ACK]` 設為 ON。
5. Robot 等待 `COORD_ACK=ON` 後使用 `PR[1]`。
6. Robot 將 `COORD_REQ` 設為 OFF。
7. Raspberry Pi 將 `COORD_ACK` 設為 OFF，準備下一次請求。

---

## 二、PR[1] 座標資料格式

若 FANUC 端以 32-bit REAL 方式映射完整 `PR[1]`，每個座標分量使用 2 個 Holding Registers。

| PR[1] 分量 | FANUC Holding Register | Pymodbus Address | 本競賽用途 |
|---|---:|---:|---|
| X | 2～3 | 1～2 | 視覺計算的 X |
| Y | 4～5 | 3～4 | 視覺計算的 Y |
| Z | 6～7 | 5～6 | `0.0` |
| W | 8～9 | 7～8 | `0.0` |
| P | 10～11 | 9～10 | `0.0` |
| R | 12～13 | 11～12 | `0.0` |

因此一筆完整座標應為：

```text
PR[1]
X = 視覺計算值
Y = 視覺計算值
Z = 0.0
W = 0.0
P = 0.0
R = 0.0
```

> 注意：以上格式必須與 FANUC 端的 Modbus / `$SNPX_ASG` 映射設定一致。若只映射 X、Y，則不要直接寫 12 個 Registers。

---

## 三、學生要改的四個地方

其他通訊底層程式原則上不要任意修改。

| # | 檔案 | 修改位置 | 要填什麼 | 如何確認 |
|---:|---|---|---|---|
| 1 | `affine_transform.py` | 作答區 1：`PIXELS` / `ARMS` | 相機像素與 FANUC Robot 對應的 X/Y 取樣點，至少 3 點、建議 5 點 | `python3 affine_transform.py` 能印出 X/Y 轉換公式 |
| 2 | `affine_transform.py` | 作答區 2：`fit()` | 依題目公式完成 Aᵀ、(AᵀA)⁻¹、T₁、T₂ 與 2×3 矩陣 | 用取樣點代回後，應接近原 Robot X/Y |
| 3 | `main_contest.py` | `PICK_ORDER` | 隨機位置放置板的夾取顏色順序；同色兩件就寫兩次 | 啟動主程式時沒有顏色缺失警告 |
| 4 | `pi_gpio_controller.py` | `IO_CODES` / `FAIL_CODE` | 顏色名稱對應 `R[1]` 的數字代碼 | 透過 A 通道測試確認 `R[1]` 正確 |

顏色名稱必須保持一致：

```text
vision_profiles.json
PICK_ORDER
IO_CODES
```

三個地方的名稱要 **完全相同、全部小寫**，例如：

```text
red
blue
green
```

`Red`、`RED`、`red ` 都視為不同名稱。

---

## 四、賽前準備

### 第 0 步：確認 FANUC 網路

確認 Raspberry Pi 與 FANUC Robot 在同一子網。

範例：

```text
FANUC Robot      192.168.0.1
Raspberry Pi     192.168.0.50
Subnet Mask      255.255.255.0
Modbus TCP Port  502
```

從 Raspberry Pi 測試：

```bash
ping 192.168.0.1
```

若能收到 Reply，再進行 Modbus 測試。

> Robot IP 只需與 `arm_link.py` 頂端的 `ROBOT_IP` 一致（`pi_gpio_controller.py` 會從那裡讀，不用另外改）。

### 第 1 步：測試 Modbus DO 通訊

執行：

```bash
python3 arm_link.py
```

程式會依序做兩件事，任何一階段失敗都會直接印出該檢查什麼：

1. TCP 連線：Raspberry Pi 能不能連上 Robot 的 Port 502。
2. Modbus 讀取：讀 `DO[1]～DO[4]`，接著每 0.5 秒重讀一次、持續 10 秒。

這 10 秒內到示教器 I/O → Digital Out 切換 DO，終端機的 ON/OFF 要跟著變。看到「通訊正常」才進下一步。

若 TCP 連得上，但 Coil 無法讀取，優先檢查 FANUC Modbus I/O Mapping。

### 第 2 步：測試 PR[1] 寫入

執行：

```bash
python3 pr_test.py
```

測試流程：

1. FANUC 將 `DO[3:COORD_REQ]` 設為 ON。
2. Python 偵測到請求。
3. 測試程式寫入指定 X/Y。
4. 確認 FANUC `PR[1]` 顯示正確。
5. 確認 `DO[4:COORD_ACK]` 變為 ON。
6. 將 `DO[3]` OFF，確認 `DO[4]` 隨後 OFF。

若 `DO[4]` 正常 ON，但 `PR[1]` 數值錯誤，檢查：

- Python `write_registers()` 起始位址
- FANUC PR[1] Holding Register 起始位址
- `$SIZE`
- `$VAR_NAME`
- `$MULTIPLY`
- 32-bit REAL / Integer 編碼方式

### 第 3 步：調整顏色

執行：

```bash
python3 vision_tuner.py
```

操作：

1. 將物件放到鏡頭下。
2. 拖曳 H、S、V 範圍。
3. 讓 mask 中只有目標物件為白色，背景盡量為黑色。
4. 按 `s` 儲存。
5. 輸入顏色名稱，必須為小寫，例如 `red`。
6. 每個比賽會使用的顏色都要設定。

常用按鍵：

```text
s = 儲存顏色
n = 載入下一個已存顏色
q = 離開
```

### 第 4 步：取得像素 ↔ FANUC Robot 座標

執行：

```bash
python3 affine_sample_tool.py
```

操作流程：

1. 在隨機位置放置板放置基準物件。
2. 畫面偵測到物件中心後，按 `SPACE` 鎖定像素座標。
3. Jog FANUC Robot，使夾爪 TCP 對準同一個實際位置。
4. 讀取 FANUC 示教器上目前 User Frame 下的 X、Y。
5. 按 `c` 輸入 X、Y。
6. 換另一個位置重複操作。

建議：

- 至少 3 點。
- 建議 5 點以上。
- 點位盡量分布在工作區四角與中央。
- 所有點不可排成同一直線。

完成後按：

```text
p
```

將印出的：

```python
PIXELS = [...]
ARMS = [...]
```

抄入 `affine_transform.py` 作答區 1。

### 第 5 步：完成座標轉換公式並驗算

執行：

```bash
python3 affine_transform.py
```

正常應看到：

```text
X = ...*cx + ...*cy + ...
Y = ...*cx + ...*cy + ...
```

能印出六個轉換參數，代表矩陣計算可執行。

再以其中一個取樣像素代入 `pixel_to_arm()`，結果應接近當初量測的 FANUC X/Y。

### 第 6 步：填寫 `PICK_ORDER` 與 `IO_CODES`

`main_contest.py`：

```python
PICK_ORDER = ["red", "blue", "green"]
```

代表 B 通道依序提供：

```text
red → blue → green
```

如果同一顏色需要夾兩件，例如：

```python
PICK_ORDER = ["red", "red", "blue"]
```

`pi_gpio_controller.py`：

```python
IO_CODES = {
    "red": 1,
    "blue": 2,
    "green": 3,
}

FAIL_CODE = 99
```

代表 A 通道辨識完成後：

```text
red   → R[1] = 1
blue  → R[1] = 2
green → R[1] = 3
```

### 第 7 步：測試 A 通道顏色回傳

執行：

```bash
python3 io_test.py
```

確認完整流程：

```text
DO[1] COLOR_REQ ON
        ↓
Raspberry Pi 顏色辨識
        ↓
R[1] 寫入正確顏色代碼
        ↓
DO[2] COLOR_ACK ON
```

Robot 端確認 `R[1]` 的數值符合 `IO_CODES`。

### 第 8 步：練習跑完整流程

執行：

```bash
python3 main_contest.py --practice
```

練習模式會開啟畫面，顯示快照辨識結果。

畫面熱鍵：

```text
r = 重新拍攝 B 通道快照
c = B 通道取用順序歸零
q = 離開
```

確認：

- A 通道顏色判斷正確。
- B 通道物件數量與顏色正確。
- `R[1]` 顏色代碼正確。
- `PR[1]` 座標正確。
- 四個 REQ/ACK 訊號能完成一次完整交握。

---

## 五、比賽當天

依序操作：

1. 確認 FANUC Robot 與 Raspberry Pi 網路正常。
2. 確認相機固定，位置沒有被移動。
3. 將 Robot 移到相機畫面外。
4. 執行正式程式：

```bash
python3 main_contest.py --no-ui
```

5. 觀察終端機，確認 B 通道快照完成：

```text
[camera] index 0 開啟, 解析度 1280x720
[b] 快照完成, 共 3 件:
    #0 red ...
    #1 blue ...
    #2 green ...
[main] === 階段二: 可以按手臂了 ===
```

6. **看到「階段二：可以按手臂了」後，才啟動 FANUC Robot 比賽程式。**
7. 比賽中不要移動相機、不要修改 Python 程式。
8. 比賽結束後按：

```text
Ctrl + C
```

結束 Raspberry Pi 程式。

---

## 六、常見錯誤與排除方式

| 現象 / 錯誤 | 可能原因 | 處理方式 |
|---|---|---|
| `LinAlgError: Singular matrix` | 取樣點太少、共線，或轉換公式錯誤 | 重新取樣；至少 3 點且不要共線 |
| `ValueError: matmul ... mismatch` | `PIXELS` 與 `ARMS` 數量不同 | 確認兩份清單點數與順序 |
| 相機無法開啟 | 相機未接好或被其他程式占用 | 關閉 tuner / sample tool，重新插拔相機 |
| 相機解析度不是 1280×720 | 相機設定或裝置不同 | 使用原本相機與相同解析度 |
| 找不到 `vision_profiles.json` | 尚未儲存顏色設定 | 執行 `vision_tuner.py` |
| `PICK_ORDER` 顏色不存在 | 顏色名稱不同或快照沒辨識到 | 統一小寫名稱；重新拍攝 |
| `ping` Robot 失敗 | IP / Subnet / 網線設定錯誤 | 確認 Raspberry Pi 與 Robot 同網段 |
| TCP 502 連線失敗 | Robot Modbus TCP 未啟用或 IP 錯 | 檢查 Robot Modbus 設定與 Port 502 |
| DO 能讀但 `pr_test.py` 無反應 | `DO[3]` Mapping 或 Coil Address 錯誤 | 確認 `DO[3] ↔ Coil 2` |
| `COORD_ACK` ON，但 PR[1] 沒有正確數值 | Holding Register 起始位址或格式錯誤 | 確認 FANUC Address 2 ↔ Python `address=1`，並檢查 PR 映射格式 |
| PR[1] 數值很大或完全錯誤 | Float / Integer、Word order 或 `$MULTIPLY` 不一致 | 確認 FANUC 與 Python 使用相同資料格式 |
| `read_coils() got an unexpected keyword argument ...` | Pymodbus 版本太舊（程式需要 3.10 以上） | 用 `pip install -r requirements_pi.txt --break-system-packages` 重裝，不要自行改版本 |
| `ModuleNotFoundError: No module named 'pymodbus'` | 還沒裝套件 | 執行上面的 `pip install -r ...` |
| Robot 一直等待 ACK | Raspberry Pi 未完成資料寫入，或 ACK Mapping 錯誤 | 先確認 R[1]/PR[1] 寫入成功，再檢查 DO[2]/DO[4] |
| B 通道回傳不到目標 | `PICK_ORDER` 已用完或指定顏色不存在 | 檢查 `PICK_ORDER` 與快照辨識結果 |

---

## 七、五個絕對不要

1. **相機移動後不重新取點。**  
   相機位置只要改變，原本像素 ↔ Robot 座標轉換就失效。

2. **主程式啟動拍快照時，Robot 留在畫面內。**  
   Robot 可能遮住物件，導致 B 通道快照辨識錯誤。

3. **三個地方的顏色名稱不一致。**  
   `vision_profiles.json`、`PICK_ORDER`、`IO_CODES` 必須完全相同。

4. **沒有確認 PR Mapping 就修改 Register Address。**  
   FANUC 位址與 Pymodbus 位址相差 1，修改時一定要同步確認。

5. **比賽前自行更新 Pymodbus。**  
   不同版本的參數名稱可能不同，可能造成原本可用的程式無法執行。

---

## 八、比賽前快速檢查表

開始比賽前逐項確認：

- [ ] FANUC Robot 與 Raspberry Pi 可以互相通訊
- [ ] Modbus TCP Port 502 正常
- [ ] `DO[1] COLOR_REQ` 正常
- [ ] `DO[2] COLOR_ACK` 正常
- [ ] `DO[3] COORD_REQ` 正常
- [ ] `DO[4] COORD_ACK` 正常
- [ ] `R[1]` 顏色代碼正確
- [ ] `PR[1]` X/Y 座標正確
- [ ] PR[1] 的 Z/W/P/R 為 0（若使用完整 PR 映射）
- [ ] 相機解析度為 1280×720
- [ ] 相機位置沒有改變
- [ ] HSV 顏色設定完成
- [ ] 仿射轉換驗算正常
- [ ] `PICK_ORDER` 正確
- [ ] Robot 已移出 B 通道快照畫面
- [ ] 終端機已顯示「階段二：可以按手臂了」

---

## 九、最重要的三句話

> **A 通道：Robot DO[1]=ON 要顏色 → 樹莓派 寫 R[1] → DO[2]=ON 顏色送出確認 → Robot DO[1]=OFF 結束 。**

> **B 通道：Robot DO[3]=ON 要座標 → Pi 寫 PR[1] → DO[4]=ON 座標送出確認 → Robot DO[3]=OFF 結束 。**

> **資料先寫成功，再送 ACK。**
