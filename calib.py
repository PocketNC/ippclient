'''
Prototype of V2 calibration routine
'''
import sys
from ipp import Client, TransactionCallbacks, float3, CmmException, readPointData
import routines
import asyncio
from tornado.ioloop import IOLoop
from dataclasses import dataclass

HOST = "10.0.0.1"
PORT = 1294

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
    ydiff = 16
    xdiff = 50
    print("Manually position probe above A-backing plate then provide any input to continue")
    input()
    getStartPos = client.Get("X(),Y(),Z()")
    await getStartPos.complete()
    pos = readPointData(getStartPos.data_list[0])
    # pos = client.points[-1]
    print("Got pos %s" % pos)
    await client.PtMeas("X(%s),Y(%s),Z(%s),IJK(0,0,1)" % (pos.x,pos.y,pos.z)).complete()
    
    input()
    await client.GoTo("X(%s),Y(%s),Z(%s)" % (pos.x,pos.y+ydiff,pos.z)).complete()
    input()
    await client.GoTo("X(%s),Y(%s),Z(%s)" % (pos.x,pos.y+ydiff,pos.z-20)).complete()
    input()
    await client.PtMeas("X(%s),Y(%s),Z(%s),IJK(0,1,0)" % (pos.x,pos.y+ydiff,pos.z-20)).complete()

    input()
    await client.GoTo("X(%s),Y(%s),Z(%s)" % (pos.x-xdiff,pos.y+ydiff,pos.z-20)).complete()
    input()
    await client.GoTo("X(%s),Y(%s),Z(%s)" % (pos.x-xdiff,pos.y,pos.z-20)).complete()
    input()
    await client.PtMeas("X(%s),Y(%s),Z(%s),IJK(1,0,0)" % (pos.x-xdiff,pos.y,pos.z-20)).complete()

    input()
    await client.GoTo("X(%s),Y(%s),Z(%s)" % (pos.x-xdiff,pos.y-ydiff,pos.z-20)).complete()
    input()
    await client.GoTo("X(%s),Y(%s),Z(%s)" % (pos.x,pos.y-ydiff,pos.z-20)).complete()
    input()
    await client.PtMeas("X(%s),Y(%s),Z(%s),IJK(0,-1,0)" % (pos.x,pos.y-ydiff,pos.z-20)).complete()

    input()
    await client.GoTo("X(%s),Y(%s),Z(%s)" % (pos.x+xdiff,pos.y-ydiff,pos.z-20)).complete()
    input()
    await client.GoTo("X(%s),Y(%s),Z(%s)" % (pos.x+xdiff,pos.y,pos.z-20)).complete()
    input()
    await client.PtMeas("X(%s),Y(%s),Z(%s),IJK(-1,0,0)" % (pos.x+xdiff,pos.y,pos.z-20)).complete()
    # await client.PtMeas("X(%s),Y(%s),Z(%s),IJK(0,0,1)" % (pos.x,pos.y+2,pos.z)).complete()
    # await client.PtMeas("X(%s),Y(%s),Z(%s),IJK(0,0,1)" % (pos.x,pos.y+3,pos.z)).complete()
    # await client.PtMeas("X(%s),Y(%s),Z(%s),IJK(0,0,1)" % (pos.x,pos.y+4,pos.z)).complete()
    # await waitForCommandComplete(client.PtMeas, "X(%s),Y(%s),Z(%s),IJK(0,0,1)" % (pos.x,pos.y,pos.z), otherCallbacks={'data': ptMeasData})

  except CmmException as ex:
    print("CmmExceptions %s" % ex)

  '''
  Do a head-probe line against 1 face of the probing fixture
  '''
  try:
    print("Manually position probe to be +Y from the -X side of the XZ-aligned plane of the L-bracket")
    input()
    getBackPos = client.Get("X(),Y(),Z()")
    await getBackPos.complete()
    backPos = readPointData(getBackPos.data_list[0])
    await routines.headProbeLine(client,backPos,float3(1,0,0),100,10,5,20,1,15)


    
  except CmmException as ex:
    print("CmmExceptions %s" % ex)



if __name__ == "__main__":
  asyncio.run(main())
