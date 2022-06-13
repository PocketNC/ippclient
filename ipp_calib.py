'''
Prototype of V2 calibration routine
'''
import sys
from ipp import Client, TransactionCallbacks, float3, CmmException, readPointData
import ipp_routines as routines
import asyncio
from tornado.ioloop import IOLoop
from dataclasses import dataclass
# sys.path.append("/Users/jakedanczyk/source/nfs/pocketnc/Settings")
# import metrology

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

DEBUG = True
def debugWait():
  if DEBUG:
    input()
  return

'''
Ensure startup conditions: homed, tool set, errors clear
Verify machine position
  Probe against top of A-backing plate for maximum clearance/safety
Characterize A motion
Characterize B motion
'''

async def main():
  '''
  Setup
  '''
  try:
    client = Client(HOST, PORT)
    await client.connect()
    await client.ClearAllErrors().complete()
    await routines.ensureHomed(client)
    await routines.ensureToolLoaded(client, "Component_3.1.50.4.A0.0-B0.0")
  except CmmException as ex:
    print("CmmExceptions %s" % ex)

  '''
  Locate machine and verify it is in home position
  '''
  try:
    print("Locate machine and verify it is in home posture")
    debugWait()
    await client.GoTo(waypoints['origin'].ToXYZString()).complete()
    debugWait()
    await client.SetProp("Tool.PtMeasPar.Search(25)").complete()
    debugWait()




    #straight down for first touch
    approachPos = waypoints['top_l_bracket_front_right'] + float3(0,0,100)
    await client.GoTo(approachPos.ToXYZString()).complete()
    await client.SetProp("Tool.PtMeasPar.HeadTouch(0)").complete()
    await client.GoTo("Tool.A(0),Tool.B(0)").complete()
    debugWait()

    ptMeas = await client.PtMeas("%s,IJK(0,0,1)" % (waypoints['top_l_bracket_front_right'].ToXYZString())).complete()
    pt = float3.FromXYZString(ptMeas.data_list[0])
    print(pt)
    debugWait()
    nextPos = waypoints['top_l_bracket_front_right'] + float3(0,15,00)
    await client.PtMeas("%s,IJK(0,0,1)" % (nextPos.ToXYZString())).complete()
    debugWait()

    nextPos = waypoints['top_l_bracket_front_right'] + float3(-95,15,0)
    await client.PtMeas("%s,IJK(0,0,1)" % (nextPos.ToXYZString())).complete()
    debugWait()

    nextPos = waypoints['top_l_bracket_front_right'] + float3(-95,0,0)
    await client.PtMeas("%s,IJK(0,0,1)" % (nextPos.ToXYZString())).complete()
    debugWait()


    #head touches against sides of L-bracket
    await client.SetProp("Tool.PtMeasPar.HeadTouch(1)").complete()
    debugWait()

    #head touch right side
    nextPos = waypoints['top_l_bracket_front_right'] + float3(10,10,10)
    await client.GoTo("%s,Tool.B(-90)" % (nextPos.ToXYZString())).complete()
    debugWait()
    nextPos = waypoints['top_l_bracket_front_right'] + float3(10,10,-10)
    await client.GoTo("%s" % (nextPos.ToXYZString())).complete()
    debugWait()
    nextPos = waypoints['top_l_bracket_front_right'] + float3(5,10,-10)
    await client.PtMeas("%s,IJK(1,0,0)" % (nextPos.ToXYZString())).complete()
    debugWait()

    #head touch far side
    nextPos = waypoints['top_l_bracket_front_right'] + float3(10,30,-10)
    await client.GoTo("%s" % (nextPos.ToXYZString())).complete()
    debugWait()
    nextPos = waypoints['top_l_bracket_front_right'] + float3(-47.5,30,-10)
    await client.GoTo("%s,Tool.B(360)" % (nextPos.ToXYZString())).complete()
    debugWait()
    nextPos = waypoints['top_l_bracket_front_right'] + float3(-47.5,20,-10)
    await client.PtMeas("%s,IJK(0,1,0)" % (nextPos.ToXYZString())).complete()
    debugWait()

    #head touch left side
    nextPos = waypoints['top_l_bracket_front_right'] + float3(-110,30,-10)
    await client.GoTo("%s" % (nextPos.ToXYZString())).complete()
    debugWait()
    nextPos = waypoints['top_l_bracket_front_right'] + float3(-110,10,-10)
    await client.GoTo("%s,Tool.B(90)" % (nextPos.ToXYZString())).complete()
    debugWait()
    nextPos = waypoints['top_l_bracket_front_right'] + float3(-100,10,-10)
    await client.PtMeas("%s,IJK(-1,0,0)" % (nextPos.ToXYZString())).complete()
    debugWait()

    #head touch near side
    nextPos = waypoints['top_l_bracket_front_right'] + float3(-105,-20,-10)
    await client.GoTo("%s" % (nextPos.ToXYZString())).complete()
    debugWait()
    nextPos = waypoints['top_l_bracket_front_right'] + float3(-47.5,-20,-10)
    await client.GoTo("%s,Tool.B(180)" % (nextPos.ToXYZString())).complete()
    debugWait()
    nextPos = waypoints['top_l_bracket_front_right'] + float3(-47.5,-10,-10)
    await client.PtMeas("%s,IJK(0,-1,0)" % (nextPos.ToXYZString())).complete()
    debugWait()


    #locate the probe fixtures vertical fin
    #head touch near side
    #head touches against sides of L-bracket
    await client.SetProp("Tool.PtMeasPar.HeadTouch(1)").complete()
    debugWait()
    nextPos = waypoints['probe_fixture_tip'] + float3(20,0,20)
    await client.GoTo("%s,Tool.B(-90)" % (nextPos.ToXYZString())).complete()
    debugWait()
    nextPos = waypoints['probe_fixture_tip'] + float3(20,0,-10)
    await client.GoTo("%s" % (nextPos.ToXYZString())).complete()
    debugWait()
    nextPos = waypoints['probe_fixture_tip'] + float3(0,0,-10)
    await client.PtMeas("%s,IJK(1,0,0)" % (nextPos.ToXYZString())).complete()
    debugWait()

    await client.GoTo("Tool.A(0),Tool.B(-135)").complete()
    debugWait()
    await client.GoTo("Tool.A(30),Tool.B(-135)").complete()
    debugWait()
    await client.GoTo("Tool.A(30),Tool.B(-90)").complete()
    debugWait()
    nextPos = waypoints['probe_fixture_tip'] + float3(-10,0,-10)
    await client.PtMeas("%s,IJK(-1,0,1)" % (nextPos.ToXYZString())).complete()
    debugWait()



    # ydiff = 16
    # xdiff = 50
    # getStartPos = client.Get("X(),Y(),Z()")
    # await getStartPos.complete()
    # pos = readPointData(getStartPos.data_list[0])
    # # pos = client.points[-1]
    # print("Got pos %s" % pos)
    # await client.PtMeas("X(%s),Y(%s),Z(%s),IJK(0,0,1)" % (pos.x,pos.y,pos.z)).complete()
    
    # input()
    # await client.GoTo("X(%s),Y(%s),Z(%s)" % (pos.x,pos.y+ydiff,pos.z)).complete()
    # input()
    # await client.GoTo("X(%s),Y(%s),Z(%s)" % (pos.x,pos.y+ydiff,pos.z-20)).complete()
    # input()
    # await client.PtMeas("X(%s),Y(%s),Z(%s),IJK(0,1,0)" % (pos.x,pos.y+ydiff,pos.z-20)).complete()

    # input()
    # await client.GoTo("X(%s),Y(%s),Z(%s)" % (pos.x-xdiff,pos.y+ydiff,pos.z-20)).complete()
    # input()
    # await client.GoTo("X(%s),Y(%s),Z(%s)" % (pos.x-xdiff,pos.y,pos.z-20)).complete()
    # input()
    # await client.PtMeas("X(%s),Y(%s),Z(%s),IJK(1,0,0)" % (pos.x-xdiff,pos.y,pos.z-20)).complete()

    # input()
    # await client.GoTo("X(%s),Y(%s),Z(%s)" % (pos.x-xdiff,pos.y-ydiff,pos.z-20)).complete()
    # input()
    # await client.GoTo("X(%s),Y(%s),Z(%s)" % (pos.x,pos.y-ydiff,pos.z-20)).complete()
    # input()
    # await client.PtMeas("X(%s),Y(%s),Z(%s),IJK(0,-1,0)" % (pos.x,pos.y-ydiff,pos.z-20)).complete()

    # input()
    # await client.GoTo("X(%s),Y(%s),Z(%s)" % (pos.x+xdiff,pos.y-ydiff,pos.z-20)).complete()
    # input()
    # await client.GoTo("X(%s),Y(%s),Z(%s)" % (pos.x+xdiff,pos.y,pos.z-20)).complete()
    # input()
    # await client.PtMeas("X(%s),Y(%s),Z(%s),IJK(-1,0,0)" % (pos.x+xdiff,pos.y,pos.z-20)).complete()


    # await client.PtMeas("X(%s),Y(%s),Z(%s),IJK(0,0,1)" % (pos.x,pos.y+2,pos.z)).complete()
    # await client.PtMeas("X(%s),Y(%s),Z(%s),IJK(0,0,1)" % (pos.x,pos.y+3,pos.z)).complete()
    # await client.PtMeas("X(%s),Y(%s),Z(%s),IJK(0,0,1)" % (pos.x,pos.y+4,pos.z)).complete()
    # await waitForCommandComplete(client.PtMeas, "X(%s),Y(%s),Z(%s),IJK(0,0,1)" % (pos.x,pos.y,pos.z), otherCallbacks={'data': ptMeasData})

  except CmmException as ex:
    print("CmmExceptions %s" % ex)

  '''
  Do a head-probe line against 1 face of the probing fixture
  '''
  # try:
  #   print("Manually position probe to be +Y from the -X side of the XZ-aligned plane of the L-bracket")
  #   input()
  #   getBackPos = client.Get("X(),Y(),Z()")
  #   await getBackPos.complete()
  #   backPos = readPointData(getBackPos.data_list[0])
  #   await routines.headProbeLine(client,backPos,float3(1,0,0),100,10,5,20,1,15)


    
  # except CmmException as ex:
  #   print("CmmExceptions %s" % ex)
  '''
  End
  '''
  try:
    await client.EndSession().complete()
    await client.disconnect()
  except CmmException as ex:
    print("CmmExceptions %s" % ex)




if __name__ == "__main__":
  asyncio.run(main())
