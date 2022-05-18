'''
A set of test methods that perform a variety of measurements
'''
import sys
import ipp
import asyncio


HOST = "10.0.0.1"
PORT = 1294




'''
Check the homed status of the CMM
Attach callbacks for different response messages (homed, unhomed, error)
Run the appropriate callback
'''
async def homing():
  client = ipp.Client(HOST, PORT)

  async def homeCompleteCallback():
    print("homing complete")

  async def isHomedDataCallback(msg):
    isCmmHomed = msg[-4] == "0"
    if not isCmmHomed:
      homeCallbacks = ipp.TransactionCallbacks(complete=homeCompleteCallback)
      await client.home(callbacks=homeCallbacks)


  if not await client.connect():
    print("Failed to connect to server.")

  await client.startSession()

  isHomedCallbacks = ipp.TransactionCallbacks(data=isHomedDataCallback)
  isHomedTag = await client.isHomed(isHomedCallbacks)
  # callbacks[isHomedTag] = {}
  # callbacks[isHomedTag]["&"] = None
  # callbacks[isHomedTag]["%"] = None
  # callbacks[isHomedTag]["#"] = isHomedCallback
  while True:
    msg = await client.handleMessage()
    print("homing: %s" % msg)
    msgTag = msg[0:5]
    if msgTag in client.transactions:
      transaction = client.transactions[msgTag]
      responseKey = msg[6]
      if responseKey == "&":
        await transaction.acknowledge()
      elif responseKey == "%":
        await transaction.complete()
      elif responseKey == "#":
        await transaction.data(msg)
      elif responseKey == "!":
        await transaction.error()

  #     if responseKey in callbacks[msgTag]:
  #       isCmmHomed = await callbacks[msgTag][responseKey](msg)
  #       break
  # callbacks = {}
  # if not isCmmHomed:
  #   homeTagNum = await client.home()
  #   homeTag = "%05d" % homeTagNum
  #   callbacks[homeTag] = {}
  #   # callbacks[homeTag]["&"] = None
  #   callbacks[homeTag]["%"] = homeCompleteCallback
  #   while True:
  #     msg = await client.handleMessage()
  #     msgTag = msg[0:5]
  #     if msgTag in callbacks:
  #       responseKey = msg[6]
  #       if responseKey in callbacks[msgTag]:
  #         await callbacks[msgTag][responseKey]()
  #         break




async def surface():
  print('surface')
  host = "10.0.0.1"
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

'''
Command a single linear move on CMM
Attach callbacks for ACK, COMPLETE, and ERROR
(I'm expecting to trigger ERROR by touching the probe mid-move)
'''
async def move():
  print('move')
  
  client = ipp.Client(HOST, PORT)

  if not await client.connect():
    print("Failed to connect to server.")

  #status check
  await client.isHomed()

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



async def main():
  print(sys.argv)
  selectedTest = sys.argv[1]
  if selectedTest not in globals():
    print("Unrecognized test name %s" % selectedTest)
    sys.exit(0)
  else:
    print("Running test %s" % selectedTest)
  

  await globals()[sys.argv[1]]()

if __name__ == "__main__":
  asyncio.run(main())
