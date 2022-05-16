import ipp
import asyncio


async def main():
  # host = "localhost"
  host = "10.0.0.1"
  # port = 50007
  port = 1294
  client = ipp.Client(host, port)

  if not await client.connect():
    print("Failed to connect to server.")

  async def sendAndWait(ippCommandMethod):
    # print("Send and wait: %s" % ippCommandMethod)
    tag = await ippCommandMethod()
    # print("Command tag %s" % tag)
    while True:
      msg = await client.handleMessage()
      # print("Got msg: %s" % msg)
      if ("%05d %%" % (tag)) in msg:
        # print("%05d transaction complete" % tag)
        break

  await sendAndWait(client.startSession)
  await sendAndWait(client.getDMEVersion)
  await sendAndWait(client.endSession)

  print(client.transactions)


if __name__ == "__main__":
  asyncio.run(main())
