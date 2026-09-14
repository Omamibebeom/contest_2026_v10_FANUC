"""
arm_link.py —— B 通道: 用 Modbus TCP 和 FANUC 手臂交換「座標請求 / 座標資料」

樹莓派當 Modbus TCP client, 連到手臂 ROBOT_IP:502 (手臂端是 Modbus server)。
交握流程 (FANUC_工科賽通訊設定v2.pdf 的「訊號交握時序 - 取得座標」):
  1. 手臂要下一件座標 → 把 DO[3] (COORD REQ) 拉 ON
  2. 本模組看到 DO[3]=ON → 回 "GET" 給主程式
  3. 主程式回 "$x,y" → 寫進 PR[1] (X, Y 是辨識值, Z/W/P/R 寫 0) → 再把 DO[4] (COORD ACK) 拉 ON
     主程式回 "$NONE" (沒得給了) → PR[1] 全部寫 0, 一樣拉 DO[4], 手臂 Job 看到 0,0 就知道結束
  4. 手臂讀完 PR[1] 把 DO[3] 放下 → 本模組把 DO[4] 放下, 等下一次

主程式 (main_contest.py) 只認得 poll() 回的指令字和 send() 收的回覆字串, 不碰 Modbus 細節。

Modbus 位址對照 (手臂端 $SNPX_ASG 設定見 PDF; pymodbus 位址 = FANUC 位址 - 1):
  DO[1]~DO[4]  → Coil 0~3           (A 通道用 DO[1] DO[2]; B 通道用 DO[3] DO[4])
  R[1]         → Holding Reg 0      (A 通道顏色代碼, 由 pi_gpio_controller.py 寫)
  PR[1]        → Holding Reg 1~12   ($SNPX_ASG[2]: $ADDRESS=2, $SIZE=12, 'PR[1]@1.12'; X Y Z W P R 各 2 個 16-bit)

直接執行 python3 arm_link.py = 連線自我檢查 (測 TCP 502 埠 → 讀 DO[1]~DO[4])。
寫 PR[1] 的交握測試在 pr_test.py。
"""
import time
import socket
import struct
from pymodbus.client import ModbusTcpClient

# ---------- 手臂連線設定 (全案唯一一處; pi_gpio_controller.py 從這裡 import) ----------
ROBOT_IP = "192.168.0.1"         # 手臂 Port#1 IP (PDF: MENU → SETUP → Host Comm → TCP/IP)
ROBOT_PORT = 502                 # Modbus TCP 固定埠
DEVICE_ID = 1                    # Modbus unit id (PDF: $SNPX_PARAM.$MODBUS_ADR = 1)

# ---------- B 通道用到的 Modbus 位址 (pymodbus 是 0-based) ----------
COIL_COORD_REQ = 2               # DO[3] 座標請求 (手臂拉)
COIL_COORD_ACK = 3               # DO[4] 座標就緒 (我們拉)
REG_PR1_START = 1                # PR[1] 的第一個 Holding Register (FANUC $ADDRESS=2 → pymodbus 1)
PR_FIELDS = ("X", "Y", "Z", "W", "P", "R")   # PR[1] 六個分量的順序, 每個佔 2 個 register

# ---------- 給主程式看的常數 ----------
HOST, PORT = ROBOT_IP, ROBOT_PORT            # main_contest.py 在「階段二」那行會印出來
CMD_GET, CMD_SCAN, CMD_GRIP = "GET", "SCAN", "GRIP"
CMD_RELEASE, CMD_RESET, CMD_QUIT = "RELEASE", "RESET", "QUIT"
REPLY_OK, REPLY_BYE, REPLY_NONE = "$OK", "$BYE", "$NONE"


def reply_target(x, y):
    """一件物件的手臂座標, 例: $487.5,0.0 (不回顏色, 手臂照 PICK_ORDER 順序就知道第幾件是什麼)。"""
    return f"${x:.1f},{y:.1f}"


def reply_count(n):
    return f"$COUNT,{n}"


def float_to_fanuc_regs(val):
    """一個 32-bit float → 兩個 16-bit register, 低字在前。
    這是 FANUC 範例程式的順序; 若 pr_test.py 看到 PR[1] 數值很大或完全不對, 先檢查這裡的字序。"""
    b = struct.pack(">f", float(val))
    upper16 = struct.unpack(">H", b[0:2])[0]
    lower16 = struct.unpack(">H", b[2:4])[0]
    return [lower16, upper16]


def pr_regs(x, y, z=0.0, w=0.0, p=0.0, r=0.0):
    """PR[1] 六個分量 → 12 個 register (順序同 PR_FIELDS)。"""
    regs = []
    for v in (x, y, z, w, p, r):
        regs += float_to_fanuc_regs(v)
    return regs


class ArmLink:
    def __init__(self):
        self.client = ModbusTcpClient(ROBOT_IP, port=ROBOT_PORT)
        self._asking = False         # True = 這次 DO[3] 已轉成 GET 交給主程式, 別重複交 (否則 PICK_ORDER 會被多扣一件)

    def open(self):
        """連上手臂 (主程式在快照完成後才呼叫)。連不上也不中止, 之後每圈 poll 會再試。"""
        try:
            if self.client.connect():
                print(f"[arm] 已連上 FANUC Modbus {ROBOT_IP}:{ROBOT_PORT}")
            else:
                print(f"[arm] 連不上 {ROBOT_IP}:{ROBOT_PORT}, 之後每圈會再試 (先跑 python3 arm_link.py 檢查)")
        except Exception as e:
            print(f"[arm] 連線錯誤: {e}")

    def _ensure_connection(self):
        if not self.client.is_socket_open():
            self.client.connect()

    def _read_coil(self, addr):
        """讀一個 coil → True/False; 讀不到回 None。"""
        res = self.client.read_coils(address=addr, count=1, device_id=DEVICE_ID)
        if res is None or res.isError():
            return None
        return bool(res.bits[0])

    def poll(self):
        """每圈呼叫一次。DO[3] 剛拉 ON 且還沒回過 → 回 ["GET"]; DO[3] 是 OFF → 順便把 DO[4] 放下。其他回 []。"""
        try:
            self._ensure_connection()
            req = self._read_coil(COIL_COORD_REQ)
            if req is None:
                return []
            if req:
                # DO[4] 還沒拉 (這次請求還沒回過) 才交 GET 給主程式
                if not self._asking and self._read_coil(COIL_COORD_ACK) is False:
                    self._asking = True
                    return [CMD_GET]
            else:
                # 手臂放下 DO[3] = 這輪交握結束 → 放下 DO[4], 準備下一次
                self.client.write_coil(address=COIL_COORD_ACK, value=False, device_id=DEVICE_ID)
                self._asking = False
        except Exception:
            pass
        return []

    def send(self, text):
        """把主程式的回覆字串變成 Modbus 動作:
        "$x,y"  → 寫 PR[1] (X, Y 辨識值, 其餘 0) → 拉 DO[4]
        "$NONE" → 寫 PR[1] 全 0             → 拉 DO[4]
        其他 ($OK / $BYE / $COUNT,n) 手臂端沒有對應訊號, 不做事。
        順序固定「資料先寫成功, 再送 ACK」, 手臂看到 DO[4]=ON 時 PR[1] 一定已經是新值。"""
        if text == REPLY_NONE:
            regs, note = pr_regs(0.0, 0.0), "沒得給了 → PR[1] 全 0"
        elif text.startswith("$"):
            try:
                px, py = (float(t) for t in text[1:].split(",")[:2])
            except ValueError:
                return
            regs, note = pr_regs(px, py), f"PR[1] X={px} Y={py}"
        else:
            return
        try:
            self._ensure_connection()
            self.client.write_registers(address=REG_PR1_START, values=regs, device_id=DEVICE_ID)
            self.client.write_coil(address=COIL_COORD_ACK, value=True, device_id=DEVICE_ID)
            print(f"[arm] {text} → {note}, DO[4] ON")
        except Exception as e:
            print(f"[arm] 寫入失敗: {e}")

    def close(self):
        self.client.close()


# ---------- 直接執行: 連線自我檢查 ----------
def self_test(watch_sec=10):
    """階段一: TCP 連得到 502 埠嗎? 階段二: Modbus 讀得到 DO[1]~DO[4] 嗎?
    通過後再持續顯示 watch_sec 秒, 讓你在示教器上切 DO 看這裡有沒有跟著變。回傳 True = 通訊正常。"""
    print(f"=== arm_link 連線檢查: {ROBOT_IP}:{ROBOT_PORT} ===")

    print("[1/2] TCP 連線 ...", end=" ", flush=True)
    try:
        socket.create_connection((ROBOT_IP, ROBOT_PORT), timeout=3).close()
        print("OK")
    except socket.timeout:
        print("失敗 (逾時): 手臂沒回應")
        print("      → 檢查網路線、樹莓派有線網卡 IP 是否為 192.168.0.x、手臂 Port#1 IP 是否為 " + ROBOT_IP)
        return False
    except ConnectionRefusedError:
        print("失敗 (拒絕連線): 手臂有回應, 但 502 埠沒開")
        print("      → 檢查 $SNPX_PARAM.$NUM_MODBUS 是否為 1, 改完手臂要重新開機")
        return False
    except OSError as e:
        print(f"失敗: {e}")
        return False

    print("[2/2] Modbus 讀 DO[1]~DO[4] ...", end=" ", flush=True)
    client = ModbusTcpClient(ROBOT_IP, port=ROBOT_PORT, timeout=3)
    if not client.connect():
        print("失敗: pymodbus 連不上")
        return False
    try:
        res = client.read_coils(address=0, count=4, device_id=DEVICE_ID)
        if res.isError():
            print(f"失敗: 手臂拒絕讀取 ({res})")
            print("      → 檢查 $SNPX_ASG 與 I/O 配置")
            return False
        print("OK")
        print(f"接下來 {watch_sec} 秒每 0.5 秒讀一次。到示教器 I/O → Digital Out 切換 DO[1]~DO[4], 下面的值要跟著變 (Ctrl+C 可提早結束)")
        t_end = time.time() + watch_sec
        while time.time() < t_end:
            res = client.read_coils(address=0, count=4, device_id=DEVICE_ID)
            bits = res.bits[:4]
            print("  " + "  ".join(f"DO[{i + 1}]={'ON ' if b else 'OFF'}" for i, b in enumerate(bits)))
            time.sleep(0.5)
        return True
    except KeyboardInterrupt:
        return True
    finally:
        client.close()


if __name__ == "__main__":
    if self_test():
        print("=== 通訊正常, 下一步: python3 pr_test.py 測 PR[1] 寫入 ===")
    else:
        print("=== 請先排除上面的問題再往下 ===")
