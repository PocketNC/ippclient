'''
A set of routines that perform common command sequeunces and can be used in consumer applications
'''
import sys
import ipp
from ipp import Client, TransactionCallbacks, waitForEvent, setEvent, waitForCommandComplete, float3, CmmException
import asyncio
from tornado.ioloop import IOLoop
import math
import numpy as np
import logging
logger = logging.getLogger(__name__)


HOST = "10.0.0.1"
PORT = 1294


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
async def ensure_homed(client):
  isHomedTransaction = client.IsHomed()
  await isHomedTransaction.complete()
  isHomedData = isHomedTransaction.data_list
  print(isHomedTransaction.data_list)
  isCmmHomed = isHomedData[0][-4] == "1"
  print("isHomed %s" % isCmmHomed)

  if not isCmmHomed:
    home = client.Home()
    await home.complete()


  '''
    homedEvent = asyncio.Event()
    waitForHomedTask = asyncio.create_task(waitForEvent(homedEvent))

    async def homeCompleteCallback():
      homedEvent.set()

    async def isHomedDataCallback(msg):
      isCmmHomed = msg[-4] == "1"
      if not isCmmHomed:
        homeCallbacks = ipp.TransactionCallbacks(complete=homeCompleteCallback)
        await client.Home(callbacks=homeCallbacks)
      else:
        homedEvent.set()

    async def isHomedErrorCallback(msg):
      print("Got error from isHomed")

    isHomedCallbacks = ipp.TransactionCallbacks(data=isHomedDataCallback)
    isHomedTag = await client.IsHomed(isHomedCallbacks)

    print('waiting')
    await waitForHomedTask
    print('finished')
  '''


async def ensure_tool_loaded(client,toolName):
  getCurrTool = await client.GetProp(["Tool.Name()"]).complete()
  print(getCurrTool.data_list)
  if toolName not in getCurrTool.data_list[0]:
    await client.ChangeTool(toolName).complete()
    # await futuresWaitForCommandComplete(client.GetProp, "Tool.Name()")


# async def probeLineInParallelPlane(client, startPos, lineVec, length, clearance, direction, plane):


async def probe_line(client, startPos, lineVec, faceNorm, length, clearance, numPoints, direction):
  '''
  uses CMM motion
  '''
  toolLength = 117.8
  global points
  points = []

  startApproachPos = startPos + faceNorm * clearance
  probeAlignVec = float3(np.cross(lineVec,faceNorm))*direction

  await client.GoTo("Tool.Alignment(%s, %s, %s, %s,%s,%s)" % ( -probeAlignVec.x, -probeAlignVec.y, -probeAlignVec.z, -faceNorm.x,-faceNorm.y,-faceNorm.z )).complete()
  await client.GoTo("%s" % ( startApproachPos.ToXYZString() )).complete()
  await client.SetProp("Tool.PtMeasPar.HeadTouch(0)").complete()
  for step in range(numPoints):
    fracLen = step / numPoints * length
    approachPos = startApproachPos + lineVec * (step / (numPoints-1) * length)
    contactPos = startPos + lineVec * (step / (numPoints-1) * length)
    print("ContactPos %s" % contactPos)
    await client.GoTo("X(%s),Y(%s),Z(%s),Tool.Alignment(%s, %s, %s, %s,%s,%s)" % (approachPos.x,approachPos.y,approachPos.z, -probeAlignVec.x, -probeAlignVec.y, -probeAlignVec.z, -faceNorm.x,-faceNorm.y,-faceNorm.z)).complete()
    ptMeas = await client.PtMeas("X(%s),Y(%s),Z(%s),IJK(%s,%s,%s)" % (contactPos.x,contactPos.y,contactPos.z,faceNorm.x,faceNorm.y,faceNorm.z)).complete()
    pt = float3.FromXYZString(ptMeas.data_list[0])
    points.append(pt)
  return points


async def omni_headprobe_line(client, startPos, lineVec, faceNorm, length, contactAngle, numPoints, direction):
  '''
  find the center position along the lineVec
  find in-plane travel angle using center and start positions
  find probeNormal at startPos contact using in-plane travel angle and contactAngle
  find center of rotation  (from startPos back along probe normal defined by contactAngle and in-plane travel angle)
  ...(i'm not sure how to finish this)
  '''
  return False


async def headprobe_line_xz(client, startPos, lineVec, length, faceNorm, numPoints, direction, headPos):
  '''
  headProbeLine for faces (approximately) parallel to CMM Y-axis
  line up A-90, B-0 (or B-180) with mid pos
  find A and B travel angles
  find the horizontal travel distance (along X) using length and slope

  line up A-90 with top pos (either end or start pos depending on slope)
  the B-component perp to lineVec at midPos (midPos = startPos + lineVec * length * 0.5)

  find B travel angle from
  line up b-perp-to-lineVec
  '''
  logger.debug('headprobe_line_xz 1')
  toolLength = 117.8
  points = []

  midPos = startPos + (0.5 * length) * lineVec
  print('midPos %s' % (midPos,))

  perpVec = float3(lineVec.x, -1 * direction * lineVec.z, direction*lineVec.y).normalize()
  print('perpVec %s' % (perpVec,))
  midPosApproach = midPos + perpVec * 10
  print('midPosApproach %s' % (midPosApproach,))

  midPosContactAngle = math.atan2(direction*lineVec.z, direction*lineVec.y)*180/math.pi
  midPosB = 0 if headPos < 0 else 180
  await client.GoTo("X(%s),Y(%s),Z(%s),Tool.A(%s),Tool.B(%s)" % ( midPosApproach.x, midPosApproach.y, midPosApproach.z, 90, midPosB)).complete()
  # xyToolLength = toolLength * math.sin(probeAngle*math.pi/180)
  # centerRot = midPosApproach + float3(xyToolLength * math.sin(midPosAngle),xyToolLength * math.cos(midPosAngle),0)
  # print(midPosApproach)
  # print(centerRot)
  # input()
  await client.SetProp("Tool.PtMeasPar.HeadTouch(1)").complete()
  # input()
  for step in range(numPoints):
    fracLen = step / numPoints * length
    contactPos = startPos + lineVec * (step / (numPoints-1) * length)
    print("ContactPos %s" % contactPos)
    # probeTravelVec = contactPos - centerRot
    # approachPos = contactPos - (0.5*probeTravelVec)
    # print("ApproachPos %s" % approachPos)
    # input()
    ptMeas = await client.PtMeas("X(%s),Y(%s),Z(%s),IJK(%s,%s,%s)" % (contactPos.x,contactPos.y,contactPos.z,perpVec.x,perpVec.y,perpVec.z)).complete()
    pt = float3.FromXYZString(ptMeas.data_list[0])
    points.append(pt)
  return points


async def headprobe_line_yz(client, startPos, lineVec, length, faceNorm, numPoints, direction):
  '''
  headProbeLine for faces (approximately) parallel to CMM X-axis
  line up A-90, B-0 (or B-180) with mid pos
  find A and B travel angles
  find the horizontal travel distance (along X) using length and slope

  line up A-90 with top pos (either end or start pos depending on slope)
  the B-component perp to lineVec at midPos (midPos = startPos + lineVec * length * 0.5)

  find B travel angle from
  line up b-perp-to-lineVec
  '''
  toolLength = 117.8
  points = []

  midPos = startPos + (0.5 * length) * lineVec

  perpVec = float3(-1 * direction * lineVec.z, lineVec.y, direction*lineVec.x).normalize()
  midPosApproach = midPos + perpVec * 10
  midPosB = -90 if direction < 0 else 90
  await client.GoTo("X(%s),Y(%s),Z(%s),Tool.A(%s),Tool.B(%s)" % ( midPosApproach.x, midPosApproach.y, midPosApproach.z, 90, midPosB)).ack()
  await client.SetProp("Tool.PtMeasPar.HeadTouch(1)").complete()

  for step in range(numPoints):
    fracLen = step / numPoints * length
    contactPos = startPos + lineVec * (step / (numPoints-1) * length)
    print("ContactPos %s" % contactPos)
    ptMeas = await client.PtMeas("X(%s),Y(%s),Z(%s),IJK(%s,%s,%s)" % (contactPos.x,contactPos.y,contactPos.z,perpVec.x,0,perpVec.z)).complete()
    pt = float3.FromXYZString(ptMeas.data_list[0])
    points.append(pt)
  return points


async def headprobe_line(client, startPos, lineVec, length, clearance, numPoints, surfaceWidth, direction, probeAngle):
  '''
  only works for horizontal (constant Z) lines
  '''
  toolLength = 117.8
  global points
  points = []


  # angle = 2*180/math.pi*math.atan(0.5*length/clearance)
  midPos = startPos + (0.5 * length) * lineVec
  perpVec = float3(-1 * direction * lineVec.y, direction * lineVec.x, lineVec.z).normalize()
  midPosApproach = midPos + perpVec * clearance
  midPosAngle = math.atan2(-1*direction*lineVec.x, direction*lineVec.y)*180/math.pi
  await client.GoTo("X(%s),Y(%s),Z(%s),Tool.A(%s),Tool.B(%s)" % ( midPosApproach.x, midPosApproach.y, midPosApproach.z, 0, midPosAngle)).ack()
  xyToolLength = toolLength * math.sin(probeAngle*math.pi/180)
  centerRot = midPosApproach + float3(xyToolLength * math.sin(midPosAngle),xyToolLength * math.cos(midPosAngle),0)
  # input()
  # await client.SetProp("Tool.PtMeasPar.HeadTouch(1)").ack()
  # input()
  for step in range(numPoints):
    fracLen = step / (numPoints-1) * length
    contactPos = startPos + lineVec * (step / (numPoints-1) * length)
    len_on_face_from_mid_pos = direction * (0.5 * length - fracLen)
    b_angle = midPosAngle - math.atan2(len_on_face_from_mid_pos,clearance) * 180/math.pi
    await client.GoTo("Tool.A(%s),Tool.B(%s)" % ( 2, b_angle)).complete()

    # probeTravelVec = contactPos - centerRot
    # # approachPos = contactPos - (0.5*probeTravelVec)
    # approachPos = contactPos - (0.5*probeTravelVec)
    # print("ApproachPos %s" % approachPos)
    # # input()
    # try:
    #   await client.GoTo("Tool.A(%s)" % ( probeAngle -2 )).ack()
    #   ptMeas = await client.PtMeas("X(%s),Y(%s),Z(%s),IJK(%s,%s,%s)" % (contactPos.x,contactPos.y,contactPos.z,perpVec.x,perpVec.y,0)).complete()
    # except CmmException as e:
    #   print("CmmException in headProbeLine, raising")
    #   raise e
    ptMeas = await client.PtMeas("X(%s),Y(%s),Z(%s),IJK(%s,%s,%s)" % (contactPos.x,contactPos.y,contactPos.z,perpVec.x,perpVec.y,0)).data()
    pt = float3.FromXYZString(ptMeas.data_list[0])
    points.append(pt)
    await client.GoTo("Tool.A(0)").send()
  return points


'''
Using only head movement, define a linear element
This offers improved speed compared to using machine movement
However, this method is limited in the geometry of the features it can measure
  The length of the line,...
  the width of the actual surface the theoretical line sits upon,...
  and the length of the probe assembly...
  ...together these factors determine whether a particular measurement is possible

dir = sets B-rotate direction
  +1 indicates CW rotate

Find the angle covered (assume a 10mm clearance)
Foreach angular step
  Find the expected contact point: intersection of line from midpoint along angle with feature line
  Step back on this line a fraction to define the approach point
'''
async def headOnlyLineOnVerticalFace(client, startPos, lineVec, length, numPoints, surfaceWidth, direction, probeAngle):

  global calcToolAlignmentData

  async def getData(data):
    global calcToolAlignmentData
    print("getData")
    print(data)
    calcToolAlignmentData = data[data.find("(") + 1:data.find("))") - 2]

  getPosDataCallback = getData
  await waitForCommandComplete(client.CalcToolAlignment, "Tool.A(15),Tool.B(-90)", otherCallbacks={'data': getData})

  print("------------------------------")
  print("calcToolAlignmentData: %s" % calcToolAlignmentData)

  #perpendicular vector in XY plane
  print("startPos %s " % startPos)
  perpVec = float3(startPos.y, startPos.z, startPos.x).normalize()
  print("perpVec %s " % perpVec)
  #find the midpoint
  #we will position probe body so probe swing is perpendicular to face at midpoint
  midPos = startPos + (0.5 * length) * lineVec
  midPosApproach = midPos + perpVec * 10
  print("midPos %s " % midPos)
  print("midPosApproach %s " % midPosApproach)

  #find the angle between the mid-point and start-point probe travel vectors
  midApproachVec = midPos - midPosApproach
  edgeApproachVec = startPos - midPosApproach
  midToEdgeDotProduct = midApproachVec.inner(edgeApproachVec)
  halfAngle = 180/math.pi * math.acos(midToEdgeDotProduct / edgeApproachVec.norm() / midApproachVec.norm())
  fullAngle = halfAngle * 2
  stepAngle = fullAngle/numPoints

  await waitForCommandComplete(client.GoTo, "X(%s),Y(%s),Z(%s),Tool.A(15),Tool.B(-90)" % (midPosApproach.x,midPosApproach.y,midPosApproach.z))

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

  startAngle = -90 + halfAngle
  startPosApproach = startPos + perpVec * 10

  endPos = startPos + lineVec * length
  endPosApproach = endPos + perpVec * 10

  await waitForCommandComplete(client.CalcToolAlignment, "Tool.A(15),Tool.B(%s)" % startAngle, otherCallbacks={'data': getData})
  await waitForCommandComplete(client.PtMeas, "X(%s),Y(%s),Z(%s),IJK(0.371,.928,-0.16)" % (startPosApproach.x,startPosApproach.y,startPosApproach.z), otherCallbacks={'data': ptMeasData})
  input()
  await waitForCommandComplete(client.CalcToolAlignment, "Tool.A(15),Tool.B(%s)" % -90, otherCallbacks={'data': getData})
  await waitForCommandComplete(client.PtMeas, "X(%s),Y(%s),Z(%s),IJK(0.99,0,-0.16)" % (midPosApproach.x,midPosApproach.y,midPosApproach.z), otherCallbacks={'data': ptMeasData})
  input()
  await waitForCommandComplete(client.CalcToolAlignment, "Tool.A(15),Tool.B(%s)" % (-90 - halfAngle)  , otherCallbacks={'data': getData})
  await waitForCommandComplete(client.PtMeas, "X(%s),Y(%s),Z(%s),IJK(0.371,-.928,-0.16)" % (endPosApproach.x,endPosApproach.y,endPosApproach.z), otherCallbacks={'data': ptMeasData})
  # await waitForCommandComplete(client.PtMeas, "X(%s),Y(%s),Z(%s),IJK(-0.096,0.24,0),Tool.Alignment(%s)" % (midPosApproach.x,midPosApproach.y,midPosApproach.z,calcToolAlignmentData), otherCallbacks={'data': ptMeasData})



async def surface():
  client = ipp.Client(HOST, PORT)

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

  await homing()

  async def wait(event):
    await event.wait()

  waitForGoToEvent = asyncio.Event()
  waitForGoToTask = asyncio.create_task(wait(waitForGoToEvent))

  client = ipp.Client(HOST, PORT)
  isHomed = False

  if not await client.connect():
    print("Failed to connect to server.")

  # IOLoop.instance().add_callback(client.handleMessages)
  messageHandler = asyncio.create_task(client.handleMessages())

  await client.StartSession()
  await client.ClearAllErrors()
  await client.SetTool("Component_3.1.50.4.A0.0-B0.0")

  # await client.GetXtdErrStatus()
  # await asyncio.sleep(2)

  # await client.SetProp(["Tool.GoToPar.Speed(2)"])
  # await asyncio.sleep(3)

  # await client.GetXtdErrStatus()
  # await asyncio.sleep(2)
  # await client.ClearAllErrors()
  # await asyncio.sleep(2)

  async def goToError():
    print("got an error")
    waitForGoToEvent.set()

  async def goToComplete():
    print("completed GoTo")
    waitForGoToEvent.set()

  goToCallbacks = ipp.TransactionCallbacks(error=goToError, complete=goToComplete)

  await client.GoTo("Y(0)", goToCallbacks)

  print('waiting')
  await waitForGoToTask
  print('finished')

  await client.EndSession()
  await client.disconnect()

  # await client.GoTo("X(0)")



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
