from pymodbus.client import ModbusTcpClient

# Replace with your logger's IP and port (default Modbus TCP port is 502)
client = ModbusTcpClient('192.168.5.10', port=502)

# Connect to the logger
client.connect()

# Example: Read 2 holding registers starting at address 40001 (Modbus address 0)
# You need to know the correct register addresses for your data!
result = client.read_input_registers(address=7999, count=1, slave=247)


if result.isError():
    print("Error reading register 8000:", result)
else:
    value = result.registers[0]
    print(f"Raw value at address 8000: 0x{value:04X}")

    if value == 0x0705:
        print("Logger type: Logger3000")
    elif value == 0x0710:
        print("Logger type: Logger1000")
    elif value == 0x0718:
        print("Logger type: Logger4000")
    else:
        print("Logger type: Unknown")

result_devices = client.read_input_registers(address=8004, count=1, slave=247)
if result_devices.isError():
    print("Error reading register 8005:", result_devices)
else:
    total_devices = result_devices.registers[0]
    print(f"Total devices connected: {total_devices}")
    
# Read total yield of array at address 8080 (zero-based: 8079), U64, factor 0.1
result_total_yield = client.read_input_registers(address=8079, count=4, slave=247)
if result_total_yield.isError():
    print("Error reading register 8080:", result_total_yield)
else:
    regs = result_total_yield.registers
    # Combine 4 registers to a 64-bit unsigned integer (big-endian)
    total_yield = (regs[0] << 48) + (regs[1] << 32) + (regs[2] << 16) + regs[3]
    total_yield_kwh = total_yield * 0.1
    print(f"Total yield of array: {total_yield_kwh} kWh")

# Read total active power of the array at address 8070 (zero-based: 8069), U64, factor 1
result_total_power = client.read_input_registers(address=8069, count=4, slave=247)
if result_total_power.isError():
    print("Error reading register 8070:", result_total_power)
else:
    regs = result_total_power.registers
    # Combine 4 registers to a 64-bit unsigned integer (big-endian)
    total_power = (regs[0] << 48) + (regs[1] << 32) + (regs[2] << 16) + regs[3]
    print(f"Total active power of array: {total_power} W")

result_soc = client.read_input_registers(address=8162, count=1, slave=247)
if result_soc.isError():
    print("Error reading Battery Level (SOC):", result_soc)
else:
    soc_raw = result_soc.registers[0]
    soc_percent = soc_raw * 0.1
    print(f"Battery Level (SOC): {soc_percent:.1f}%")

result_gateway_power = client.read_input_registers(address=8156, count=2, slave=247)
if result_gateway_power.isError():
    print("Error reading Active power of gateway meter:", result_gateway_power)
else:
    regs = result_gateway_power.registers
    # Combine 2 registers to a 32-bit signed integer (big-endian)
    raw = (regs[0] << 16) + regs[1]
    # Convert to signed
    if raw >= 0x80000000:
        raw -= 0x100000000
    gateway_power_kw = raw * 0.01
    print(f"Active power of gateway meter: {gateway_power_kw:.2f} kW")

result_total_active_power = client.read_input_registers(address=8154, count=2, slave=247)
if result_total_active_power.isError():
    print("Error reading Total active power (8155):", result_total_active_power)
else:
    regs = result_total_active_power.registers
    # Combine 2 registers to a 32-bit signed integer (big-endian)
    raw = (regs[0] << 16) + regs[1]
    # Convert to signed
    if raw >= 0x80000000:
        raw -= 0x100000000
    total_active_power_kw = raw * 0.01
    print(f"Total active power: {total_active_power_kw:.2f} kW")

# Read total reactive power of the array at address 8076 (zero-based: 8075), S64, factor 1 var
result_total_reactive_power = client.read_input_registers(address=8075, count=4, slave=247)
if result_total_reactive_power.isError():
    print("Error reading Total reactive power of array (8076):", result_total_reactive_power)
else:
    regs = result_total_reactive_power.registers
    # Combine 4 registers to a 64-bit signed integer (big-endian)
    raw = (regs[0] << 48) + (regs[1] << 32) + (regs[2] << 16) + regs[3]
    # Convert to signed
    if raw >= 0x8000000000000000:
        raw -= 0x10000000000000000
    print(f"Total reactive power of array: {raw} var")

# Read Max. adjustable active power of array at address 8086 (zero-based: 8085), U32, factor 0.1 kW
result_max_adjustable_active_power = client.read_input_registers(address=8085, count=2, slave=247)
if result_max_adjustable_active_power.isError():
    print("Error reading Max. adjustable active power of array (8086):", result_max_adjustable_active_power)
else:
    regs = result_max_adjustable_active_power.registers
    # Combine 2 registers to a 32-bit unsigned integer (big-endian)
    max_adjustable_active_power = (regs[0] << 16) + regs[1]
    max_adjustable_active_power_kw = max_adjustable_active_power * 0.1
    print(f"Max. adjustable active power of array: {max_adjustable_active_power_kw:.1f} kW")

# Read Max. adjustable reactive power of array at address 8090 (zero-based: 8089), S32, factor 0.1 kVar
result_max_adjustable_reactive_power = client.read_input_registers(address=8089, count=2, slave=247)
if result_max_adjustable_reactive_power.isError():
    print("Error reading Max. adjustable reactive power of array (8090):", result_max_adjustable_reactive_power)
else:
    regs = result_max_adjustable_reactive_power.registers
    # Combine 2 registers to a 32-bit signed integer (big-endian)
    raw = (regs[0] << 16) + regs[1]
    # Convert to signed
    if raw >= 0x80000000:
        raw -= 0x100000000
    max_adjustable_reactive_power_kvar = raw * 0.1
    print(f"Max. adjustable reactive power of array: {max_adjustable_reactive_power_kvar:.1f} kVar")


# Read Total nominal active power at address 8145 (zero-based: 8144), U32, factor 0.1 kW
result_total_nominal_active_power = client.read_input_registers(address=8144, count=2, slave=247)
if result_total_nominal_active_power.isError():
    print("Error reading Total nominal active power (8145):", result_total_nominal_active_power)
else:
    regs = result_total_nominal_active_power.registers
    # Combine 2 registers to a 32-bit unsigned integer (big-endian)
    total_nominal_active_power = (regs[0] << 16) + regs[1]
    total_nominal_active_power_kw = total_nominal_active_power * 0.1
    print(f"Total nominal active power: {total_nominal_active_power_kw:.1f} kW")

# Read Max. allowable charge power of battery at address 8151 (zero-based: 8150), U16, factor 0.1 kW
result_max_allowable_charge_power = client.read_input_registers(address=8150, count=1, slave=247)
if result_max_allowable_charge_power.isError():
    print("Error reading Max. allowable charge power of battery (8151):", result_max_allowable_charge_power)
else:
    raw = result_max_allowable_charge_power.registers[0]
    max_allowable_charge_power_kw = raw * 0.1
    print(f"Max. allowable charge power of battery: {max_allowable_charge_power_kw:.1f} kW")


# Read Max. allowable discharge power of battery at address 8153 (zero-based: 8152), U16, factor 0.1 kW
result_max_allowable_discharge_power = client.read_input_registers(address=8152, count=1, slave=247)
if result_max_allowable_discharge_power.isError():
    print("Error reading Max. allowable discharge power of battery (8153):", result_max_allowable_discharge_power)
else:
    raw = result_max_allowable_discharge_power.registers[0]
    max_allowable_discharge_power_kw = raw * 0.1
    print(f"Max. allowable discharge power of battery: {max_allowable_discharge_power_kw:.1f} kW")

# Read Total active power at address 8155 (zero-based: 8154), S32, factor 0.01 kW
result_total_active_power = client.read_input_registers(address=8154, count=2, slave=247)
if result_total_active_power.isError():
    print("Error reading Total active power (8155):", result_total_active_power)
else:
    regs = result_total_active_power.registers
    # Combine 2 registers to a 32-bit signed integer (big-endian)
    raw = (regs[0] << 16) + regs[1]
    # Convert to signed
    if raw >= 0x80000000:
        raw -= 0x100000000
    total_active_power_kw = raw * 0.01
    print(f"Total active power: {total_active_power_kw:.2f} kW")



# Set sub-array inverter OFF (write 0 to holding register 8002, zero-based 8001)
#result = client.write_register(address=8002, value=0, slave=5)

#if result.isError():
#    print("Error setting sub-array inverter OFF:", result)
#else:
#    print("Successfully set sub-array inverter OFF (register 8002 = 0)")


# slave_id = 247  # Logger address
# register_address = 8001  # Modbus address for register 8002

# result = client.write_register(address=register_address, value=0, slave=slave_id)
# if result.isError():
#     print("Error stopping inverter:", result)
# else:
#     print("Successfully stopped inverter (register 8002 = 0)")


#slave_id = 1  # Logger address

# 1. Set discharge command
# result_cmd = client.write_register(address=8024, value=0xBB, slave=slave_id)
# if result_cmd.isError():
#     print("Error sending discharge command:", result_cmd)
# else:
#     print("Discharge command sent (register 8025 = 0xBB)")

# 2. Set discharge power to 10 kW (value = 100, factor 0.1 kW)
# result_power = client.write_register(address=8025, value=100, slave=slave_id)
# if result_power.isError():
#     print("Error setting discharge power:", result_power)
# else:
#     print("Discharge power set to 10 kW (register 8026 = 100)")

client.close()