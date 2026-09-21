"""
arm_link_test_fanuc.py —— 只測「手臂 ↔ 樹莓派」的通訊 (FANUC 版, 廠商測機用)

跟比賽主程式的差別
  不開相機、不讀 vision_profiles.json、不做座標轉換, 也不碰 a 通道 (DO[1] DO[2] R[1])。
  只留下 arm_link.py (和比賽用的是同一支), 所以這裡測通的 Modbus 連線、
  DO[3]/DO[4] 交握、PR[1] 字序, 比賽時完全一樣。

手臂做什麼 → 這支做什麼
  DO[3] 拉 ON  → 把 FAKE_TARGETS 的下一個點寫進 PR[1] (X, Y; Z/W/P/R 為 0), 再把 DO[4] 拉 ON
  DO[3] 放 OFF → arm_link 自動把 DO[4] 放下, 等下一次
  用完會從頭再來

執行 (先跑 python3 arm_link.py 確認連得上)
  python3 arm_link_test_fanuc.py
  沒有 TP 程式時, 可在示教器 MENU → I/O → Digital, 按 IN/OUT 切到 DO, 手動把 DO[3] 按 ON/OFF 模擬

賽前手臂端要先確認的三件事 (FANUC_工科賽通訊設定 PDF)
  1. 手臂 Port#1 IP = arm_link.py 的 ROBOT_IP; 樹莓派有線網卡 192.168.0.50/24
  2. $SNPX_PARAM.$NUM_MODBUS = 1, $MODBUS_ADR = 1; I/O 配置 DO[1-4] / RACK 0 / SLOT 0 / START 1 (改完要重開機)
  3. $SNPX_ASG[2]: $ADDRESS=2, $SIZE=12, $VAR_NAME='PR[1]@1.12', $MULTIPLY=0

注意
  手臂 TP 程式若照 PR[1] 走, 收到座標會真的移動, FAKE_TARGETS 請填這台手臂上安全可達的點。
  不要填 (0, 0): 這個協定用 PR[1] 全 0 代表「沒有可給的物件」。
"""
import time

import arm_link

# ======= 測試用假座標 (單位 mm, 手臂 User Frame 座標) =======
# 這裡只驗通訊, 座標本身不需要準; 但手臂若照 PR[1] 走會真的移動, 務必填安全的點。
FAKE_TARGETS = [
    (300.0, 10.0),
    (300.0, 20.0),
    (300.0, -30.0),
]
# ==========================================================


def main():
    link = arm_link.ArmLink()
    link.open()
    print(f"[測試] 連線: {arm_link.HOST}:{arm_link.PORT}")
    print(f"[測試] 假座標共 {len(FAKE_TARGETS)} 個, 用完會從頭再來")
    print("[測試] 等 DO[3]=ON ... (Ctrl+C 離開)\n")

    i = 0                                   # 下一次要給第幾個假座標
    total = 0                               # 這次總共給了幾組
    try:
        while True:
            for cmd in link.poll():         # DO[3] 剛拉 ON 且還沒回過 → ["GET"]
                if cmd != arm_link.CMD_GET:
                    continue
                x, y = FAKE_TARGETS[i % len(FAKE_TARGETS)]
                i += 1
                total += 1
                print(f"[收到]DO[3]=ON, 第 {total} 次請求 → 寫 PR[1] X={x} Y={y}, 再將DO[4]=ON")
                link.send(arm_link.reply_target(x, y))
                print("       1.確認PR[1]X/Y的值是否正確 ; 確認是否DO[4]=ON")
                print("       2.將DO[3]=OFF後, 自動將DO[4]=OFF ; 再將DO[4]=ON就給下一組座標\n")
            time.sleep(0.1)                 # 每 0.1 秒讀一次 DO[3]
    except KeyboardInterrupt:
        print("\n[測試] 手動結束")
    finally:
        link.close()
        print(f"[測試] 已關閉, 這次共給了 {total} 組座標")


if __name__ == "__main__":
    main()
