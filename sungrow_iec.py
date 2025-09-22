from c104.client import IEC104Client

HOST = '192.168.100.184'
PORT = 2404
FEED_IN_LIMIT_ADDR = 17403

def main():
    client = IEC104Client(HOST, PORT)
    client.connect()
    # Send general interrogation to get all values
    result = client.interrogate()
    # result is a dict: {address: value, ...}
    value = result.get(FEED_IN_LIMIT_ADDR)
    if value is not None:
        print(f"Feed-in limitation value: {value}")
    else:
        print(f"Value at address {FEED_IN_LIMIT_ADDR} not found.")
    client.disconnect()

if __name__ == "__main__":
    main()