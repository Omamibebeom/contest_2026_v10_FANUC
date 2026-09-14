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

- A 通道（PiGPIOController）與 B 通道（ArmLink）各自開一條 Modbus TCP 連線到手臂，而 PDF 把 `$SNPX_PARAM.$NUM_MODBUS` 設為 1（v1 第 17 頁 / v2 第 22 頁）。若此變數限制同時連線數，io_test.py 與 pr_test.py 各自單跑會過、但 main_contest.py 同時開兩條時會有一條失敗。建議在 Roboguide 或實機上同時執行 io_test.py 與 pr_test.py 驗證，或向 FANUC 工程師確認。
- `float_to_fanuc_regs()` 的字序（低字在前）沿用 FANUC 範例程式，需以 pr_test.py 在手臂上確認 PR[1] 數值正確。
- io_test.py 畫面與終端上的「R2 R3 R4 =」字樣沿用舊標籤，功能正常但字面已不是繼電器；因該檔與 FANUC 原包相同，暫未修改。

## 2026-09-11 — 廠商 PDF 更新為 v2（28 頁 → 33 頁），程式不需修改

用 pdfplumber 抽出兩版每頁文字逐頁比對，結果：

- **新增**「Robot 通訊設定 - 設定 I/O 配置」一節（v2 第 15–18 頁）：MENU → I/O → Digital → IN/OUT 切到 DO → CONFIG，設定 `DO[1-4] / RACK 0 / SLOT 0 / START 1`，完成後重新開機。這是手臂端把 DO[1]～DO[4] 分配出來的步驟，v1 沒有寫到。
- 第 14 頁補充：重新開機可以等全部步驟設定完再做一次；並加註「不可任意改變 IP 位置」。
- 其餘為文件修正：大綱移除沒有內容的「設定 PR[1]」項目並把 I/O 配置排在 Modbus 變數之前；v1 第 11 頁誤植的標題改為「Robot 通訊設定 - 設定 IP Address」；步驟編號「19.」改回「10.」；兩張時序表加上「辨識顏色 /取得座標 -」前綴；最後一頁改名「訊號交握畫面」並加上 DO 訊號 / 顏色代碼 / 座標位置的標註。
- **程式依賴的所有設定都沒變**（逐頁文字比對為 IDENTICAL）：Robot IP 192.168.0.1、`$NUM_MODBUS=1`、`$MODBUS_ADR=1`、`$SNPX_ASG[1]`（R[1]，ADDRESS 1）、`$SNPX_ASG[2]`（PR[1]，ADDRESS 2、SIZE 12、MULTIPLY 0）、訊號定義表、兩張交握時序表、測試程式名稱 io_test.py / pr_test.py。因此 arm_link.py、pi_gpio_controller.py 的位址常數（Coil 0～3、Holding Reg 0、Holding Reg 1～12、device_id 1）與交握流程維持不變。
- 「$NUM_MODBUS=1 是否允許兩條連線」的疑問 v2 仍未說明，維持待現場驗證。

## 2026-09-14 — 審查 GitHub 版（Omamibebeom/contest_2026_v10_FANUC）

GitHub 上 13 個檔案與 r2 交付版 byte-for-byte 相同，僅 README_student_FANUC.md 的資料夾名改為 `contest_2026_v10_FANUC`（與簡報 `git clone` 路徑一致）。

### 本次修改

無。出題者決定 GitHub 版全部不改動；Project 內 `fanuc/` 各檔與 GitHub 現版一致。

### 已知但決定不改（出題者決定）

- pi_gpio_controller.py `send()` / `send_fail()` 的背景執行緒沒有 try/except：第二次寫入（DO[2] ON）與 `all_off()` 若遇到斷線，執行緒會帶著 traceback 結束，DO[2] 不會 ON 也不會被清掉。曾做過加保護的版本並以假手臂模擬驗證通過，未採用。

- **手臂未連線時主迴圈每圈阻塞 12 秒**（實測：`ready()` 6 秒 + `poll()` 6 秒，因 pymodbus 預設 timeout 3 秒 + 重試，且每一幀重新 `connect()`）。影響：沒有手臂時 `main_contest.py --practice` 與 `io_test.py` 畫面 12 秒才更新一次、熱鍵無反應。若日後要改：`ModbusTcpClient(..., timeout=1, retries=0)` 加連線失敗後 2 秒內不重試（原型實測第一次 1 秒、之後每圈 0 秒）。
- **A 通道 DO[2] 固定保持 7 秒**（PDF v2 第 31 頁）：ChannelA 看到 DO[1]=OFF 就回 WAIT_READY，若手臂在 7 秒 hold 結束前又拉 DO[1]，會讀到仍為 ON 的 DO[2] 與上一件的 R[1]。**待向 FANUC 確認**手臂程式在下一次請求前是否等 DO[2]=OFF。`HOLD_SEC` 在學生作答區可直接改，但數字須與手臂程式一致；根本解法是「DO[1]=OFF 就提前清 DO[2]/R[1]，7 秒為上限」。
- pr_test.py 第 11 行選單路徑「DATA -> Digital Out」應為「MENU → I/O → Digital」（PDF v2 第 16 頁），且用語為 Roboguide；io_test.py 印出的「R2 R3 R4 =」為舊標籤；arm_link.poll() 在 DO[3]=OFF 時每一幀寫一次 DO[4]=False。皆不影響功能。
- 廠商 PDF 第 6 頁樹莓派網路設定的「閘道器」填 255.255.255.0（遮罩值）；直連一條線時可留空，不影響通訊。

## r3（2026-09-14）— 只修注解與印出文字，程式邏輯零變動

以 GitHub 現版為基礎。用「去掉字串常數後比較 AST」證明 10 個 .py 的程式邏輯與 GitHub 版完全相同；pyflakes 乾淨；假手臂交握模擬 22 項全過。改動：

- affine_transform.py、affine_sample_tool.py：「達明顯示板」→「FANUC 示教器」。
- io_test.py：docstring 與終端文字裡的「接線」「繼電器」「ready 腳」「R2 R3 R4 =」改為 Modbus / DO[1] / R[1] 的說法。
- main_contest.py：docstring、ChannelA/ChannelB 注解與 [a] 訊息改為 DO[1]/R[1]/DO[3]/PR[1] 的說法；「接受手臂連線」→「連上手臂 (Modbus TCP)」。
- pr_test.py：終端指引「Roboguide」→「示教器」，「DATA -> Digital Out」→「MENU → I/O → Digital，按 IN/OUT 切到 DO」（PDF v2 第 16–17 頁）。
- arm_link.py、pi_gpio_controller.py：docstring 的 PDF 檔名改為 v2。
- camera_config.py、color_detect.py、vision_tuner.py、README_student_FANUC.md、requirements_pi.txt、vision_profiles.json 未動。
