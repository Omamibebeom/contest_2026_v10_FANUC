import time
from arm_link import ArmLink, CMD_GET

link = ArmLink()
link.open()

print("=========================================")
print(" B 通道 PR[] 寫入與交握測試 (等待 DO[3] 觸發)")
print("=========================================")
print("請至 Roboguide 進行以下操作：")
print("1. 進入 DATA -> Digital Out")
print("2. 手動將 DO[3] 切換為 ON (模擬手臂發出 GET 請求)")
print("程式正在背景輪詢 DO[3] 狀態，隨時等待觸發...\n")

try:
    while True:
        # poll() 會自動去讀取 DO[3] (Coil 2)
        # 如果是 ON，就會回傳 ["GET"]；若是 OFF 則回傳空陣列 []
        cmds = link.poll()
        
        if CMD_GET in cmds:
            print("\n>> [觸發] 偵測到 DO[3] 變為 ON！手臂發出座標請求。")
            
            # 設定測試座標
            test_x = 123.4
            test_y = -56.7
            test_cmd = f"${test_x},{test_y}"
            
            print(f">> [寫入] 轉換並發送測試座標: {test_cmd}")
            link.send(test_cmd)
            
            print(">> [完成] 寫入指令已發送！")
            print("請至 Roboguide 檢查：")
            print(f"  1. PR[1] (DATA -> Position Reg) 的 X 應為 {test_x}, Y 應為 {test_y}")
            print("  2. DO[4] (DATA -> Digital Out) 應轉為 ON (代表座標就緒)")
            print("\n-----------------------------------------")
            print("如需反覆測試，請將 DO[3] 切回 OFF (程式會自動降下 DO[4])，然後再次切為 ON。")
            
        # 暫停 0.1 秒避免 CPU 100% 滿載
        time.sleep(0.1)

except KeyboardInterrupt:
    print("\n測試中斷，關閉連線。")
finally:
    link.close()
