from pymodbus.client import ModbusTcpClient

ROBOT_IP = "192.168.0.1"   # 如果 Robot 已改成 .0.1，這裡一起改

client = ModbusTcpClient(
    ROBOT_IP,
    port=502,
    timeout=3
)

try:
    print("Connecting...")

    if not client.connect():
        print("TCP 連線失敗")
        raise SystemExit

    print("TCP 連線成功")

    result = client.read_coils(
        address=0,
        count=4,
        slave=1
    )

    print("Modbus response:", result)

    if result.isError():
        print("Modbus 回傳錯誤:", result)
    else:
        print("DO[1] COLOR_REQ =", result.bits[0])
        print("DO[2] COLOR_ACK =", result.bits[1])
        print("DO[3] COORD_REQ =", result.bits[2])
        print("DO[4] COORD_ACK =", result.bits[3])

except Exception as e:
    print("發生錯誤:", repr(e))

finally:
    client.close()
