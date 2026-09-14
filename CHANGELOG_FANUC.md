# FANUC 版變更紀錄

## r2（2026-09-10）— 以 FANUC 提供的 contest2026_v10_FANUC.zip 為基礎

### 修正

- **arm_link.py `$NONE` 路徑的 NameError**：原程式在 PICK_ORDER 用完時定義了 `zero_regs` 卻寫入不存在的 `xy_regs`，例外被 `except: pass` 吞掉，結果 PR[1] 沒清 0、DO[4] 也沒拉 ON，手臂會一直等 COORD ACK。已改為正確寫入 12 個 0 並拉 DO[4]（用假手臂模擬驗證）。
- arm_link.py 頂端注解「PR[1] (Reg 20~23)」與程式實際寫入的 address 1~12 不符，已更正。
- README_student_FANUC.md 第 1 步原本叫學生執行不存在的 `DO_test.py`，已改為 `python3 arm_link.py`。

### 結構調整

- **連線設定集中**：`ROBOT_IP` / `ROBOT_PORT` / `DEVICE_ID` 只在 arm_link.py 定義，pi_gpio_controller.py 改為 `from arm_link import`。改 IP 只改一個檔。
- **test_modbus.py 併入 arm_link.py**：兩階段連線診斷（TCP 502 埠 → Modbus 讀 DO[1]~DO[4]）改寫成 `python3 arm_link.py` 的自我檢查，訊息改為樹莓派＋實機的排除步驟，並持續 10 秒顯示 DO 狀態讓學生在示教器上切換驗證。test_modbus.py 已移除。
- **pr_test.py 原樣保留**（FANUC 通訊設定 PDF 第 23 頁點名此檔）。
- **安裝pymodbus指令.txt 併入 requirements_pi.txt**：新增 `pymodbus>=3.10,<4`（程式用的 `device_id=` 參數自 pymodbus 3.10.0 起才有，3.9 以前叫 `slave=`；PDF 截圖現場版本為 3.15.0）。移除已無任何檔案 import 的 `rpi-lgpio`。安裝指令仍是 `pip install -r requirements_pi.txt --break-system-packages`。
- 主程式「階段二」那行改印手臂的 `192.168.0.1:502`（原本印的 `0.0.0.0:5000` 在 FANUC 版沒有意義）。
- Modbus 位址改用具名常數（`COIL_COORD_REQ`、`REG_PR1_START`、`REG_COLOR` …），並在 docstring 附上與 PDF `$SNPX_ASG` 設定的對照。

### 未動的檔案

main_contest.py、io_test.py、camera_config.py、color_detect.py、affine_transform.py、affine_sample_tool.py、vision_tuner.py、vision_profiles.json、pr_test.py 與 FANUC 原包完全相同。

### 待現場驗證（無法從文件確認）

- A 通道（PiGPIOController）與 B 通道（ArmLink）各自開一條 Modbus TCP 連線到手臂，而 PDF 第 17 頁把 `$SNPX_PARAM.$NUM_MODBUS` 設為 1。若此變數限制同時連線數，io_test.py 與 pr_test.py 各自單跑會過、但 main_contest.py 同時開兩條時會有一條失敗。建議在 Roboguide 或實機上同時執行 io_test.py 與 pr_test.py 驗證，或向 FANUC 工程師確認。
- `float_to_fanuc_regs()` 的字序（低字在前）沿用 FANUC 範例程式，需以 pr_test.py 在手臂上確認 PR[1] 數值正確。
- io_test.py 畫面與終端上的「R2 R3 R4 =」字樣沿用舊標籤，功能正常但字面已不是繼電器；因該檔與 FANUC 原包相同，暫未修改。
