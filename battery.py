from pymodbus.client import ModbusTcpClient

client = ModbusTcpClient('192.168.5.10', port=502)
client.connect()

slave_id = 247

# 1. Set Energy management mode to VPP (already done previously, but safe to repeat)
client.write_register(address=8023, value=4, slave=slave_id)

# 2. Set charging/discharging command to Discharge (0xBB)
client.write_register(address=8024, value=0xBB, slave=slave_id)

# 3. Set charging/discharging power to 10 kW (register expects 0.1 kW units, so 10 kW = 100)
client.write_register(address=8025, value=100, slave=slave_id)

print("Sent commands to start discharging the battery with 10 kW.")

client.close()