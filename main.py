import ipp
import asyncio


async def main():
  # host = "localhost"
  host = "10.0.0.1"
  # port = 50007
  port = 1294

  client = ipp.Client(host, port)

  if not await client.connect():
    logger.debug("Failed to connect to server.")

  async def sendAndWait(ippCommandMethod):
    logger.debug("Send and wait: %s" % ippCommandMethod)
    tag = await ippCommandMethod()
    while True:
      msg = await client.handleMessage()
      logger.debug("Got msg: %s" % msg)
      if ("%s %%" % (tag)) in msg:
        logger.debug("%s transaction complete" % tag)

  await sendAndWait(client.startSession)

  print(client.transactions)


if __name__ == "__main__":
  asyncio.run(main())
