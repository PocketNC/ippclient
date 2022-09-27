'''
A set of test methods that perform a variety of measurements
'''
import sys
from ipp import Client, TransactionCallbacks, waitForEvent, setEvent, waitForCommandComplete, futureWaitForCommandComplete, float3, CmmException, readPointData
import ipp_routines as routines
import asyncio
from tornado.ioloop import IOLoop
from dataclasses import dataclass

HOST = "10.0.0.1"
PORT = 1294

X_ORIGIN = 528
Y_ORIGIN = 238
Z_ORIGIN = 400
ORIGIN = float3(X_ORIGIN,Y_ORIGIN,Z_ORIGIN)

waypoints = {
  'origin': ORIGIN,
  'top_l_bracket_front_right': float3(367.5, 422.0, 126.33),
  'probe_fixture_tip': float3(326.0, 290.0, 50.0),
}


async def version():
  try:
    client = Client(HOST, PORT)
    
    await client.connect()

    # await client.StartSession().complete()
    await client.ClearAllErrors().complete()

    getVersion = await client.GetDMEVersion().complete()
    print(getVersion.data_list)

    await client.EndSession().complete()
    await client.disconnect()
    return getVersion.data_list[0]
  except Exception as e:
    print("Test 'version' failed, exception")
    print(e)


'''
Ensure that the CMM is homed
  Prepare to send IsHomed
    data response callback
      if not already homed, send home command
    error response callback
      bail out
  Send IsHomed command
  Wait until confirmation CMM is homed, or quit upon error
'''
async def homing():
  client = Client(HOST, PORT)  
  if not await client.connect():
    print("Failed to connect to server.")
  
  await client.StartSession().complete()
  await client.ClearAllErrors().complete()
  await routines.ensure_homed(client)

  await asyncio.sleep(1)
  await client.EndSession().complete()
  await client.disconnect()


async def pt():

  client = Client(HOST, PORT)
  
  if not await client.connect():
    print("Failed to connect to server.")

  await client.StartSession().complete()
  await client.ClearAllErrors().complete()
  await routines.ensure_homed(client)

  await routines.ensure_tool_loaded(client, "Component_3.1.50.4.A0.0-B0.0")

  approachPos = waypoints['top_l_bracket_front_right'] + float3(0,0,100)
  await client.GoTo(approachPos.ToXYZString()).complete()
  await client.SetProp("Tool.PtMeasPar.HeadTouch(0)").complete()
  await client.GoTo("Tool.A(0),Tool.B(0)").complete()

  ptMeas = await client.PtMeas("%s,IJK(0,0,1)" % (waypoints['top_l_bracket_front_right'].ToXYZString())).complete()
  pt = float3.FromXYZString(ptMeas.data_list[0])
  print(pt)

  await asyncio.sleep(1)
  await client.EndSession().complete()
  await client.disconnect()
  return pt



async def exc():
  try:
    client = Client(HOST, PORT)
    
    await client.connect()

    # await client.StartSession().complete()
    await client.ClearAllErrors().complete()

    await client.GoTo("X(0)").complete()

    await client.EndSession().complete()

    await asyncio.sleep(1)
    await client.disconnect()
  except CmmException as e:
    print("Inner CmmExc %s" % e)
  except Exception as e:
    print("Inner Exc %s" % e)


async def exc2():
  client = Client(HOST, PORT)
  try:
    await client.connect()

    print('waiting')
    try:
      # await client.GoTo("Z(0)")
      cmds = [(client.GoTo, ["Z(0)"]),(client.GoTo, ["X(0)"])]
      r = await client.sendCommandSequence(cmds)
      print("result %s" % r)
    except CmmException as e:
      print("Inner CmmExc %s" % e)
    except Exception as e:
      print("Inner Exc %s" % e)

    await asyncio.sleep(1)
    await client.disconnect()
  except CmmException as e:
    print("Outer CmmExc %s" % e)
  except Exception as e:
    print("Outer Exc %s" % e)
    print(e)



'''
Set a tool alignment
'''
async def align():
  client = Client(HOST, PORT)
  await client.connect()
  messageHandler = asyncio.create_task(client.handleMessages())

  await client.StartSession()

  await waitForCommandComplete(client.ClearAllErrors)
  # await waitForCommandComplete(client.SetTool, "Component_3.1.50.4.A0.0-B0.0")

  # await waitForCommandComplete(client.GoTo, "Tool.Alignment(0,0,1,0,0,1,0.01,0.01)")
  await waitForCommandComplete(client.AlignTool, "-0.01,-0.999,-0.052,0.274,0,0.884,0.1,0.1")

  await client.EndSession()
  await asyncio.sleep(1)
  await client.disconnect()



'''
Perform a PtMeas in empty space
Deal with the exception and try again
'''
async def ex_recovery():
  client = Client(HOST, PORT)
  await client.connect()
  getCurrPosCmd = await client.Get("X(),Y(),Z()").complete()
  currPos = readPointData(getCurrPosCmd.data_list[0])
  try:
    cmd = client.PtMeas("%s,IJK(0,1,0)" % (currPos.ToXYZString()))
    ptMeas = await cmd.error()
    print('got the error')
    print(ptMeas)
    print(ptMeas.exception())
    # ptMeas = await asyncio.wait([cmd.complete(), cmd.error()], return_when=asyncio.FIRST_COMPLETED)
  except Exception as e:
    print('yeah')
    print(e)


'''
Command two linear moves on CMM
  To X0, Y0
  To X0, Y400
If an error occurs stop early
'''
async def move():

  client = Client(HOST, PORT)
  await client.connect()
  messageHandler = asyncio.create_task(client.handleMessages())

  await client.StartSession()

  await waitForCommandComplete(client.ClearAllErrors)
  # clearErrorsCompleted = asyncio.Event()
  # waitForClearErrorsTask = asyncio.create_task(waitForEvent(clearErrorsCompleted))
  # clearErrorsCallbacks = TransactionCallbacks(complete=(lambda: setEvent(clearErrorsCompleted)))
  # await client.ClearAllErrors(clearErrorsCallbacks)
  # await waitForClearErrorsTask

  await waitForCommandComplete(client.SetTool, "Component_3.1.50.4.A0.0-B0.0")
  # setToolCompleted = asyncio.Event()
  # waitForSetToolTask = asyncio.create_task(waitForEvent(setToolCompleted))
  # setToolCallbacks = TransactionCallbacks(complete=(lambda: setEvent(setToolCompleted)))
  # await client.SetTool("Component_3.1.50.4.A0.0-B0.0", setToolCallbacks)
  # await waitForSetToolTask
    

  global isError
  isError = False
  goToEvent = asyncio.Event()

  async def goToError(err):
    global isError
    isError = True
    goToEvent.set()

  async def goToComplete():
    goToEvent.set()

  waitForGoToTask = asyncio.create_task(waitForEvent(goToEvent))
  goToCallbacks = TransactionCallbacks(error=goToError, complete=goToComplete)
  await client.GoTo("X(0),Y(0)", goToCallbacks)
  await waitForGoToTask

  if isError:
    print("Error during move 1, stopping now")
    return
    

  goToEvent2 = asyncio.Event()

  async def goToError2(err):
    global isError
    isError = True
    goToEvent2.set()

  async def goToComplete2():
    goToEvent2.set()

  waitForGoToTask2 = asyncio.create_task(waitForEvent(goToEvent2))
  goToCallbacks2 = TransactionCallbacks(error=goToError2, complete=goToComplete2)
  await client.GoTo("X(0),Y(400)", goToCallbacks2)
  await waitForGoToTask2

  if isError:
    print("Error during move 2, stopping now")
    return

  print("Moves completed succesfully")

  await client.EndSession()
  await asyncio.sleep(1)
  await client.disconnect()



'''
Define a surface by taking 4 points
  Touches performed with Z-axis movement
  Touches placed at the corners of a square shape
    Length of square sides can be set (default 25.4mm (1 inch))
If an error occurs stop early
'''
async def surfaceSquareMachineTouchZ(length=25.4):
  print('manually position machine above 1st point then provide any input key to continue')
  input()
  client = Client(HOST, PORT)
  await client.connect()
  messageHandler = asyncio.create_task(client.handleMessages())

  await client.StartSession()

  await waitForCommandComplete(client.ClearAllErrors)
  await waitForCommandComplete(client.SetTool, "Component_3.1.50.4.A0.0-B0.0")

  global startPos
  startPos = float3()

  async def getData(data):
    global startPos
    x = float(data[data.find("X(") + 2 : data.find("), Y")])
    y = float(data[data.find("Y(") + 2 : data.find("), Z")])
    z = float(data[data.find("Z(") + 2 : data.find(")\r\n")])
    startPos = float3(x,y,z)

  getPosDataCallback = getData
  await waitForCommandComplete(client.Get, "X(),Y(),Z()", otherCallbacks={'data': getData})


  global points
  points = []

  async def ptMeasData(data):
    global points
    print("ptmeas: %s" % data)
    x = float(data[data.find("X(") + 2 : data.find("), Y")])
    y = float(data[data.find("Y(") + 2 : data.find("), Z")])
    z = float(data[data.find("Z(") + 2 : data.find(")\r\n")])
    pt = float3(x,y,z)
    points.append(pt)

  await waitForCommandComplete(client.PtMeas, "X(%s),Y(%s),Z(%s),IJK(0,0,1)" % (startPos.x,startPos.y,startPos.z), otherCallbacks={'data': ptMeasData})
  # input()

  # await waitForCommandComplete(client.GoTo, "X(%s),Y(%s),Z(%s)" % (startPos.x,startPos.y-25.4,startPos.z))
  # input()

  await waitForCommandComplete(client.PtMeas, "X(%s),Y(%s),Z(%s),IJK(0,0,1)" % (startPos.x,startPos.y-25.4,startPos.z), otherCallbacks={'data': ptMeasData})
  # input()

  # await waitForCommandComplete(client.GoTo, "X(%s),Y(%s),Z(%s)" % (startPos.x+25.4,startPos.y-25.4,startPos.z))
  # input()
  await waitForCommandComplete(client.PtMeas, "X(%s),Y(%s),Z(%s),IJK(0,0,1)" % (startPos.x+25.4,startPos.y-25.4,startPos.z), otherCallbacks={'data': ptMeasData})
  # input()

  # await waitForCommandComplete(client.GoTo, "X(%s),Y(%s),Z(%s)" % (startPos.x+25.4,startPos.y,startPos.z))
  # input()
  await waitForCommandComplete(client.PtMeas, "X(%s),Y(%s),Z(%s),IJK(0,0,1)" % (startPos.x+25.4,startPos.y,startPos.z), otherCallbacks={'data': ptMeasData})
  # input()
  await waitForCommandComplete(client.GoTo, "X(%s),Y(%s),Z(%s)" % (startPos.x,startPos.y,startPos.z))

  await client.EndSession()
  await asyncio.sleep(1)
  await client.disconnect()

  print(points)




'''
Define a line from 3 points
  Touches performed with Head movement
  Plane must be aligned in the CMM YZ plane
  Probe touch direction CMM -X
If an error occurs stop early
'''
async def linePlusYHeadTouchMinusX():
  print('manually position machine to right (+X) of 1st point then provide any input key to continue')
  input()
  client = Client(HOST, PORT)
  await client.connect()
  messageHandler = asyncio.create_task(client.handleMessages())

  await client.StartSession()

  await waitForCommandComplete(client.ClearAllErrors)
  # await waitForCommandComplete(client.SetTool, "Component_3.1.50.4.A0.0-B0.0")
  await waitForCommandComplete(client.SetProp, "Tool.PtMeasPar.HeadTouch(1)")

  global startPos
  startPos = float3()

  async def getData(data):
    global startPos
    x = float(data[data.find("X(") + 2 : data.find("), Y")])
    y = float(data[data.find("Y(") + 2 : data.find("), Z")])
    z = float(data[data.find("Z(") + 2 : data.find(")\r\n")])
    startPos = float3(x,y,z)

  getPosDataCallback = getData
  await waitForCommandComplete(client.Get, "X(),Y(),Z()", otherCallbacks={'data': getData})

  await waitForCommandComplete(client.GoTo, "X(%s),Y(%s),Z(%s),Tool.Alignment(0, 0.14, 0.99)" % (startPos.x,startPos.y,startPos.z))
  input()

  global points
  points = []

  async def ptMeasData(data):
    global points
    print("ptmeas: %s" % data)
    x = float(data[data.find("X(") + 2 : data.find("), Y")])
    y = float(data[data.find("Y(") + 2 : data.find("), Z")])
    z = float(data[data.find("Z(") + 2 : data.find(")\r\n")])
    pt = float3(x,y,z)
    points.append(pt)

  await waitForCommandComplete(client.PtMeas, "X(%s),Y(%s),Z(%s),IJK(0,0.988,-0.156)" % (startPos.x,startPos.y,startPos.z), otherCallbacks={'data': ptMeasData})
  input()
  await waitForCommandComplete(client.PtMeas, "X(%s),Y(%s),Z(%s),IJK(0.988,0,-0.156),Tool.Alignment(0.14, 0, 0.99)" % (startPos.x-15.24,startPos.y+26.4,startPos.z), otherCallbacks={'data': ptMeasData})
  input()
  # await waitForCommandComplete(client.PtMeas, "X(%s),Y(%s),Z(%s),IJK(0,-0.988,+0.156)" % (startPos.x,startPos.y+52.8,startPos.z), otherCallbacks={'data': ptMeasData})
  # input()

  # # await waitForCommandComplete(client.GoTo, "X(%s),Y(%s),Z(%s)" % (startPos.x,startPos.y-25.4,startPos.z))
  # # input()

  await waitForCommandComplete(client.SetProp, "Tool.PtMeasPar.HeadTouch(0)")

  await client.EndSession()
  await asyncio.sleep(1)
  await client.disconnect()

  # print(points)


async def line():
  client = Client(HOST, PORT)
  await client.connect()

  await client.ClearAllErrors().complete()
  getPos = client.Get("X(),Y(),Z()")
  await getPos.complete()
  pos = float3.FromXYZString(getPos.data_list[0])

  print(pos)
  input()
  await client.GoTo(pos.ToXYZString()).complete()
  input()
  await routines.probe_line(client, pos, float3(1,1,0), float3(1, -1, -1), 50, 10, 3)

  
  await client.EndSession().complete()
  await client.disconnect()


async def test1():
  client = Client(HOST, PORT)
  await client.connect()
  messageHandler = asyncio.create_task(client.handleMessages())

  await waitForCommandComplete(client.StartSession)
  # await waitForCommandComplete(client.SetTool, "Component_3.1.50.4.A0.0-B0.0")
  await waitForCommandComplete(client.ClearAllErrors)
  await routines.ensure_homed(client)
  input()

  # global startPos
  # startPos = float3()

  # async def getData(data):
  #   global startPos
  #   x = float(data[data.find("X(") + 2 : data.find("), Y")])
  #   y = float(data[data.find("Y(") + 2 : data.find("), Z")])
  #   z = float(data[data.find("Z(") + 2 : data.find(")\r\n")])
  #   startPos = float3(x,y,z)

  # getPosDataCallback = getData

  # global points
  # points = []

  # async def ptMeasData(data):
  #   global points
  #   print("ptmeas: %s" % data)
  #   x = float(data[data.find("X(") + 2 : data.find("), Y")])
  #   y = float(data[data.find("Y(") + 2 : data.find("), Z")])
  #   z = float(data[data.find("Z(") + 2 : data.find(")\r\n")])
  #   pt = float3(x,y,z)
  #   points.append(pt)

  startPos = float3(252.57, 250.16, -56.60)

  # await waitForCommandComplete(client.GoTo, "X(%s),Y(%s),Z(%s)" % (startPos.x,startPos.y,startPos.z))
  await routines.headprobe_line(client,startPos,float3(0,1,0),50,10,5,10,1,15)
  # await routines.headOnlyLineOnVerticalFace(client,startPos,float3(0,1,0),50,3,10,1,15)

  await waitForCommandComplete(client.SetProp, "Tool.PtMeasPar.HeadTouch(0)")

  await client.EndSession()
  await asyncio.sleep(1)
  await client.disconnect()

  # print(points)


async def test45():
  client = Client(HOST, PORT)
  await client.connect()
  await client.ClearAllErrors().complete()

  startPos = float3(203.72, 138.57, 276.75)

  # await waitForCommandComplete(client.GoTo, "X(%s),Y(%s),Z(%s)" % (startPos.x,startPos.y,startPos.z))
  points = await routines.headprobe_line(client,startPos,float3(-1,-1,0),30,10,3,10,-1,15)
  # await routines.headOnlyLineOnVerticalFace(client,startPos,float3(0,1,0),50,3,10,1,15)


  await client.EndSession().complete()
  await client.disconnect()

  print(points)



async def headProbeXZ_vertical():
  client = Client(HOST, PORT)
  try:
    await client.connect()
  except CmmException:
    pass
  await client.ClearAllErrors().complete()
  await routines.ensure_homed(client)
  await routines.ensure_tool_loaded(client, "Component_3.1.50.4.A0.0-B0.0")
  input()

  getPos = client.Get("X(),Y(),Z()")
  await getPos.complete()
  # startPos = float3.FromXYZString(getPos.data_list[0])
  startPos = float3(345.2, 643.1, 407.3)


  # await waitForCommandComplete(client.GoTo, "X(%s),Y(%s),Z(%s)" % (startPos.x,startPos.y,startPos.z))
  points = await routines.headprobe_line_xz(client,startPos,float3(0,0,-1),30,float3(1,0,0),5,1)
  # await routines.headOnlyLineOnVerticalFace(client,startPos,float3(0,1,0),50,3,10,1,15)


  await client.EndSession().complete()
  await client.disconnect()

  print(points)



async def headProbeXZ_45():
  client = Client(HOST, PORT)
  try:
    await client.connect()
  except CmmException:
    pass
  await client.ClearAllErrors().complete()
  await routines.ensure_homed(client)
  await routines.ensure_tool_loaded(client, "Component_3.1.50.4.A0.0-B0.0")
  input()

  getPos = client.Get("X(),Y(),Z()")
  await getPos.complete()
  startPos = float3.FromXYZString(getPos.data_list[0])
  # startPos = float3(345.2, 643.1, 407.3)


  # await waitForCommandComplete(client.GoTo, "X(%s),Y(%s),Z(%s)" % (startPos.x,startPos.y,startPos.z))
  points = await routines.headprobe_line_xz(client,startPos,float3(-1,0,-1),30,float3(1,0,0),5,1)
  # await routines.headOnlyLineOnVerticalFace(client,startPos,float3(0,1,0),50,3,10,1,15)


  await client.EndSession().complete()
  await client.disconnect()

  print(points)





async def backface():
  try:
    client = Client(HOST, PORT)
    
    await client.connect()
    await client.ClearAllErrors().complete()
    await routines.ensure_homed(client)
    await routines.ensure_tool_loaded(client, "Component_3.1.50.4.A0.0-B0.0")
  
    top_l_bracket_back_right = float3(371.9, 466.8, 126.33)
    approachPos = top_l_bracket_back_right + float3(-10,10,10)
    await client.GoTo(approachPos.ToXYZString()).complete()
    await client.GoTo("Tool.A(0),Tool.B(0)").complete()
    input()
    approachPos = top_l_bracket_back_right + float3(-10,10,-20)
    await client.GoTo(approachPos.ToXYZString()).complete()
    input()
    
    await client.SetProp("Tool.PtMeasPar.HeadTouch(0)").complete()
    await client.SetProp("Tool.PtMeasPar.Search(25)").complete()
    ptMeas = await client.PtMeas("%s,IJK(0,1,0)" % (approachPos.ToXYZString())).complete()
    pt = float3.FromXYZString(ptMeas.data_list[0])
    input()
    startPos = pt
    await routines.headprobe_line(client,startPos,float3(-1,0,0),75,10,5,10,-1,15)

    await client.EndSession().complete()
    await client.disconnect()
  except Exception as e:
    print("Test 'version' failed, exception")
    print(e)
    await client.disconnect()




async def main():
  print(sys.argv)
  selectedTest = sys.argv[1]
  if selectedTest not in globals():
    print("Unrecognized test name %s" % selectedTest)
    sys.exit(0)
  else:
    print("Running test %s" % selectedTest)
  
  if len(sys.argv) > 2:
    await globals()[sys.argv[1]](sys.argv[2:])
  else:
    await globals()[sys.argv[1]]()

if __name__ == "__main__":
  asyncio.run(main())
