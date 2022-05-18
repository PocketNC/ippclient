import socket
import sys
from enum import Enum
import time
import asyncio
import logging
from tornado.ioloop import IOLoop
from tornado.tcpclient import TCPClient


HOST = "10.0.0.1"
PORT = 1294

status = 0

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

async def noop():
  pass

class CmmException(Exception):
  pass

class TransactionStatus(Enum):
  ERROR = -1
  CREATED = 0
  SENT = 1
  ACK = 2
  COMPLETE = 3

class TransactionCallbacks:
  def __init__(self, send=noop, ack=noop, complete=noop, data=noop, error=noop):
    self.send = send
    self.ack = ack
    self.complete = complete
    self.data = data
    self.error = error

class Transaction:
  def __init__(self, callbacks=TransactionCallbacks()):
    self.status = TransactionStatus.CREATED
    self.dataList = []
    self.errorList = []
    self.callbacks = callbacks

  async def send(self):
    self.status = TransactionStatus.SENT
    await self.callbacks.send()

  async def acknowledge(self):
    self.status = TransactionStatus.ACK
    await self.callbacks.ack()

  async def data(self, data):
    self.dataList.append(data)
    await self.callbacks.data(data)

  async def error(self, err):
    self.errorList.append(err)
    await self.callbacks.error(err)

  async def complete(self):
    self.status = TransactionStatus.COMPLETE
    await self.callbacks.complete()


RECEIVE_SIZE = 1024
class Client:
  def __init__(self, host=HOST, port=PORT):
    self.host = host
    self.port = port
    self.tcpClient = TCPClient()
    self.stream = None
    self.nextTagNum = 1
    self.nextEventTagNum = 1
    self.transactions = {}
    self.events = {}
    self.buffer = ""

  async def connect(self):
    try:
      self.stream = await self.tcpClient.connect(self.host, self.port)
      return True
    except Exception as e:
      logger.error("connect error: %s", e)
      return False

  async def disconnect(self):
    try:
      if self.stream is not None:
        self.stream.close()
    except Exception as e:
      logger.error("disconnect error: %s", e)

  async def sendCommand(self, command, isEvent=False, callbacks=None):
    logger.debug("Send I++ command %s ", command)
    
    try:
      if isEvent:
        tagNum = self.nextEventTagNum
        tag = "E%04d" % eventTagNum 
        self.nextEventTagNum = self.nextEventTagNum%9999+1 # Get the next event tag between 1 - 9999
      else:
        tagNum = self.nextTagNum
        tag = "%05d" % tagNum
        self.nextTagNum = self.nextTagNum%99999+1 # Get the next tag between 1 - 99999

      transaction = Transaction() if callbacks is None else Transaction(callbacks)
      self.transactions[tag] = transaction
      message = "%s %s\r\n" % (tag, command)

      await self.stream.write(message.encode('ascii'))
      await transaction.send()
      return tag
    except Exception as e:
      logger.error(e)

  # Might be removing this, sendCommand now can handle either normal or event commands
  async def sendEventCommand(self, command):
    '''
    Event Commands go into the Fast Queue
    '''
    try:
      logger.debug("Send I++ event-command %s ", command)
      eventTagNum = self.nextEventTag
      eventTag = "E%04d" % eventTagNum
      transaction = Transaction()
      self.transactions[eventTag] = transaction
      message = "%s %s\r\n" % (eventTag, command)
      self.nextEventTag = eventTagNum%9999+1 # Get the next eventTag between 1 - 9999
      await self.tcpClient.send_message(message.encode('ascii'))
      transaction.send()
      return eventTag
    except Exception as e:
      logger.error(e)

  async def handleMessage(self):
    msg = await self.stream.read_until(b"\r\n")
    msg = msg.decode("ascii")
    logger.debug("Rcv msg: %s", msg)
    return msg

  async def sendAndWait(self, command):
    tag = await self.sendCommand(command)
    while True:
      msg = await self.handleMessage()
      if ("%s %%" % (tag)) in msg:
        logger.debug("Transaction Complete")
        break

  async def eventSendAndWait(self, command):
    tag = await self.sendEventCommand(command)
    while True:
      msg = await self.handleMessage()
      if ("%s %%" % (tag)) in msg:
        logger.debug("Transaction Complete")
        break

  async def commandSequence(self, cmdArr ):
    for cmd in cmdArr:
      await self.sendCommand(cmd)

  async def sendCommandWithCallbacks(self, cmd):
    cmdFn = getattr(self, cmd, None)
    if cmdFn is not None:
      await cmdFn()


  '''
  I++ Server Methods
  '''
  async def startSession(self, callbacks=None):
    await self.sendCommand("EndSession()")
    return await self.sendCommand("StartSession()", callbacks=callbacks)

  async def endSession(self, callbacks=None):
    endTag = await self.sendCommand("EndSession()", callbacks=callbacks)
    self.nextTag = 1
    self.nextEventTag = 1
    return endTag

  async def stopDaemon(self, eventTag, callbacks=None):
    return await self.sendCommand("StopDaemon(%s)" % eventTag, callbacks=callbacks)

  async def stopAllDaemons(self, callbacks=None):
    return await self.sendCommand("StopAllDaemons()", callbacks=callbacks)

  async def abortE(self, callbacks=None):
    '''
    Fast Queue command
    '''
    return await self.sendCommand("AbortE()", isEvent=True, callbacks=callbacks)

  async def getErrorInfo(self, errNum=None, callbacks=None):
    return await self.sendCommand("GetErrorInfo(%s)" % str(errNum or ''), callbacks=callbacks)

  async def clearAllErrors(self, callbacks=None):
    return await self.sendCommand("ClearAllErrors()", callbacks=callbacks)

  async def getProp(self, propArr, callbacks=None):
    propsString = ", ".join(propArr)
    return await self.sendCommand("GetProp(%s)" % propsString, callbacks=callbacks)

  async def getPropE(self, propArr, callbacks=None):
    '''
    Fast Queue command
    '''
    propsString = ", ".join(propArr)
    return await self.sendCommand("GetPropE(%s)" % propsString, isEvent=true, callbacks=callbacks)

  async def setProp(self, propArr, callbacks=None):
    propsString = ", ".join(propArr)
    return await self.sendCommand("SetProp(%s)" % propsString, callbacks=callbacks)

  
  async def enumProp(self, pointerString, callbacks=None):
    '''
    Get the list of properties for a system object
    For example, "EnumProp(Tool.PtMeasPar())" will return 
    the active tool's PtMeas properties list
    '''
    return await self.sendCommand("EnumProp(%s)" % pointerString, callbacks=callbacks)

  async def enumAllProp(self, pointerString, callbacks=None):
    '''
    Get the entire tree of properties and sub-properties for a system object
    '''
    return await self.sendCommand("EnumAllProp(%s)" % pointerString, callbacks=callbacks)

  async def getDMEVersion(self, callbacks=None):
    return await self.sendCommand("GetDMEVersion()", callbacks=callbacks)


  '''
  I++ DME Methods
  '''
  async def home(self, callbacks=None):
    return await self.sendCommand("Home()", callbacks=callbacks)

  async def isHomed(self, callbacks=None):
    return await self.sendCommand("IsHomed()", callbacks=callbacks)

  async def enableUser(self, callbacks=None):
    return await self.sendCommand("EnableUser()", callbacks=callbacks)

  async def disableUser(self, callbacks=None):
    return await self.sendCommand("DisableUser()", callbacks=callbacks)

  async def isUserEnabled(self, callbacks=None):
    return await self.sendCommand("IsUserEnabled()", callbacks=callbacks)

  async def onPtMeasReport(self, ptMeasFormatString, callbacks=None):
    '''
    Define the information reported in the result of a PtMeas command
    '''
    return await self.sendCommand("OnPtMeasReport(%s)" % ptMeasFormatString, callbacks=callbacks)

  async def onMoveReportE(self, onMoveReportFormatString, callbacks=None):
    '''
    Fast Queue command
    Start a daemon that reports machine movement, and define
    which information is sent (sequence and contents)
    '''
    return await self.sendCommand("OnMoveReportE(%s)" % onMoveReportFormatString, isEvent=True, callbacks=callbacks)

  async def getMachineClass(self, callbacks=None):
    return await self.sendCommand("GetMachineClass()", callbacks=callbacks)

  async def getErrStatusE(self, callbacks=None):
    '''
    Fast Queue command
    Response is "ErrStatus(1)" if in error
    Response is "ErrStatus(0)" if ok
    '''
    return await self.sendCommand("GetErrStatusE()", isEvent=true, callbacks=callbacks)

  async def getXtdErrStatus(self, callbacks=None):
    '''
    Response is one or more lines of status information
    Could also include one or more errors
    Example:
      IsHomed(1)
      IsUserEnabled(0)
      1009: Air Pressure Out Of Range
      0512: No Daemons Are Active.
    '''
    return await self.sendCommand("GetXtdErrStatus()", callbacks=callbacks)

  async def get(self, queryString, callbacks=None):
    '''
    Query tool position
    queryString example:
      "X(), Y(), Z(), Tool.A(), Tool.B()"
    '''
    return await self.sendCommand("Get(%s)" % queryString, callbacks=callbacks)

  async def goTo(self, positionString, callbacks=None):
    '''
    Move to a target position, including tool rotation
    '''
    return await self.sendCommand("GoTo(%s)" % positionString, callbacks=callbacks)

  async def ptMeas(self, ptMeasString, callbacks=None):
    '''
    Execute a single point measurement
    Necessary parameters are defined by the active tool
    Return format is set by OnPtMeasReport
    Errors if surface not found (Error 1006: Surface not Found)
    '''
    return await self.sendCommand("PtMeas(%s)" % ptMeasString, callbacks=callbacks)

  # See examples 7.6 and 7.7 in IDME specification for tool handling examples
  async def tool(self, callbacks=None):
    '''
    Select a pointer to the active tool
    '''
    return await self.sendCommand("Tool()", callbacks=callbacks)

  async def findTool(self, toolName, callbacks=None):
    '''
    Select a pointer to a tool with a known name
    '''
    return await self.sendCommand("FindTool(%s)" % toolName, callbacks=callbacks)
  
  async def foundTool(self, callbacks=None):
    '''
    Acts as pointer to tool selected by FindTool command
    Default pointer is "UnDefTool" 
    '''
    return await self.sendCommand("FoundTool()", callbacks=callbacks)

  async def changeTool(self, toolName, callbacks=None):
    '''
    Perform a tool change
    '''
    return await self.sendCommand("ChangeTool(%s)" % toolName, callbacks=callbacks)

  async def setTool(self, toolName, callbacks=None):
    '''
    Force the server to assume a given tool is the active tool
    '''
    return await self.sendCommand("SetTool(%s)" % toolName, callbacks=callbacks)

  async def alignTool(self, alignToolString, callbacks=None):
    '''
    Orientate an alignable tool
    '''
    return await self.sendCommand("AlignTool(%s)" % alignToolString, callbacks=callbacks)

  async def goToPar(self, callbacks=None):
    '''
    This method acts as a pointer to the GoToParameter block of the DME
    '''
    return await self.sendCommand("GoToPar()", callbacks=callbacks)

  async def prMeasPar(self, callbacks=None):
    '''
    This method acts as a pointer to the PtMeasParameter block of the DME
    '''
    return await self.sendCommand("PtMeasPar()", callbacks=callbacks)

  async def enumTools(self, callbacks=None):
    '''
    Returns a list of the names of available tools
    '''
    return await self.sendCommand("enumTools()", callbacks=callbacks)

  async def getChangeToolAction(self, toolName, callbacks=None):
    '''
    Query the necessary movement to change to a given tool
    '''
    return await self.sendCommand("GetChangeToolAction(%s)" % toolName, callbacks=callbacks)

  async def enumToolCollection(self, collectionName, callbacks=None):
    '''
    Query the names and types of tools (or child collections) belonging to a collection
    '''
    return await self.sendCommand("EnumToolCollection(%s)" % collectionName, callbacks=callbacks)

  async def enumAllToolCollections(self, collectionName, callbacks=None):
    '''
    Recursively return all tools and sub-collections to this collection
    '''
    return await self.sendCommand("EnumToolCollection(%s)" % collectionName, callbacks=callbacks)

  async def openToolCollection(self, collectionName, callbacks=None):
    '''
    Make all tools in referenced collection visible, meaning a ChangeTool command can
    directly use names in the collection without a path extension
    '''
    return await self.sendCommand("EnumToolCollection(%s)" % collectionName, callbacks=callbacks)

  async def ijkAct(self, callbacks=None):
    '''
    Query the meaning of server IJK() values: actual measured normal, nominal, or tool alignment
    '''
    return await self.sendCommand("IJKAct()", callbacks=callbacks)

  async def ptMeasSelfCenter(self, ptMeasSelfCenterString, callbacks=None):
    '''
    Execute a single point measurement by self-centering probing
    Necessary parameters defined by the active tool
    '''
    return await self.sendCommand("PtMeasSelfCenter(%s)" % ptMeasSelfCenterString, callbacks=callbacks)

  async def ptMeasSelfCenterLocked(self, ptMeasSelfCenterString, callbacks=None):
    '''
    Execute a single point measurement by self-centering probing
    without leaving a plane defined by params
    Necessary parameters defined by the active tool
    '''
    return await self.sendCommand("PtMeasSelfCenter(%s)" % ptMeasSelfCenterString, callbacks=callbacks)

  async def readAllTemperatures(self, callbacks=None):
    return await self.sendCommand("ReadAllTemperatures()", callbacks=callbacks)


  '''
  I++ CartCMM Methods
  '''
  async def setCoordSystem(self, coodSystemString, callbacks=None):
    '''
    Arg is one of: MachineCsy, MoveableMachineCsy, MultipleArmCsy, RotaryTableVarCsy, PartCsy
    '''
    return await self.sendCommand("SetCoordSystem(%s)" % coodSystemString, callbacks=callbacks)

  async def getCoordSystem(self, callbacks=None):
    '''
    Query which coord sys is selected
    '''
    return await self.sendCommand("GetCoordSystem()", callbacks=callbacks)

  async def getCsyTransformation(self, getCsyTransformationString, callbacks=None):
    return await self.sendCommand("GetCsyTransformation(%s)" % getCsyTransformationString, callbacks=callbacks)

  async def setCsyTransformation(self, setCsyTransformationString, callbacks=None):
    return await self.sendCommand("SetCsyTransformation(%s)" % setCsyTransformationString, callbacks=callbacks)

  async def saveActiveCoordSystem(self, csyName, callbacks=None):
    return await self.sendCommand("SaveActiveCoordSystem(%s)" % csyName, callbacks=callbacks)

  async def loadCoordSystem(self, csyName, callbacks=None):
    return await self.sendCommand("LoadCoordSystem(%s)" % csyName, callbacks=callbacks)
    
  async def deleteCoordSystem(self, csyName, callbacks=None):
    return await self.sendCommand("DeleteCoordSystem(%s)" % csyName, callbacks=callbacks)

  async def enumCoordSystem(self, name, callbacks=None):
    return await self.sendCommand("EnumCoordSystem()", callbacks=callbacks)

  async def getNamedCsyTransformation(self, csyName, callbacks=None):
    return await self.sendCommand("GetNamedCsyTransformation(%s)" % csyName, callbacks=callbacks)
  
  async def saveNamedCsyTransformation(self, csyName, csyCoordsString, callbacks=None):
    return await self.sendCommand("SaveNamedCsyTransformation(%s, %s)" % (csyName, csyCoordsStsring), callbacks=callbacks)


  '''
  I++ Tool Methods
  '''
  async def reQualify(self, callbacks=None):
    '''
    Requalify active tool
    '''
    return await self.sendCommand("ReQualify()", callbacks=callbacks)

  async def scanPar(self, callbacks=None):
    '''
    Acts as a pointer to the ScanParameter block of KTool instance
    '''
    return await self.sendCommand("ScanPar()", callbacks=callbacks)

  async def avrRadius(self, callbacks=None):
    '''
    Return average tip radius of selected tool
    '''
    return await self.sendCommand("AvrRadius()", callbacks=callbacks)

  async def isAlignable(self, callbacks=None):
    '''
    Query if selected tool is alignable
    '''
    return await self.sendCommand("IsAlignable()", callbacks=callbacks)

  async def alignment(self, alignmentVectorString, callbacks=None):
    '''
    Query if selected tool is alignable
    '''
    return await self.sendCommand("Alignment(%s)" % alignmentVectorString, callbacks=callbacks)

  async def calcToolAlignment(self, calcToolAlignmentString, callbacks=None):
    '''
    Query the alignment of selected tool
    '''
    return await self.sendCommand("CalcToolAlignment(%s)" % calcToolAlignmentString, callbacks=callbacks)

  async def calcToolAngles(self, calcToolAnglesString, callbacks=None):
    '''
    Query the alignment of selected tool
    '''
    return await self.sendCommand("CalcToolAngles(%s)" % calcToolAnglesString, callbacks=callbacks)

  async def useSmallestAngleToAlignTool(self, enabled, callbacks=None):
    '''
    Param is 0 or 1
    When enabled with CalcToolAngles(1), attempting to rotate the tool by
    180 degrees or more will produce an error
    '''
    return await self.sendCommand("CalcToolAngles(%s)" % calcToolAnglesString, callbacks=callbacks)

  '''
  I++ Scanning Methods
  '''
  async def onScanReport(self, onScanReportString, callbacks=None):
    '''
    Define the format of scan reports
    '''
    return await self.sendCommand("OnScanReport(%s)" % onScanReportString, callbacks=callbacks)

  async def scanOnCircleHint(self, displacement, form, callbacks=None):
    '''
    Optimize ScanOnCircle execution by defining expected deviation from nominal of the measured circle
    '''
    return await self.sendCommand("ScanOnCircleHint(%s, %s)" % (displacement, form), callbacks=callbacks)

  async def scanOnCircle(self, scanOnCircleString, callbacks=None):
    '''
    Perform a scanning measurement on a circular 
    Parameters: (Cx, Cy, Cz, Sx, Sy, Sz, i, j, k, delta, sfa, StepW)
      Cx, Cy, Cz is the nominal center point of the circle
      Sx, Sy, Sz is a point on the circle radius where the scan starts
      i,j,k      is the normal vector of the circle plane
      delta      is the angle to scan
      sfa        is the surface angle of the circle
      StepW      average angular distance between 2 measured points in degrees.
    '''
    return await self.sendCommand("ScanOnCircle(%s)" % (scanOnCircleString), callbacks=callbacks)

  async def scanOnLineHint(self, angle, form, callbacks=None):
    '''
    Optimize ScanOnLine execution by defining expected deviation from nominal of the measured line
    '''
    return await self.sendCommand("ScanOnLineHint(%s, %s)" % (angle, form), callbacks=callbacks)

  async def scanOnLine(self, scanOnLineString, callbacks=None):
    '''
    Perform a scanning measurement on a circular 
    Parameters: (Sx,Sy,Sz,Ex,Ey,Ez,i,j,k,StepW)
      Sx, Sy, Sz defines the line start point
      Ex, Ey, Ez defines the line end point
      i,j,k      is the surface normal vector on the line
      StepW      average distance between 2 measured points in mm
    '''
    return await self.sendCommand("ScanOnLine(%s)" % (scanOnLineString), callbacks=callbacks)

  async def scanOnCurveHint(self, deviation, minRadiusOfCurvature, callbacks=None):
    '''
    Optimize ScanOnCurve execution by defining expected deviation from nominal of the measured curve
    '''
    return await self.sendCommand("ScanOnCurveHint(%s, %s)" % (deviation, minRadiusOfCurvature), callbacks=callbacks)
  
  async def scanOnCurveDensity(self, scanOnCurveDensityString, callbacks=None):
    '''
    Define density of points returned from server by ScanOnCurve execution
    Parameters: (Dis(),Angle(),AngleBaseLength(),AtNominals())
      Dis()             Maximum distance of 2 points returned
      Angle()           Maximum angle between the 2 segments between the last 3 points
      AngleBaseLength() Baselength for calculating the Angle criteria (necessary for small point distances)
      AtNominals()      Boolean 0 or 1. If 1 the arguments Dis() and Angle() are ignored
      
      Dis() or/and AtNominals() without Angle() and AngleBaseLength() also possible.
    '''
    return await self.sendCommand("ScanOnCurveDensity(%s)" % (scanOnCurveDensityString), callbacks=callbacks)

  async def scanOnCurve(self, scanOnCurveString, callbacks=None):
    '''
    Perform a scanning measurement along a curve
    Parameters: ( 
      Closed(), 
      Format(X(),Y(),Z(),IJK(),tag[,pi,pj,pk[,si,sj,sk]]),
      Data(
        P1x,P1y,P1z,i1,j1,k1,tag1[,pi1,pj1,pk1[,si1,sj1,sk1]],
        Pnx,Pny,Pnz,in,jn,jn,tagn[,pin,pjn,pkn[,sin,sjn,skn]]
      )
    )

      Closed() Boolean 0 or 1. 1 means contour is closed
      Format Defines the structure of data set send to server
        X(),Y(),Z() Format definition for nominal point coordinates
        IJK() Format definition for nominal point direction
        [pi,pj,pk] Optional format definition for nominal primary tool direction
        [si,sj,sk] Optional format definition for nominal secondary tool direction
      Data
        Pnx, Pny, Pnz defines the nth surface point of the scanning path
        in, jn, kn defines the nominal surface vector of the nth point
        tagn Integer defining if the nth nominal point is assumed to be on the
          part surface (+1) or without contact to the surface (-1). For this
          spec version the values are fixed to +1 or -1.
        [pin,pjn,pkn] Optional data for nominal primary tool direction
        [sin,sjn,skn] Optional data for nominal secondary tool direction
    '''
    return await self.sendCommand("ScanOnCurve(%s)" % (scanOnCurveString), callbacks=callbacks)

  async def scanOnHelix(self, scanOnHelixString, callbacks=None):
    '''
    Perform a scanning measurement along a helical path
    Parameters: (Cx, Cy, Cz, Sx, Sy, Sz, i, j, k, delta, sfa, StepW, pitch)
      Cx, Cy, Cz is a nominal center point of the helix
      Sx, Sy, Sz is a point on the helix radius where the scan starts
      i,j,k      is the normal vector of the helix plane
      delta      is the angle to scan
      sfa        is the surface angle of the circle, 90 and 270 not allowed
      StepW      average angular distance between 2 measured points in degrees.
      lead       is the lead in mm per 360 degrees rotation
    '''
    return await self.sendCommand("ScanOnHelix(%s)" % (scanOnHelixString), callbacks=callbacks)

  async def scanUnknownHint(self, minRadiusOfCurvature, callbacks=None):
    '''
    Define expected minimum radius of curvature during scan of unknown contour
    '''
    return await self.sendCommand("ScanUnknownHint(%s)" % (minRadiusOfCurvature), callbacks=callbacks)

  async def scanUnknownDensity(self, scanUnknownDensityString, callbacks=None):
      '''
      Define density of points returned from server by ScanUnknown execution
      Parameters: (Dis(),Angle(),AngleBaseLength())
        Dis()             Maximum distance of 2 points returned
        Angle()           Maximum angle between the 2 segments defined by AngleBaseLength()
        AngleBaseLength() Baselength for calculating the Angle criteria (necessary for small point distances)

        Dis() without Angle() and AngleBaseLength() possible.
      '''
      return await self.sendCommand("ScanUnknownDensity(%s)" % (scanUnknownDensityString), callbacks=callbacks)

  async def scanInPlaneEndIsSphere(self, scanInPlaneEndIsSphereString, callbacks=None):
    '''
    Perform a scanning measurement along an unknown contour
    The scan stops if the sphere stop criterion is matched
    Parameters: (Sx,Sy,Sz,Si,Sj,Sk,Ni,Nj,Nk,Dx,Dy,Dz,StepW,Ex,Ey,Ez,Dia,n,Ei,Ej,Ek)
      Sx, Sy, Sz  defines the scan start point
      Si, Sj, Sk  defines the surface direction in the start point
      Ni, Nj, Nk  defines the normal vector of the scanning plane
      Dx, Dy, Dz  defines the scan direction point
      StepW       is the average distance between 2 measured points
      Ex, Ey, Ez, defines the expected scan end point
      Dia         define a sphere around the end point where the scan stops
      n           Number of reaching the stop sphere
      Ei, Ej, Ek  defines the surface direction at the end point. It defines the direction for retracting
    '''
    return await self.sendCommand("ScanInPlaneEndIsSphere(%s)" % (scanInPlaneEndIsSphereString), callbacks=callbacks)

  async def scanInPlaneEndIsPlane(self, scanInPlaneEndIsPlaneString, callbacks=None):
    '''
    Perform a scanning measurement along an unknown contour
    The scan stops if the plane stop criterion is matched
    Parameters: (Sx,Sy,Sz,Si,Sj,Sk,Ni,Nj,Nk,Dx,Dy,Dz,StepW,Px,Py,Pz,Pi,Pj,Pk,n,Ei,Ej,Ek)
      Sx, Sy, Sz defines the scan start point
      Si, Sj, Sk defines the surface direction in the start point
      Ni, Nj, Nk defines the normal vector of the scanning plane
      Dx, Dy, Dz defines the scan direction point
      StepW      is the average distance between 2 measured points
      Px, Py, Pz,
      Pi, Pj, Pk Define a plane where the scan stops
      n          Number of through the plane
      Ei, Ej, Ek defines the surface direction at the end point. It defines the direction for retracting
    '''
    return await self.sendCommand("ScanInPlaneEndIsPlane(%s)" % (scanInPlaneEndIsPlaneString), callbacks=callbacks)

  async def scanInPlaneEndIsCyl(self, scanInPlaneEndIsCylString, callbacks=None):
    '''
    Perform a scanning measurement along an unknown contour
    The scan stops if the cylinder stop criterion is matched
    Parameters: (Sx,Sy,Sz,Si,Sj,Sk,Ni,Nj,Nk,Dx,Dy,Dz,StepW,Cx,Cy,Cz,Ci,Cj,Ck,d,n,Ei,Ej,Ek)
      Sx,Sy,Sz   defines the scan start point
      Si,Sj,Sk   defines the surface direction in the start point
      Ni,Nj,Nk   defines the normal vector of the scanning plane
      Dx,Dy,Dz   defines the scan direction point
      StepW      is the average distance between 2 measured points
      Cx,Cy,Cz
      Ci,Cj,Ck,d define a cylinder where the scan stops
      n          Number of through the cylinder
      Ei, Ej, Ek defines the surface vector at the end point. It defines the direction for retracting
    '''
    return await self.sendCommand("ScanInPlaneEndIsCyl(%s)" % (scanInPlaneEndIsCylString), callbacks=callbacks)

  async def scanInCylEndIsSphere(self, scanInCylEndIsSphereString, callbacks=None):
    '''
    Perform a scanning measurement along an unknown contour
    The scan stops if the sphere stop criterion is matched
    Parameters: (Cx,Cy,Cz,Ci,Cj,Ck,Sx,Sy,Sz,Si,Sj,Sk,Dx,Dy,Dz,StepW,Ex,Ey,Ez,Dia,n,Ei,Ej,Ek)
      Cx,Cy,Cz
      Ci,Cj,Ck     defines the axis of the cylinder
      Sx,Sy,Sz     defines the scan start point
      Si,Sj,Sk     defines the surface direction in the start point
      Dx,Dy,Dz     defines the scan direction point
      StepW        is the average distance between 2 measured points
      Ex,Ey,Ez,Dia define a sphere where the scan stops
      n            Number of reaching the stop sphere
      Ei, Ej, Ek   defines the surface at the end point. It defines the direction for retracting
    '''
    return await self.sendCommand("ScanInCylEndIsSphere(%s)" % (scanInCylEndIsSphereString), callbacks=callbacks)

  async def scanInCylEndIsPlane(self, scanInCylEndIsPlaneString, callbacks=None):
    '''
    Perform a scanning measurement along an unknown contour
    The scan stops if the sphere stop criterion is matched
    Parameters: (Cx,Cy,Cz,Ci,Cj,Ck,Sx,Sy,Sz,Si,Sj,Sk,Dx,Dy,Dz,StepW,Px,Py,Pz,Pi,Pj,Pk,n,Ei,Ej,Ek)
      Cx,Cy,Cz
      Ci,Cj,Ck    defines the axis of the cylinder
      Sx,Sy,Sz    defines the scan start point
      Si,Sj,Sk    defines the surface direction in the start point
      Dx,Dy,Dz    defines the scan direction point
      StepW       is the average distance between 2 measured points
      Px, Py, Pz,
      Pi, Pj, Pk  defines the stop plane
      n           number of through stop plane
      Ei, Ej, Ek  defines the surface direction at the end point. It defines the direction for retracting
    '''
    return await self.sendCommand("ScanInCylEndIsPlane(%s)" % (scanInCylEndIsPlaneString), callbacks=callbacks)

