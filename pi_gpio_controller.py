"""
pi_gpio_controller.py —— A 通道: 用 Modbus TCP 把「顏色」告訴 FANUC 手臂

交握流程 (FANUC_工科賽通訊設定.pdf 的「訊號交握時序 - 辨識顏色」):
  1. 手臂到辨識位置 → 把 DO[1] (COLOR REQ) 拉 ON        ← ready() 讀這個
  2. 主程式投票 3 秒決定顏色 → 呼叫 send(color)
  3. send(): 寫 R[1] = 顏色代碼 → 等 1 秒 → 把 DO[2] (COLOR ACK) 拉 ON → 保持 HOLD_SEC 秒 → DO[2] OFF、R[1] = 0
  4. 手臂讀 R[1] 後把 DO[1] 放下, 主程式才收下一件
辨識失敗: send_fail() 只寫 R[1] = FAIL_CODE, 不拉 DO[2], 保持 FAIL_HOLD_SEC 秒後清掉。

連線設定 (ROBOT_IP 等) 統一放在 arm_link.py, 這裡直接 import。
"""
import time
import threading
from pymodbus.client import ModbusTcpClient

from arm_link import ROBOT_IP, ROBOT_PORT, DEVICE_ID

# ======= 學生作答區: 放置板物件 (A 通道) 顏色 → R[1] 的數字代碼 =======
# 顏色名要和 vision_profiles.json 存的名稱一樣 (小寫); 變數名必須是 IO_CODES (主程式會 import)
IO_CODES = {
    "red": 1,
    "blue": 2,
    "green": 3,
}
FAIL_CODE = 99               # 辨識失敗時寫進 R[1] 的代碼 (DO[2] 不拉)
HOLD_SEC = 7                 # DO[2] 拉 ON 後保持幾秒
FAIL_HOLD_SEC = 10           # 失敗碼保持幾秒
# ==========================================================

# ---------- A 通道用到的 Modbus 位址 (pymodbus 是 0-based; FANUC 位址 - 1) ----------
COIL_COLOR_REQ = 0           # DO[1] 顏色請求 (手臂拉)
COIL_COLOR_ACK = 1           # DO[2] 顏色就緒 (我們拉)
REG_COLOR = 0                # R[1] 顏色代碼 ($SNPX_ASG[1]: $ADDRESS=1, 'R[1]@1.1')


class PiGPIOController:
    """類別名沿用, 主程式只用 ready() / send() / send_fail() / all_off() / cleanup()。"""

    def __init__(self):
        self.client = ModbusTcpClient(ROBOT_IP, port=ROBOT_PORT)
        self.lock = threading.Lock()        # send() 在背景 thread 寫, ready() 在主迴圈讀, 同一條連線要排隊
        try:
            if self.client.connect():
                print(f"[io] 已連上 FANUC Modbus {ROBOT_IP}:{ROBOT_PORT}")
            else:
                print(f"[io] 連不上 {ROBOT_IP}:{ROBOT_PORT}, 之後會再試 (先跑 python3 arm_link.py 檢查)")
        except Exception as e:
            print(f"[io] 連線錯誤: {e}")

    def _ensure_connection(self):
        if not self.client.is_socket_open():
            self.client.connect()

    def ready(self):
        """讀 DO[1]: 1 = 手臂請我們辨識, 0 = 沒有 (讀不到也回 0)。"""
        try:
            with self.lock:
                self._ensure_connection()
                res = self.client.read_coils(address=COIL_COLOR_REQ, count=1, device_id=DEVICE_ID)
                if res and not res.isError():
                    return 1 if res.bits[0] else 0
        except Exception:
            pass
        return 0

    def send(self, color):
        """辨識成功: 背景執行「寫 R[1] → 1 秒 → DO[2] ON → 保持 HOLD_SEC 秒 → 全清」, 不卡主迴圈。
        顏色不在 IO_CODES 裡就當失敗。"""
        code = IO_CODES.get(color, FAIL_CODE)
        if code == FAIL_CODE:
            self.send_fail()
            return

        def run():
            print(f"[io] {color} → R[1]={code}, 1 秒後 DO[2] ON, 保持 {HOLD_SEC} 秒")
            with self.lock:
                self._ensure_connection()
                self.client.write_register(address=REG_COLOR, value=code, device_id=DEVICE_ID)
            time.sleep(1)
            with self.lock:
                self.client.write_coil(address=COIL_COLOR_ACK, value=True, device_id=DEVICE_ID)
            time.sleep(HOLD_SEC)
            self.all_off()

        threading.Thread(target=run, daemon=True).start()

    def send_fail(self):
        """辨識失敗: 背景執行「寫 R[1]=FAIL_CODE (DO[2] 不拉) → 保持 FAIL_HOLD_SEC 秒 → 全清」。"""
        def run():
            print(f"[io] 辨識失敗 → R[1]={FAIL_CODE}, DO[2] 不拉, 保持 {FAIL_HOLD_SEC} 秒")
            with self.lock:
                self._ensure_connection()
                self.client.write_register(address=REG_COLOR, value=FAIL_CODE, device_id=DEVICE_ID)
            time.sleep(FAIL_HOLD_SEC)
            self.all_off()

        threading.Thread(target=run, daemon=True).start()

    def all_off(self):
        """清掉訊號: DO[2] OFF、R[1] = 0。"""
        try:
            with self.lock:
                self._ensure_connection()
                self.client.write_coil(address=COIL_COLOR_ACK, value=False, device_id=DEVICE_ID)
                self.client.write_register(address=REG_COLOR, value=0, device_id=DEVICE_ID)
        except Exception:
            pass

    def cleanup(self):
        """程式結束前關閉連線。"""
        if self.client:
            self.client.close()
