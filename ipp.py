"""
An I++ client implemented in python using asycio async/await syntax.
"""
import socket
import sys
from enum import Enum
import time
import asyncio
import logging
import tornado
from tornado.ioloop import IOLoop
from tornado.tcpclient import TCPClient
from tornado.iostream import StreamClosedError
from dataclasses import dataclass
import math
import functools
import traceback
import numpy as np
from scipy.spatial.transform import Rotation

logger = logging.getLogger(__name__)

RECEIVE_SIZE = 1024

HOST = "10.0.0.1"
PORT = 1294

IPP_ACK_CHAR = "&"
IPP_COMPLETE_CHAR = "%"
IPP_DATA_CHAR = "#"
IPP_ERROR_CHAR = "!"

status = 0

class float3:
  def __init__(self, *args):
    if len(args)==0: 
      self.values = (0,0,0)
    elif len(args)==1:
      if hasattr(args[0], '__iter__'):
        self.values = tuple([ i for i in args[0] ])
      else:
        logger.debug("failed to create values")
        raise ValueError("Invalid args {} for float3".format(args))
    elif len(args) == 3:
      self.values = args
    else: 
      raise ValueError("Invalid args {} for float3".format(args))

    self.x = self.values[0]
    self.y = self.values[1]
    self.z = self.values[2]


  def __array__(self, dtype=None):
      if dtype:
          return np.array([self.x, self.y, self.z], dtype=dtype)
      else:
          return np.array([self.x, self.y, self.z])
  
  def __sub__(self, other):
    """ Returns the vector difference of self and other """
    if isinstance(other, float3):
      subbed = float3(self.x-other.x,self.y-other.y,self.z-other.z)
    elif isinstance(other, (int, float)):
      subbed = float3( list(a - other for a in self) )
    else:
        raise ValueError("Subtraction with type {} not supported".format(type(other)))
    return self.__class__(*subbed)
  def __rsub__(self, other):
      return self.__sub__(other)

  def __add__(self, other):
    """ Returns the vector addition of self and other """
    if isinstance(other, float3):
      added = float3(other.x+self.x,other.y+self.y,other.z+self.z)
    elif isinstance(other, (int, float)):
      added = float3( list(a + other for a in self) )
    else:
      raise ValueError("Addition with type {} not supported".format(type(other)))
    return added
  def __radd__(self, other):
    return self.__add__(other)

  def __mul__(self,other):
    if isinstance(other, float3):
      product = float3(other.x * self.x,other.y * self.y,other.z * self.z)
      return product
    elif isinstance(other, (int, float)):
      product = float3(self.x*other, self.y*other, self.z*other)
      return product
    else:
      raise ValueError("Multiplication with type {} not supported".format(type(other)))
  def __rmul__(self, other):
      """ Called if 4 * self for instance """
      return self.__mul__(other)
  def norm(self):
        """ Returns the norm (length, magnitude) of the vector """
        return math.sqrt(sum( x*x for x in self ))
  def normalize(self):
        """ Returns a normalized unit vector """
        norm = self.norm()
        normed = tuple( x / norm for x in self )
        return self.__class__(*normed)
  def __iter__(self):
    for val in [self.x,self.y,self.z]:
      yield val
  def __repr__(self):
        return str(self.values)

  def inner(self, vector):
    """ Returns the dot product (inner product) of self and another vector
    """
    if not isinstance(vector, float3):
      raise ValueError('The dot product requires another vector')
    return sum(a * b for a, b in zip(self, vector))
  
  def ToXYZString(self):
    return "X(%s), Y(%s), Z(%s)" % (self.x, self.y, self.z)
  
  @classmethod
  def FromXYZString(cls, xyzString):
    x = float(xyzString[xyzString.find("X(") + 2 : xyzString.find("), Y")])
    y = float(xyzString[xyzString.find("Y(") + 2 : xyzString.find("), Z")])
    z = float(xyzString[xyzString.find("Z(") + 2 : xyzString.rfind(")")])
    return cls(x,y,z)

  def ToIJKString(self):
    return "IJK(%s,%s,%s)" % (self.x, self.y, self.z)

# I++ documentation mentions zxz rotation order in an example and 
# experimentation has shown it work. 
ORDER = 'zxz'
class Csy:
  def __init__(self, x,y,z,theta,psi,phi):
    """
    Parameters are in the same order as they are passed to I++'s SetCsyTransform.
    Note that the order of the angles is different than the order they are passed 
    in to perform euler angle calculations.
    """
    self.x = x
    self.y = y
    self.z = z
    self.theta = theta
    self.psi = psi
    self.phi = phi

  def toMatrix4(self):
    r = Rotation.from_euler(ORDER, (self.phi, self.theta, self.psi), degrees=True)

    # Convert rotation to 3x3 matrix
    mat3 = r.as_matrix()

    # Initialize empty 4x4 matrix
    mat4 = np.empty((4,4))

    # Copy 3x3 rotation matrix into top left of 4x4 matrix
    mat4[:3,:3] = mat3

    # Populate the translation portion of the 4x4 matrix with the origin
    mat4[:3,3] = (self.x, self.y, self.z)

    # Fill in the homogenous coordinates
    mat4[3,:] = [0,0,0,1]

    return mat4

  def fromMatrix4(mat4):
    # Extract the 3x3 rotation matrix from the 4x4 matrix
    mat3 = mat4[0:3, 0:3]

    # Create a rotation object with rotation matrix
    r = Rotation.from_matrix(mat3)

    # Convert rotation to euler angles
    (phi, theta, psi) = r.as_euler(ORDER, degrees=True)

    # Extract the origin from the translation components of 4x4 matrix
    x = mat4[0][3]
    y = mat4[1][3]
    z = mat4[2][3]

    return Csy(x,y,z,theta,psi,phi)

def readPointData(data):
  logger.debug("read point data %s" % data)
  x = float(data[data.find("X(") + 2 : data.find("), Y")])
  y = float(data[data.find("Y(") + 2 : data.find("), Z")])
  z = float(data[data.find("Z(") + 2 : data.rfind(")")])
  pt = float3(x,y,z)
  return pt


async def noop(args=None):
  pass

async def setEvent(event):
  logger.debug("setting event")
  event.set()

async def waitForEvent(event):
  await event.wait()

def gotError():
  raise CmmException()

async def setFutureException(fut,msg):
  logger.debug("setFutureException %s" % msg)
  if not fut.done():
    fut.set_exception(CmmException(msg))

async def setFutureResult(fut,val):
  if not fut.done():
    fut.set_result(val)

async def futureWaitForCommandComplete(cmd, *args):
  loop = asyncio.get_running_loop()
  fut = loop.create_future()
  obj = {}
  callbacks = TransactionCallbacks(complete=(lambda: setFutureResult(fut,obj)), error=(lambda: setFutureException(fut,"boo")))
  await cmd(*args, callbacks=callbacks)
  logger.debug("awaiting fut")
  r = await fut
  logger.debug("Future resolved %s" % r)

async def waitForCommandComplete(cmd, *args, otherCallbacks=None):
  cmdCompleted = asyncio.Event()
  waitTask = asyncio.create_task(waitForEvent(cmdCompleted))
  logger.debug(otherCallbacks)
  if otherCallbacks:
    callbacks = TransactionCallbacks(complete=(lambda: setEvent(cmdCompleted)), **otherCallbacks)
  else:
    callbacks = TransactionCallbacks(complete=(lambda: setEvent(cmdCompleted)))
  logger.debug(callbacks.complete)
  await cmd(*args, callbacks=callbacks)
  await waitTask


class CmmException(Exception):
  pass
class CmmExceptionUnexpectedCollision(CmmException):
  pass
class CmmExceptionErrorsPresent(CmmException):
  pass
class CmmExceptionAxisLimit(CmmException):
  pass
class CmmExceptionUnknownCommand(CmmException):
  pass


class TransactionStatus(Enum):
  ERROR = -1
  CREATED = 0
  SENT = 1
  ACK = 2
  COMPLETE = 3


class TransactionCallbacks:
  # def __init__(self, send, ack, complete, data, error):
  def __init__(self):
    self.send = []
    self.ack = []
    self.complete = []
    self.data = []
    self.error = []


class StandardTransactionCallbacks(TransactionCallbacks):
  def __init__(self, future):
    self.send = None
    self.ack = None
    self.complete = (lambda: setFutureResult(fut,data))
    self.data = data
    self.error = (lambda msg: setFutureException(fut,msg))


class Callbacks:
  def __init__(self,transaction):
    self.transaction = transaction

  def send(self):
    self.transaction.status = TransactionStatus.SENT
    if self.transaction.custom_callbacks.send is not None:
      self.transaction.custom_callbacks.send()

  def ack(self):
    self.transaction.status = TransactionStatus.ACK

  def data(self):
    self.transaction.data = TransactionStatus.SENT

  def error(self):
    self.transaction.error = TransactionStatus.ERROR

  def complete(self):
    self.transaction.complete = TransactionStatus.COMPLETE


class Transaction:
  def __init__(self, tag, cmd):
    self.status = TransactionStatus.CREATED
    self.tag = tag
    self.data_list = []
    self.error_list = []
    self.futures = {}
    self.sendTask = None
    self.command = cmd
    self.fut = None
    self.callbacks = TransactionCallbacks()

  def register_callback(self, event, callback, once):
    try:
      getattr(self.callbacks, event).append({'callback': callback, 'once': once})
    except AttributeError as err:
      return err

  def clear_callbacks(self, event=None):
    if event is not None:
      setattr(self.callbacks, event, [])
    else:
      self.callbacks = TransactionCallbacks()

  def _std_event_callback(self, key):
    loop = asyncio.get_running_loop()
    fut = loop.create_future()
    def callback(transaction, isError=False):
      self.fut = None
      fut.set_result(transaction)
    def error_callback(transaction, isError=False):
      self.fut = None
      fut.set_exception(CmmException("".join(transaction.error_list)))
    self.register_callback(key, callback, True)
    self.register_callback('error', error_callback, True)

    self.fut = fut

    if self.sendCoro:
      sendCoro = self.sendCoro
      async def mycoro():
        await sendCoro
        return await fut

      self.sendCoro = None
      return asyncio.create_task(mycoro())
    else:
      return fut


  def _process_event_callbacks(self, event, isError=False):
    eventCallbacks = getattr(self.callbacks, event)
    repeatCallbacks = []
    for cb in eventCallbacks:
      func = cb['callback']
      func(self, isError)
      if not cb['once']:
        repeatCallbacks.append(cb)
    setattr(self.callbacks, event, repeatCallbacks)

  def send(self):
    return self._std_event_callback("send")

  def ack(self):
    logger.debug("creating ack future for message %s", self.tag)
    return self._std_event_callback("ack")

  def complete(self):
    logger.debug("creating complete future for message %s", self.tag)
    return self._std_event_callback("complete")

  def data(self):
    logger.debug("creating data future for message %s", self.tag)
    return self._std_event_callback("data")

  def error(self):
    logger.debug("creating error future for message %s", self.tag)
    return self._std_event_callback("error")

  def handle_send(self):
    logger.debug("handling send for message %s", self.tag)
    self.status = TransactionStatus.SENT
    self._process_event_callbacks('send')

  def handle_ack(self):
    logger.debug("handling ack for message %s", self.tag)
    self.status = TransactionStatus.ACK
    self._process_event_callbacks('ack')

  def handle_data(self, data_msg):
    logger.debug("handling data for message %s", self.tag)
    self.data_list.append(data_msg)
    self._process_event_callbacks('data')

  def handle_error(self, err_msg):
    logger.debug("handling error for message %s", self.tag)
    self.status = TransactionStatus.ERROR
    self.error_list.append(err_msg)
    self._process_event_callbacks('error', True)

  def handle_complete(self):
    logger.debug("handling complete for message %s", self.tag)
    self.status = TransactionStatus.COMPLETE
    self._process_event_callbacks('complete')


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
    self.points = []

  def is_connected(self):
    return not self.stream.closed() if self.stream else False

  async def connect(self):
    print(tornado.version)
    try:
      logger.debug('connecting')
      self.stream = await self.tcpClient.connect(self.host, self.port, timeout=3.0)
      logger.debug('connected %s' % (self.stream,))
      
      self.listenerTask = asyncio.create_task(self.handleMessages())
      return True
    except Exception as e:
      logger.error("connect error %s", traceback.format_exc())
      raise e

  async def disconnect(self):
    try:
      if self.stream is not None:
        self.stream.close()
    except Exception as e:
      logger.error("disconnect error %s", traceback.format_exc())
      raise e

  def sendCommand(self, command, isEvent=False):
    try:
      if isEvent:
        tagNum = self.nextEventTagNum
        tag = "E%04d" % eventTagNum 
        self.nextEventTagNum = self.nextEventTagNum%9999+1 # Get the next event tag between 1 - 9999
      else:
        tagNum = self.nextTagNum
        tag = "%05d" % tagNum 
        self.nextTagNum = self.nextTagNum%99999+1 # Get the next tag between 1 - 99999

      logger.debug("sendCommand %s, tag %s " % (command, tag))
        
      transaction = Transaction(tag, command)
      self.transactions[tag] = transaction
      
      transaction.sendCoro = self._coro_send_command(transaction)
      return transaction
    except Exception as e:
      logger.error(e)
      raise e

  async def _coro_send_command(self, transaction):
    message = "%s %s\r\n" % (transaction.tag, transaction.command)
    try:
      await asyncio.wait_for(self.stream.write(message.encode('ascii')), 3.0)
    except asyncio.TimeoutError as e:
      logger.debug("Timeout!")
      loop = asyncio.get_running_loop()
      loop.stop()
      raise e
    transaction.handle_send()

  async def readMessage(self):
    msg = await self.stream.read_until(b"\r\n")
    msg = msg.decode("ascii")
    return msg

  async def handleMessages(self, stopTag=None, stopKey=None):
    '''
    Run this in a coroutine
    '''
    logger.debug("started handling messages")
    try:
      while True:
        msg = await self.readMessage()
        logger.debug("handleMessage: %s" % msg)
        msgTag = msg[0:5]
        responseKey = msg[6]
        if msgTag in self.transactions:
          transaction = self.transactions[msgTag]
          if transaction.status != TransactionStatus.ERROR:
            if responseKey == IPP_ACK_CHAR:
              transaction.handle_ack()
            elif responseKey == IPP_COMPLETE_CHAR:
              transaction.handle_complete()
            elif responseKey == IPP_DATA_CHAR:
              transaction.handle_data(msg)
            elif responseKey == IPP_ERROR_CHAR:
              for t in self.transactions.values():
                if t.fut:
                  t.handle_error(msg)
        else:
          logger.debug("%s NOT in transactions dict" % msgTag)
    except StreamClosedError:
      pass



  '''
  I++ Server Methods
  '''
  def StartSession(self):
    return self.sendCommand("StartSession()")

  def EndSession(self):
    endTransaction = self.sendCommand("EndSession()")
    self.nextTag = 1
    self.nextEventTag = 1
    return endTransaction

  def StopDaemon(self, eventTag):
    return self.sendCommand("StopDaemon(%s)" % eventTag)

  def StopAllDaemons(self):
    return self.sendCommand("StopAllDaemons()")

  def AbortE(self):
    '''
    Fast Queue command
    '''
    return self.sendCommand("AbortE()", isEvent=True)

  def GetErrorInfo(self, errNum=None):
    return self.sendCommand("GetErrorInfo(%s)" % str(errNum or ''))

  def ClearAllErrors(self):
    return self.sendCommand("ClearAllErrors()")

  def GetProp(self, propArr):
    propsString = ", ".join(propArr)
    return self.sendCommand("GetProp(%s)" % propsString)

  def GetPropE(self, propArr):
    '''
    Fast Queue command
    '''
    propsString = ", ".join(propArr)
    return self.sendCommand("GetPropE(%s)" % propsString, isEvent=true)

  def SetProp(self, setPropString):
    return self.sendCommand("SetProp(%s)" % setPropString)
  
  def EnumProp(self, pointerString):
    '''
    Get the list of properties for a system object
    For example, "EnumProp(Tool.PtMeasPar())" will return 
    the active tool's PtMeas properties list
    '''
    return self.sendCommand("EnumProp(%s)" % pointerString)

  def EnumAllProp(self, pointerString):
    '''
    Get the entire tree of properties and sub-properties for a system object
    '''
    return self.sendCommand("EnumAllProp(%s)" % pointerString)

  def GetDMEVersion(self):
    return self.sendCommand("GetDMEVersion()")



  '''
  I++ DME Methods
  '''
  def Home(self):
    return self.sendCommand("Home()")

  def IsHomed(self):
    return self.sendCommand("IsHomed()")

  def EnableUser(self):
    return self.sendCommand("EnableUser()")

  def DisableUser(self):
    return self.sendCommand("DisableUser()")

  def IsUserEnabled(self):
    return self.sendCommand("IsUserEnabled()")

  def OnPtMeasReport(self, ptMeasFormatString):
    '''
    Define the information reported in the result of a PtMeas command
    '''
    return self.sendCommand("OnPtMeasReport(%s)" % ptMeasFormatString)

  def OnMoveReportE(self, onMoveReportFormatString):
    '''
    Fast Queue command
    Start a daemon that reports machine movement, and define
    which information is sent (sequence and contents)
    '''
    return self.sendCommand("OnMoveReportE(%s)" % onMoveReportFormatString, isEvent=True)

  def GetMachineClass(self):
    return self.sendCommand("GetMachineClass()")

  def GetErrStatusE(self):
    '''
    Fast Queue command
    Response is "ErrStatus(1)" if in error
    Response is "ErrStatus(0)" if ok
    '''
    return self.sendCommand("GetErrStatusE()", isEvent=true)

  def GetXtdErrStatus(self):
    '''
    Response is one or more lines of status information
    Could also include one or more errors
    Example:
      IsHomed(1)
      IsUserEnabled(0)
      1009: Air Pressure Out Of Range
      0512: No Daemons Are Active.
    '''
    return self.sendCommand("GetXtdErrStatus()")

  def Get(self, queryString):
    '''
    Query tool position
    queryString example:
      "X(), Y(), Z(), Tool.A(), Tool.B()"
    '''
    return self.sendCommand("Get(%s)" % queryString)

  def GoTo(self, positionString):
    '''
    Move to a target position, including tool rotation
    '''
    return self.sendCommand("GoTo(%s)" % positionString)


  async def sendPtMeas(self, ptMeasString):
    await self.sendCommand("PtMeas(%s)" % ptMeasString)


  def PtMeas(self, ptMeasString):
    '''
    Execute a single point measurement
    Necessary parameters are defined by the active tool
    Return format is set by OnPtMeasReport
    Errors if surface not found (Error 1006: Surface not Found)
    '''
    cmdString = "PtMeas(%s)" % ptMeasString
    return self.sendCommand(cmdString)

  # See examples 7.6 and 7.7 in IDME specification for tool handling examples
  def Tool(self):
    '''
    Select a pointer to the active tool
    '''
    return self.sendCommand("Tool()")

  def FindTool(self, toolName):
    '''
    Select a pointer to a tool with a known name
    '''
    return self.sendCommand("FindTool(%s)" % toolName)
  
  def FoundTool(self):
    '''
    Acts as pointer to tool selected by FindTool command
    Default pointer is "UnDefTool" 
    '''
    return self.sendCommand("FoundTool()")

  def ChangeTool(self, toolName):
    '''
    Perform a tool change
    '''
    return self.sendCommand('ChangeTool("%s")' % toolName)

  def SetTool(self, toolName):
    '''
    Force the server to assume a given tool is the active tool
    '''
    return self.sendCommand("SetTool(\"%s\")" % toolName)

  def AlignTool(self, alignToolString):
    '''
    Orientate an alignable tool
    '''
    return self.sendCommand("AlignTool(%s)" % alignToolString)

  def GoToPar(self):
    '''
    This method acts as a pointer to the GoToParameter block of the DME
    '''
    return self.sendCommand("GoToPar()")

  def PtMeasPar(self):
    '''
    This method acts as a pointer to the PtMeasParameter block of the DME
    '''
    return self.sendCommand("PtMeasPar()")

  def EnumTools(self):
    '''
    Returns a list of the names of available tools
    '''
    return self.sendCommand("enumTools()")

  def GetChangeToolAction(self, toolName):
    '''
    Query the necessary movement to change to a given tool
    '''
    return self.sendCommand("GetChangeToolAction(%s)" % toolName)

  def EnumToolCollection(self, collectionName):
    '''
    Query the names and types of tools (or child collections) belonging to a collection
    '''
    return self.sendCommand("EnumToolCollection(%s)" % collectionName)

  def EnumAllToolCollections(self, collectionName):
    '''
    Recursively return all tools and sub-collections to this collection
    '''
    return self.sendCommand("EnumToolCollection(%s)" % collectionName)

  def OpenToolCollection(self, collectionName):
    '''
    Make all tools in referenced collection visible, meaning a ChangeTool command can
    directly use names in the collection without a path extension
    '''
    return self.sendCommand("EnumToolCollection(%s)" % collectionName)

  def IjkAct(self):
    '''
    Query the meaning of server IJK() values: actual measured normal, nominal, or tool alignment
    '''
    return self.sendCommand("IJKAct()")

  def PtMeasSelfCenter(self, ptMeasSelfCenterString):
    '''
    Execute a single point measurement by self-centering probing
    Necessary parameters defined by the active tool
    '''
    return self.sendCommand("PtMeasSelfCenter(%s)" % ptMeasSelfCenterString)

  def PtMeasSelfCenterLocked(self, ptMeasSelfCenterString):
    '''
    Execute a single point measurement by self-centering probing
    without leaving a plane defined by params
    Necessary parameters defined by the active tool
    '''
    return self.sendCommand("PtMeasSelfCenter(%s)" % ptMeasSelfCenterString)

  def ReadAllTemperatures(self):
    return self.sendCommand("ReadAllTemperatures()")



  '''
  I++ CartCMM Methods
  '''
  def SetCoordSystem(self, coodSystemString):
    '''
    Arg is one of: MachineCsy, MoveableMachineCsy, MultipleArmCsy, RotaryTableVarCsy, PartCsy
    '''
    return self.sendCommand("SetCoordSystem(%s)" % coodSystemString)

  def GetCoordSystem(self):
    '''
    Query which coord sys is selected
    '''
    return self.sendCommand("GetCoordSystem()")

  def GetCsyTransformation(self, getCsyTransformationString):
    return self.sendCommand("GetCsyTransformation(%s)" % getCsyTransformationString)

  def SetCsyTransformation(self, setCsyTransformationString):
    return self.sendCommand("SetCsyTransformation(%s)" % setCsyTransformationString)

  def SaveActiveCoordSystem(self, csyName):
    return self.sendCommand("SaveActiveCoordSystem(%s)" % csyName)

  def LoadCoordSystem(self, csyName):
    return self.sendCommand("LoadCoordSystem(%s)" % csyName)
    
  def DeleteCoordSystem(self, csyName):
    return self.sendCommand("DeleteCoordSystem(%s)" % csyName)

  def EnumCoordSystem(self, name):
    return self.sendCommand("EnumCoordSystem()")

  def GetNamedCsyTransformation(self, csyName):
    return self.sendCommand("GetNamedCsyTransformation(%s)" % csyName)
  
  def SaveNamedCsyTransformation(self, csyName, csyCoordsString):
    return self.sendCommand("SaveNamedCsyTransformation(%s, %s)" % (csyName, csyCoordsStsring))



  '''
  I++ Tool Methods
  '''
  def ReQualify(self):
    '''
    Requalify active tool
    '''
    return self.sendCommand("ReQualify()")

  def ScanPar(self):
    '''
    Acts as a pointer to the ScanParameter block of KTool instance
    '''
    return self.sendCommand("ScanPar()")

  def AvrRadius(self):
    '''
    Return average tip radius of selected tool
    '''
    return self.sendCommand("AvrRadius()")

  def IsAlignable(self):
    '''
    Query if selected tool is alignable
    '''
    return self.sendCommand("IsAlignable()")

  def Alignment(self, alignmentVectorString):
    '''
    Query if selected tool is alignable
    '''
    return self.sendCommand("Alignment(%s)" % alignmentVectorString)

  def CalcToolAlignment(self, calcToolAlignmentString):
    '''
    Query the alignment of selected tool
    '''
    return self.sendCommand("CalcToolAlignment(%s)" % calcToolAlignmentString)

  def CalcToolAngles(self, calcToolAnglesString):
    '''
    Query the alignment of selected tool
    '''
    return self.sendCommand("CalcToolAngles(%s)" % calcToolAnglesString)

  def UseSmallestAngleToAlignTool(self, enabled):
    '''
    Param is 0 or 1
    When enabled with CalcToolAngles(1), attempting to rotate the tool by
    180 degrees or more will produce an error
    '''
    return self.sendCommand("CalcToolAngles(%s)" % calcToolAnglesString)



  '''
  I++ Scanning Methods
  '''
  def OnScanReport(self, onScanReportString):
    '''
    Define the format of scan reports
    '''
    return self.sendCommand("OnScanReport(%s)" % onScanReportString)

  def ScanOnCircleHint(self, displacement, form):
    '''
    Optimize ScanOnCircle execution by defining expected deviation from nominal of the measured circle
    '''
    return self.sendCommand("ScanOnCircleHint(%s, %s)" % (displacement, form))

  def ScanOnCircle(self, scanOnCircleString):
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
    return self.sendCommand("ScanOnCircle(%s)" % (scanOnCircleString))

  def ScanOnLineHint(self, angle, form):
    '''
    Optimize ScanOnLine execution by defining expected deviation from nominal of the measured line
    '''
    return self.sendCommand("ScanOnLineHint(%s, %s)" % (angle, form))

  def ScanOnLine(self, scanOnLineString):
    '''
    Perform a scanning measurement on a circular 
    Parameters: (Sx,Sy,Sz,Ex,Ey,Ez,i,j,k,StepW)
      Sx, Sy, Sz defines the line start point
      Ex, Ey, Ez defines the line end point
      i,j,k      is the surface normal vector on the line
      StepW      average distance between 2 measured points in mm
    '''
    return self.sendCommand("ScanOnLine(%s)" % (scanOnLineString))

  def ScanOnCurveHint(self, deviation, minRadiusOfCurvature):
    '''
    Optimize ScanOnCurve execution by defining expected deviation from nominal of the measured curve
    '''
    return self.sendCommand("ScanOnCurveHint(%s, %s)" % (deviation, minRadiusOfCurvature))
  
  def ScanOnCurveDensity(self, scanOnCurveDensityString):
    '''
    Define density of points returned from server by ScanOnCurve execution
    Parameters: (Dis(),Angle(),AngleBaseLength(),AtNominals())
      Dis()             Maximum distance of 2 points returned
      Angle()           Maximum angle between the 2 segments between the last 3 points
      AngleBaseLength() Baselength for calculating the Angle criteria (necessary for small point distances)
      AtNominals()      Boolean 0 or 1. If 1 the arguments Dis() and Angle() are ignored
      
      Dis() or/and AtNominals() without Angle() and AngleBaseLength() also possible.
    '''
    return self.sendCommand("ScanOnCurveDensity(%s)" % (scanOnCurveDensityString))

  def ScanOnCurve(self, scanOnCurveString):
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
    return self.sendCommand("ScanOnCurve(%s)" % (scanOnCurveString))

  def ScanOnHelix(self, scanOnHelixString):
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
    return self.sendCommand("ScanOnHelix(%s)" % (scanOnHelixString))

  def ScanUnknownHint(self, minRadiusOfCurvature):
    '''
    Define expected minimum radius of curvature during scan of unknown contour
    '''
    return self.sendCommand("ScanUnknownHint(%s)" % (minRadiusOfCurvature))

  def ScanUnknownDensity(self, scanUnknownDensityString):
      '''
      Define density of points returned from server by ScanUnknown execution
      Parameters: (Dis(),Angle(),AngleBaseLength())
        Dis()             Maximum distance of 2 points returned
        Angle()           Maximum angle between the 2 segments defined by AngleBaseLength()
        AngleBaseLength() Baselength for calculating the Angle criteria (necessary for small point distances)

        Dis() without Angle() and AngleBaseLength() possible.
      '''
      return self.sendCommand("ScanUnknownDensity(%s)" % (scanUnknownDensityString))

  def ScanInPlaneEndIsSphere(self, scanInPlaneEndIsSphereString):
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
    return self.sendCommand("ScanInPlaneEndIsSphere(%s)" % (scanInPlaneEndIsSphereString))

  def ScanInPlaneEndIsPlane(self, scanInPlaneEndIsPlaneString):
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
    return self.sendCommand("ScanInPlaneEndIsPlane(%s)" % (scanInPlaneEndIsPlaneString))

  def ScanInPlaneEndIsCyl(self, scanInPlaneEndIsCylString):
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
    return self.sendCommand("ScanInPlaneEndIsCyl(%s)" % (scanInPlaneEndIsCylString))

  def ScanInCylEndIsSphere(self, scanInCylEndIsSphereString):
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
    return self.sendCommand("ScanInCylEndIsSphere(%s)" % (scanInCylEndIsSphereString))

  def ScanInCylEndIsPlane(self, scanInCylEndIsPlaneString):
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
    return self.sendCommand("ScanInCylEndIsPlane(%s)" % (scanInCylEndIsPlaneString))

