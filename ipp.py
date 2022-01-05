import socket
import sys
from enum import Enum

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
  def __init__(self, host, port):
    self.host = host
    self.port = port
    self.nextTag = 1
    self.nextEventTag = 1
    self.transactions = {}
    self.events = {}
    self.buffer = ""

  def connect(self):
    self.socket = socket.create_connection((self.host, self.port))
    self.sendCommand("StartSession()")
    return True

  def disconnect(self):
    self.sendCommand("EndSession()")
    self.socket.close()

  def sendCommand(self, command):
    tag = self.nextTag
    transaction = Transaction()
    self.transactions[tag] = transaction
    message = "%05d %s\r\n" % (tag, command)
    self.nextTag = self.nextTag%99999+1 # Get the next tag between 1 - 99999
    self.socket.send(message.encode("ascii"))
    transaction.send()

    return tag

  def handleMessage(self):
    self.buffer += self.socket.recv(RECEIVE_SIZE).decode("ascii")
    index = self.buffer.find("\r\n")
    if index > -1:
      message = self.buffer[0:index]
      self.buffer = self.buffer[index+2:]
      return message
    else:
      return None
    
  def GetDMEVersion(self):
    return self.sendCommand("GetDMEVersion()")
