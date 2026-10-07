"""
arm_link.py —— 和機械手臂講話的模組 (FANUC 版; 換ROBOT只改這一支)

樹莓派當 Modbus TCP client, 連到ROBOT ROBOT_IP:502 (ROBOT端是 Modbus server)。
a、b 兩個通道都走這一條 Modbus 連線, 位址對照 (ROBOT端設定見 FANUC_工科賽通訊設定 PDF; pymodbus 位址 = FANUC 位址 - 1):
  DO[1]~DO[4]  → Coil 0~3           (I/O 配置 DO[1-4] / RACK 0 / SLOT 0 / START 1)
  R[1]         → Holding Reg 0      ($SNPX_ASG[1]: $ADDRESS=1, $SIZE=1, 'R[1]@1.1')
  PR[1]        → Holding Reg 1~12   ($SNPX_ASG[2]: $ADDRESS=2, $SIZE=12, 'PR[1]@1.12'; X Y Z W P R 各 2 個 16-bit)

a 通道 (顏色, PDF「辨識顏色 - 訊號交握時序」):
  主程式和 io_test.py 都是透過 pi_gpio_controller.PiGPIOController 送顏色。本檔在 import 時把該類別的
  ready() / send() / send_fail() / all_off() / cleanup() / __init__() 換成「繼電器 + Modbus 一起做」的版本:
  繼電器 R1~R4 與 GPIO26 照 pi_gpio_controller.py 原本的時序輸出, 同一時刻再多寫一份到 Modbus,
  ROBOT 端用實體 DI 讀或用 R[1] 讀都可以; ready 也是兩邊擇一 (GPIO26 拉高 或 DO[1]=ON)
  (main_contest.py 先 import arm_link、再 import pi_gpio_controller, 所以替換會在建立物件之前生效;
  io_test.py 是先建物件再載入 main_contest, 方法掛在類別上, 已建立的物件一樣會改用 Modbus)。
  pi_gpio_controller.py 本身不用改, 學生作答的 IO_CODES / FAIL_CODE / HOLD_SEC / FAIL_HOLD_SEC 照常從那裡讀:
    1. ROBOT到辨識位置 → DO[1] (顏色請求) ON 或 實體 DO 拉高 GPIO26   ← ready() 兩邊任一
    2. 主程式投票 3 秒決定顏色 → send(color)
    3. send(): 繼電器 R2 R3 R4 = IO_CODES 的 (R2, R3, R4); 同一組當 3-bit 二進位 → R[1] = R2*4 + R3*2 + R4 (預設 red=1 blue=2 green=3)
              → 等 1 秒 → R1 拉高 / DO[2] (顏色確認) ON → 保持 HOLD_SEC 秒 → 全關、DO[2] OFF、R[1] = 0
       辨識失敗: send_fail() 繼電器 R2 R3 R4 = FAIL_CODE、R1 不拉高; R[1] = FAIL_CODE 換算的數字 (預設 (1,1,1) = 7), 不拉 DO[2]; 保持 FAIL_HOLD_SEC 秒後清 0
    4. ROBOT讀 R[1] (或實體 DI) 後把 DO[1] / 實體 DO 放 OFF, 主程式才收下一件

b 通道 (座標, PDF「取得座標 - 訊號交握時序」):
    1. ROBOT要下一件座標 → DO[3] (座標請求) ON
    2. poll() 看到 DO[3]=ON → 回 "GET" 給主程式
    3. 主程式回 "$x,y" → send() 寫進 PR[1] (X, Y 是辨識值, Z/W/P/R 寫 0) → DO[4] (座標確認) ON
       主程式回 "$NONE" (沒得給了) → PR[1] 全部寫 0, 一樣拉 DO[4], ROBOT看到 X=Y=0 就知道結束
    4. ROBOT讀完 PR[1] 把 DO[3] 放 OFF → poll() 把 DO[4] 放 OFF, 等下一次

主程式怎麼用 (main_contest.py 已寫好, 這裡只是說明)
  link = ArmLink(); link.open()
  每一圈:  for cmd in link.poll(): link.send(b.handle(cmd))
  結束:    link.close()

直接執行 python3 arm_link.py = 連線自我檢查 (測 TCP 502 埠 → 讀 DO[1]~DO[4])。
a 通道的交握測試用 io_test.py; b 通道 (PR[1] 寫入) 用 arm_link_test_fanuc.py。
"""
import time
import socket
import struct
import threading
from pymodbus.client import ModbusTcpClient

import pi_gpio_controller
from pi_gpio_controller import IO_CODES, FAIL_CODE, HOLD_SEC, FAIL_HOLD_SEC

# ---------- ROBOT連線設定 (全案唯一一處) ----------
ROBOT_IP = "192.168.0.1"         # ROBOT Port#1 IP (PDF: MENU → SETUP → Host Comm → TCP/IP)
ROBOT_PORT = 502                 # Modbus TCP 固定埠
#DEVICE_ID = 1                    # Modbus unit id (PDF: $SNPX_PARAM.$MODBUS_ADR = 1)
CONNECT_TIMEOUT = 1.0            # 每次讀寫最多等幾秒 (ROBOT沒開時, 主迴圈才不會卡太久)
RECONNECT_SEC = 2.0              # 連線失敗後隔幾秒再試

# ---------- Modbus 位址 (pymodbus 是 0-based) ----------
COIL_COLOR_REQ = 0               # DO[1] 顏色請求 (ROBOT拉)
COIL_COLOR_ACK = 1               # DO[2] 顏色確認 (我們拉)
COIL_COORD_REQ = 2               # DO[3] 座標請求 (ROBOT拉)
COIL_COORD_ACK = 3               # DO[4] 座標確認 (我們拉)
REG_COLOR = 0                    # R[1] 顏色代碼
REG_PR1_START = 1                # PR[1] 的第一個 Holding Register (FANUC $ADDRESS=2 → pymodbus 1)
PR_FIELDS = ("X", "Y", "Z", "W", "P", "R")   # PR[1] 六個分量的順序, 每個佔 2 個 register

# ---------- 給主程式看的常數 ----------
HOST, PORT = ROBOT_IP, ROBOT_PORT            # main_contest.py 在「階段二」那行會印出來
CMD_GET, CMD_SCAN, CMD_GRIP = "GET", "SCAN", "GRIP"
CMD_RELEASE, CMD_RESET, CMD_QUIT = "RELEASE", "RESET", "QUIT"
REPLY_OK, REPLY_BYE, REPLY_NONE = "$OK", "$BYE", "$NONE"


def reply_target(x, y):
    """一件物件的ROBOT座標, 例: $487.5,0.0 (不回顏色, ROBOT照 PICK_ORDER 順序就知道第幾件是什麼)。"""
    return f"${x:.1f},{y:.1f}"


def reply_count(n):
    return f"$COUNT,{n}"


# ==============================================================================
# 共用的 Modbus 連線 (a、b 通道與背景執行緒都走這一條, 用鎖排隊)
# ==============================================================================
_client = ModbusTcpClient(ROBOT_IP, port=ROBOT_PORT, timeout=CONNECT_TIMEOUT, retries=0)
_lock = threading.Lock()
_last_fail = 0.0                 # 上次連線失敗的時間, 用來隔 RECONNECT_SEC 秒再試


def _connected():
    """確認連線還在; 斷了就重連 (失敗後 RECONNECT_SEC 秒內不重試)。回傳 True = 可以讀寫。"""
    global _last_fail
    if _client.connected:
        return True
    if time.time() - _last_fail < RECONNECT_SEC:
        return False
    if _client.connect():
        return True
    _last_fail = time.time()
    return False


def _read_coil(addr):
    """讀一個 coil → True/False; 讀不到回 None。"""
    with _lock:
        if not _connected():
            return None
        try:
            res = _client.read_coils(address=addr, count=1, slave=1)
        except Exception:
            return None
    if res is None or res.isError():
        return None
    return bool(res.bits[0])


def _write_coil(addr, value):
    """寫一個 coil; 回傳 True = 成功。"""
    with _lock:
        if not _connected():
            return False
        try:
            res = _client.write_coil(address=addr, value=value, slave=1)
        except Exception:
            return False
    return res is not None and not res.isError()


def _write_regs(addr, values):
    """從 addr 起連續寫多個 holding register; 回傳 True = 成功。"""
    with _lock:
        if not _connected():
            return False
        try:
            res = _client.write_registers(address=addr, values=list(values), slave=1)
        except Exception:
            return False
    return res is not None and not res.isError()


def _close():
    with _lock:
        _client.close()


# ==============================================================================
# a 通道: 用 Modbus 版本替換 PiGPIOController 的方法
# ==============================================================================
def _code_of(bits):
    """IO_CODES 的 (R2, R3, R4) → R[1] 的數字: R2 是最高位。例 (0,0,1)=1、(0,1,0)=2、(0,1,1)=3、(1,1,1)=7。"""
    r2, r3, r4 = bits
    return int(r2) * 4 + int(r3) * 2 + int(r4)


# ---- 保留 pi_gpio_controller 原本的方法 (繼電器那一半), 下面的新方法會呼叫它們 ----
_gpio_init = pi_gpio_controller.PiGPIOController.__init__
_gpio_ready = pi_gpio_controller.PiGPIOController.ready
_gpio_cleanup = pi_gpio_controller.PiGPIOController.cleanup


def _a_init(self):
    """繼電器 GPIO 照常初始化, 再把 Modbus 這邊的 DO[2]、R[1] 清 0 (連不上就等第一次讀寫時再連)。"""
    _gpio_init(self)
    print(f"[I/O] a 通道同時走 Modbus: DO[1] → R[1] / DO[2] ({ROBOT_IP}:{ROBOT_PORT}); 繼電器 R1~R4 照常輸出")
    _a_all_off(self)


def _a_ready(self):
    """GPIO26 拉高 或 DO[1]=ON, 任一個就算 ROBOT 請我們辨識 (Modbus 讀不到當 0)。"""
    return 1 if (_gpio_ready(self) == 1 or _read_coil(COIL_COLOR_REQ)) else 0


def _a_all_off(self):
    """清掉兩邊的訊號: 繼電器全關、DO[2] OFF、R[1] = 0。"""
    self._set(0, 0, 0, 0)                      # pi_gpio_controller 原本的低階方法, 未被替換
    _write_coil(COIL_COLOR_ACK, False)
    _write_regs(REG_COLOR, [0])


def _a_send(self, color):
    """辨識成功, 背景執行、不卡主迴圈, 兩條路同一時序:
    繼電器: R2 R3 R4 擺好 → 1 秒 → R1 拉高 → 保持 HOLD_SEC 秒 → 全關
    Modbus: 寫 R[1]        → 1 秒 → DO[2] ON → 保持 HOLD_SEC 秒 → DO[2] OFF、R[1] = 0
    顏色不在 IO_CODES 裡就當失敗。"""
    if color not in IO_CODES:
        _a_send_fail(self)
        return
    r2, r3, r4 = IO_CODES[color]
    code = _code_of((r2, r3, r4))

    def run():
        print(f"[I/O] {color} → R2 R3 R4 = {r2} {r3} {r4}, R[1]={code}; 1 秒後 R1 拉高 / DO[2] ON, 保持 {HOLD_SEC} 秒")
        self._set(0, r2, r3, r4)
        if not _write_regs(REG_COLOR, [code]):
            print("[I/O] 寫 R[1] 失敗 (連不上ROBOT?), 這次 Modbus 不拉 DO[2], 繼電器照常")
        time.sleep(1)
        self._set(1, r2, r3, r4)
        _write_coil(COIL_COLOR_ACK, True)
        time.sleep(HOLD_SEC)
        _a_all_off(self)

    threading.Thread(target=run, daemon=True).start()


def _a_send_fail(self):
    """辨識失敗, 兩條路同一時序: 繼電器 R1 不拉高、R2 R3 R4 = FAIL_CODE; Modbus 寫 R[1] = 失敗碼、DO[2] 不拉;
    保持 FAIL_HOLD_SEC 秒後全清。"""
    r2, r3, r4 = FAIL_CODE
    code = _code_of(FAIL_CODE)

    def run():
        print(f"[I/O] 辨識失敗 → R2 R3 R4 = {r2} {r3} {r4}, R[1]={code}; R1 不拉高 / DO[2] 不拉, 保持 {FAIL_HOLD_SEC} 秒")
        self._set(0, r2, r3, r4)
        _write_regs(REG_COLOR, [code])
        time.sleep(FAIL_HOLD_SEC)
        _a_all_off(self)

    threading.Thread(target=run, daemon=True).start()


def _a_cleanup(self):
    """程式結束前: 兩邊都清掉、關閉 Modbus 連線、釋放 GPIO。"""
    _a_all_off(self)
    _close()
    _gpio_cleanup(self)


pi_gpio_controller.PiGPIOController.__init__ = _a_init
pi_gpio_controller.PiGPIOController.ready = _a_ready
pi_gpio_controller.PiGPIOController.send = _a_send
pi_gpio_controller.PiGPIOController.send_fail = _a_send_fail
pi_gpio_controller.PiGPIOController.all_off = _a_all_off
pi_gpio_controller.PiGPIOController.cleanup = _a_cleanup


# ==============================================================================
# b 通道: PR[1] 編碼與 ArmLink
# ==============================================================================
def float_to_fanuc_regs(val):
    """一個 32-bit float → 兩個 16-bit register, 低字在前。
    這是 FANUC 範例程式的順序; 若 arm_link_test_fanuc.py 看到 PR[1] 數值很大或完全不對, 先檢查這裡的字序。"""
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
        self._asking = False         # True = 這次 DO[3] 已轉成 GET 交給主程式, 別重複交 (否則 PICK_ORDER 會被多扣一件)

    def open(self):
        """連上ROBOT (主程式在快照完成後才呼叫)。連不上也不中止, 之後每圈 poll 會再試。"""
        with _lock:
            ok = _connected()
        if ok:
            print(f"[ROBOT] 已連上 FANUC Modbus {ROBOT_IP}:{ROBOT_PORT}")
        else:
            print(f"[ROBOT] 連不上 {ROBOT_IP}:{ROBOT_PORT}, 之後每圈會再試 (先跑 python3 arm_link.py 檢查)")

    def poll(self):
        """每圈呼叫一次。DO[3] 剛拉 ON 且還沒回過 → 回 ["GET"]; DO[3] 是 OFF → 順便把 DO[4] 放下。其他回 []。"""
        req = _read_coil(COIL_COORD_REQ)
        if req is None:
            return []
        if req:
            # DO[4] 還沒拉 (這次請求還沒回過) 才交 GET 給主程式
            if not self._asking and _read_coil(COIL_COORD_ACK) is False:
                self._asking = True
                return [CMD_GET]
        else:
            # ROBOT放下 DO[3] = 這輪交握結束 → 放下 DO[4], 準備下一次
            # (DO[3]=OFF 時每圈都寫一次, 上一次程式沒清乾淨的 DO[4] 也會被順手放下)
            if _write_coil(COIL_COORD_ACK, False):
                self._asking = False
        return []

    def send(self, text):
        """把主程式的回覆字串變成 Modbus 動作:
        "$x,y"  → 寫 PR[1] (X, Y 辨識值, 其餘 0) → 拉 DO[4]
        "$NONE" → 寫 PR[1] 全 0             → 拉 DO[4]
        其他 ($OK / $BYE / $COUNT,n) ROBOT端沒有對應訊號, 不做事。
        順序固定「資料先寫成功, 再送 ACK」, ROBOT看到 DO[4]=ON 時 PR[1] 一定已經是新值。"""
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
        if _write_regs(REG_PR1_START, regs) and _write_coil(COIL_COORD_ACK, True):
            print(f"[ROBOT] {text} → {note}, DO[4] ON")
        else:
            print(f"[ROBOT] 寫入失敗 (連不上ROBOT?): {note}")

    def close(self):
        _close()


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
        print("失敗 (逾時): ROBOT沒回應")
        print("      → 檢查網路線、樹莓派有線網卡 IP 是否為 192.168.0.x、ROBOT Port#1 IP 是否為 " + ROBOT_IP)
        return False
    except ConnectionRefusedError:
        print("失敗 (拒絕連線): ROBOT有回應, 但 502 埠沒開")
        print("      → 檢查 $SNPX_PARAM.$NUM_MODBUS 是否為 1, 改完ROBOT要重新開機")
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
        res = client.read_coils(address=0, count=4, slave=1)
        if res.isError():
            print(f"失敗: ROBOT拒絕讀取 ({res})")
            print("      → 檢查 I/O 配置 (DO[1-4] 有沒有分配到 Modbus) 與 $SNPX_ASG")
            return False
        print("OK")
        print(f"接下來 {watch_sec} 秒每 0.5 秒讀一次。到示教器 I/O → Digital Out 切換 DO[1]~DO[4], 下面的值要跟著變 (Ctrl+C 可提早結束)")
        t_end = time.time() + watch_sec
        while time.time() < t_end:
            res = client.read_coils(address=0, count=4, slave=1)
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
        print("=== 通訊正常, 下一步: python3 io_test.py 測 a 通道, python3 arm_link_test_fanuc.py 測 PR[1] 寫入 ===")
    else:
        print("=== 請先排除上面的問題再往下 ===")
