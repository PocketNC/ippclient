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

class CmmException(Exception):
  pass

class TransactionStatus(Enum):
  ERROR = -1
  CREATED = 0
  SENT = 1
  ACK = 2
  COMPLETE = 3

class Transaction:
  def __init__(self):
    self.status = TransactionStatus.CREATED
    self.data = []
    self.errors = []

  def send(self):
    self.status = TransactionStatus.SENT

  def acknowledge(self):
    self.status = TransactionStatus.ACK

  def data(self, data):
    self.data.append(data)

  def error(self, err):
    self.errors.append(err)

  def complete(self):
    self.status = TransactionStatus.COMPLETE

RECEIVE_SIZE = 1024
class Client:
  def __init__(self, host=HOST, port=PORT):
    self.host = host
    self.port = port
    self.tcpClient = TCPClient()
    self.stream = None
    self.nextTag = 1
    self.nextEventTag = 1
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

  async def sendCommand(self, command):
    try:
      logger.debug("Send I++ command %s ", command)
      tag = self.nextTag
      transaction = Transaction()
      self.transactions[tag] = transaction
      message = "%05d %s\r\n" % (tag, command)
      self.nextTag = self.nextTag%99999+1 # Get the next tag between 1 - 99999
      await self.stream.write(message.encode('ascii'))
      transaction.send()
      return tag
    except Exception as e:
      logger.error("sendCommand %s", e)

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


  '''
  I++ Server Methods
  '''
  async def startSession(self):
    await self.sendCommand("EndSession()")
    return await self.sendCommand("StartSession()")

  async def endSession(self):
    endTag = await self.sendCommand("EndSession()")
    self.nextTag = 1
    self.nextEventTag = 1
    return endTag

  async def stopDaemon(self, eventTag):
    return await self.sendCommand("StopDaemon(%s)" % eventTag)

  async def stopAllDaemons(self):
    return await self.sendCommand("StopAllDaemons()")

  async def abortE(self):
    '''
    Fast Queue command
    '''
    return await self.sendEventCommand("AbortE()")

  async def getErrorInfo(self, errNum=None):
    return await self.sendCommand("GetErrorInfo(%s)" % str(errNum or ''))

  async def clearAllErrors(self):
    return await self.sendCommand("ClearAllErrors()")

  async def getProp(self, propArr):
    propsString = ", ".join(propArr)
    return await self.sendCommand("GetProp(%s)" % propsString)

  async def getPropE(self, propArr):
    '''
    Fast Queue command
    '''
    propsString = ", ".join(propArr)
    return await self.sendEventCommand("GetPropE(%s)" % propsString)

  async def setProp(self, propArr):
    propsString = ", ".join(propArr)
    return await self.sendCommand("SetProp(%s)" % propsString)

  
  async def enumProp(self, pointerString):
    '''
    Get the list of properties for a system object
    For example, "EnumProp(Tool.PtMeasPar())" will return 
    the active tool's PtMeas properties list
    '''
    return await self.sendCommand("EnumProp(%s)" % pointerString)

  async def enumAllProp(self, pointerString):
    '''
    Get the entire tree of properties and sub-properties for a system object
    '''
    return await self.sendCommand("EnumAllProp(%s)" % pointerString)

  async def getDMEVersion(self):
    return await self.sendCommand("GetDMEVersion()")


  '''
  I++ DME Methods
  '''
  async def home(self):
    return await self.sendCommand("Home()")

  async def isHomed(self):
    return await self.sendCommand("IsHomed()")

  async def enableUser(self):
    return await self.sendCommand("EnableUser()")

  async def disableUser(self):
    return await self.sendCommand("DisableUser()")

  async def isUserEnabled(self):
    return await self.sendCommand("IsUserEnabled()")

  async def onPtMeasReport(self, ptMeasFormatString):
    '''
    Define the information reported in the result of a PtMeas command
    '''
    return await self.sendCommand("OnPtMeasReport(%s)" % ptMeasFormatString)

  async def onMoveReportE(self, onMoveReportFormatString):
    '''
    Fast Queue command
    Start a daemon that reports machine movement, and define
    which information is sent (sequence and contents)
    '''
    return await self.sendEventCommand("OnMoveReportE(%s)" % onMoveReportFormatString)

  async def getMachineClass(self):
    return await self.sendCommand("GetMachineClass()")

  async def getErrStatusE(self):
    '''
    Fast Queue command
    Response is "ErrStatus(1)" if in error
    Response is "ErrStatus(0)" if ok
    '''
    return await self.sendEventCommand("GetErrStatusE()")

  async def getXtdErrStatus(self):
    '''
    Response is one or more lines of status information
    Could also include one or more errors
    Example:
      IsHomed(1)
      IsUserEnabled(0)
      1009: Air Pressure Out Of Range
      0512: No Daemons Are Active.
    '''
    return await self.sendCommand("GetXtdErrStatus()")

  async def get(self, queryString):
    '''
    Query tool position
    queryString example:
      "X(), Y(), Z(), Tool.A(), Tool.B()"
    '''
    return await self.sendCommand("Get(%s)" % queryString)

  async def goTo(self, positionString):
    '''
    Move to a target position, including tool rotation
    '''
    return await self.sendCommand("GoTo(%s)" % positionString)

  async def ptMeas(self, ptMeasString):
    '''
    Execute a single point measurement
    Necessary parameters are defined by the active tool
    Return format is set by OnPtMeasReport
    Errors if surface not found (Error 1006: Surface not Found)
    '''
    return await self.sendCommand("PtMeas(%s)" % ptMeasString)

  # See examples 7.6 and 7.7 in IDME specification for tool handling examples
  async def tool(self):
    '''
    Select a pointer to the active tool
    '''
    return await self.sendCommand("Tool()")

  async def findTool(self, toolName):
    '''
    Select a pointer to a tool with a known name
    '''
    return await self.sendCommand("FindTool(%s)" % toolName)
  
  async def foundTool(self):
    '''
    Acts as pointer to tool selected by FindTool command
    Default pointer is "UnDefTool" 
    '''
    return await self.sendCommand("FoundTool()")

  async def changeTool(self, toolName):
    '''
    Perform a tool change
    '''
    return await self.sendCommand("ChangeTool(%s)" % toolName)

  async def setTool(self, toolName):
    '''
    Force the server to assume a given tool is the active tool
    '''
    return await self.sendCommand("SetTool(%s)" % toolName)

  async def alignTool(self, alignToolString):
    '''
    Orientate an alignable tool
    '''
    return await self.sendCommand("AlignTool(%s)" % alignToolString)

  async def goToPar(self):
    '''
    This method acts as a pointer to the GoToParameter block of the DME
    '''
    return await self.sendCommand("GoToPar()")

  async def prMeasPar(self):
    '''
    This method acts as a pointer to the PtMeasParameter block of the DME
    '''
    return await self.sendCommand("PtMeasPar()")

  async def enumTools(self):
    '''
    Returns a list of the names of available tools
    '''
    return await self.sendCommand("enumTools()")

  async def getChangeToolAction(self, toolName):
    '''
    Query the necessary movement to change to a given tool
    '''
    return await self.sendCommand("GetChangeToolAction(%s)" % toolName)

  async def enumToolCollection(self, collectionName):
    '''
    Query the names and types of tools (or child collections) belonging to a collection
    '''
    return await self.sendCommand("EnumToolCollection(%s)" % collectionName)

  async def enumAllToolCollections(self, collectionName):
    '''
    Recursively return all tools and sub-collections to this collection
    '''
    return await self.sendCommand("EnumToolCollection(%s)" % collectionName)

  async def openToolCollection(self, collectionName):
    '''
    Make all tools in referenced collection visible, meaning a ChangeTool command can
    directly use names in the collection without a path extension
    '''
    return await self.sendCommand("EnumToolCollection(%s)" % collectionName)

  async def ijkAct(self):
    '''
    Query the meaning of server IJK() values: actual measured normal, nominal, or tool alignment
    '''
    return await self.sendCommand("IJKAct()")

  async def ptMeasSelfCenter(self, ptMeasSelfCenterString):
    '''
    Execute a single point measurement by self-centering probing
    Necessary parameters defined by the active tool
    '''
    return await self.sendCommand("PtMeasSelfCenter(%s)" % ptMeasSelfCenterString)

  async def ptMeasSelfCenterLocked(self, ptMeasSelfCenterString):
    '''
    Execute a single point measurement by self-centering probing
    without leaving a plane defined by params
    Necessary parameters defined by the active tool
    '''
    return await self.sendCommand("PtMeasSelfCenter(%s)" % ptMeasSelfCenterString)

  async def readAllTemperatures(self):
    return await self.sendCommand("ReadAllTemperatures()")


  '''
  I++ CartCMM Methods
  '''
  async def setCoordSystem(self, coodSystemString):
    '''
    Arg is one of: MachineCsy, MoveableMachineCsy, MultipleArmCsy, RotaryTableVarCsy, PartCsy
    '''
    return await self.sendCommand("SetCoordSystem(%s)" % coodSystemString)

  async def getCoordSystem(self):
    '''
    Query which coord sys is selected
    '''
    return await self.sendCommand("GetCoordSystem()")

  async def getCsyTransformation(self, getCsyTransformationString):
    return await self.sendCommand("GetCsyTransformation(%s)" % getCsyTransformationString)

  async def setCsyTransformation(self, setCsyTransformationString):
    return await self.sendCommand("SetCsyTransformation(%s)" % setCsyTransformationString)

  async def saveActiveCoordSystem(self, csyName):
    return await self.sendCommand("SaveActiveCoordSystem(%s)" % csyName)

  async def loadCoordSystem(self, csyName):
    return await self.sendCommand("LoadCoordSystem(%s)" % csyName)
    
  async def deleteCoordSystem(self, csyName):
    return await self.sendCommand("DeleteCoordSystem(%s)" % csyName)

  async def enumCoordSystem(self, name):
    return await self.sendCommand("EnumCoordSystem()")

  async def getNamedCsyTransformation(self, csyName):
    return await self.sendCommand("GetNamedCsyTransformation(%s)" % csyName)
  
  async def saveNamedCsyTransformation(self, csyName, csyCoordsString):
    return await self.sendCommand("SaveNamedCsyTransformation(%s, %s)" % (csyName, csyCoordsStsring))


  '''
  I++ Tool Methods
  '''
  async def reQualify(self):
    '''
    Requalify active tool
    '''
    return await self.sendCommand("ReQualify()")

  async def scanPar(self):
    '''
    Acts as a pointer to the ScanParameter block of KTool instance
    '''
    return await self.sendCommand("ScanPar()")

  async def avrRadius(self):
    '''
    Return average tip radius of selected tool
    '''
    return await self.sendCommand("AvrRadius()")

  async def isAlignable(self):
    '''
    Query if selected tool is alignable
    '''
    return await self.sendCommand("IsAlignable()")

  async def alignment(self, alignmentVectorString):
    '''
    Query if selected tool is alignable
    '''
    return await self.sendCommand("Alignment(%s)" % alignmentVectorString)

  async def calcToolAlignment(self, calcToolAlignmentString):
    '''
    Query the alignment of selected tool
    '''
    return await self.sendCommand("CalcToolAlignment(%s)" % calcToolAlignmentString)

  async def calcToolAngles(self, calcToolAnglesString):
    '''
    Query the alignment of selected tool
    '''
    return await self.sendCommand("CalcToolAngles(%s)" % calcToolAnglesString)

  async def useSmallestAngleToAlignTool(self, enabled):
    '''
    Param is 0 or 1
    When enabled with CalcToolAngles(1), attempting to rotate the tool by
    180 degrees or more will produce an error
    '''
    return await self.sendCommand("CalcToolAngles(%s)" % calcToolAnglesString)

  '''
  I++ Scanning Methods
  '''
  async def onScanReport(self, onScanReportString):
    '''
    Define the format of scan reports
    '''
    return await self.sendCommand("OnScanReport(%s)" % onScanReportString)

  async def scanOnCircleHint(self, displacement, form):
    '''
    Optimize ScanOnCircle execution by defining expected deviation from nominal of the measured circle
    '''
    return await self.sendCommand("ScanOnCircleHint(%s, %s)" % (displacement, form))

  async def scanOnCircle(self, scanOnCircleString):
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
    return await self.sendCommand("ScanOnCircle(%s)" % (scanOnCircleString))

  async def scanOnLineHint(self, angle, form):
    '''
    Optimize ScanOnLine execution by defining expected deviation from nominal of the measured line
    '''
    return await self.sendCommand("ScanOnLineHint(%s, %s)" % (angle, form))

  async def scanOnLine(self, scanOnLineString):
    '''
    Perform a scanning measurement on a circular 
    Parameters: (Sx,Sy,Sz,Ex,Ey,Ez,i,j,k,StepW)
      Sx, Sy, Sz defines the line start point
      Ex, Ey, Ez defines the line end point
      i,j,k      is the surface normal vector on the line
      StepW      average distance between 2 measured points in mm
    '''
    return await self.sendCommand("ScanOnLine(%s)" % (scanOnLineString))

  async def scanOnCurveHint(self, deviation, minRadiusOfCurvature):
    '''
    Optimize ScanOnCurve execution by defining expected deviation from nominal of the measured curve
    '''
    return await self.sendCommand("ScanOnCurveHint(%s, %s)" % (deviation, minRadiusOfCurvature))
  
  async def scanOnCurveDensity(self, scanOnCurveDensityString):
    '''
    Define density of points returned from server by ScanOnCurve execution
    Parameters: (Dis(),Angle(),AngleBaseLength(),AtNominals())
      Dis()             Maximum distance of 2 points returned
      Angle()           Maximum angle between the 2 segments between the last 3 points
      AngleBaseLength() Baselength for calculating the Angle criteria (necessary for small point distances)
      AtNominals()      Boolean 0 or 1. If 1 the arguments Dis() and Angle() are ignored
      
      Dis() or/and AtNominals() without Angle() and AngleBaseLength() also possible.
    '''
    return await self.sendCommand("ScanOnCurveDensity(%s)" % (scanOnCurveDensityString))

  async def scanOnCurve(self, scanOnCurveString):
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
    return await self.sendCommand("ScanOnCurve(%s)" % (scanOnCurveString))

  async def scanOnHelix(self, scanOnHelixString):
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
    return await self.sendCommand("ScanOnHelix(%s)" % (scanOnHelixString))

  async def scanUnknownHint(self, minRadiusOfCurvature):
    '''
    Define expected minimum radius of curvature during scan of unknown contour
    '''
    return await self.sendCommand("ScanUnknownHint(%s)" % (minRadiusOfCurvature))

  async def scanUnknownDensity(self, scanUnknownDensityString):
      '''
      Define density of points returned from server by ScanUnknown execution
      Parameters: (Dis(),Angle(),AngleBaseLength())
        Dis()             Maximum distance of 2 points returned
        Angle()           Maximum angle between the 2 segments defined by AngleBaseLength()
        AngleBaseLength() Baselength for calculating the Angle criteria (necessary for small point distances)

        Dis() without Angle() and AngleBaseLength() possible.
      '''
      return await self.sendCommand("ScanUnknownDensity(%s)" % (scanUnknownDensityString))

  async def scanInPlaneEndIsSphere(self, scanInPlaneEndIsSphereString):
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
    return await self.sendCommand("ScanInPlaneEndIsSphere(%s)" % (scanInPlaneEndIsSphereString))

  async def scanInPlaneEndIsPlane(self, scanInPlaneEndIsPlaneString):
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
    return await self.sendCommand("ScanInPlaneEndIsPlane(%s)" % (scanInPlaneEndIsPlaneString))

  async def scanInPlaneEndIsCyl(self, scanInPlaneEndIsCylString):
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
    return await self.sendCommand("ScanInPlaneEndIsCyl(%s)" % (scanInPlaneEndIsCylString))

  async def scanInCylEndIsSphere(self, scanInCylEndIsSphereString):
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
    return await self.sendCommand("ScanInCylEndIsSphere(%s)" % (scanInCylEndIsSphereString))

  async def scanInCylEndIsPlane(self, scanInCylEndIsPlaneString):
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
    return await self.sendCommand("ScanInCylEndIsPlane(%s)" % (scanInCylEndIsPlaneString))

