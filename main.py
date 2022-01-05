import ipp

def main():
  host = "localhost"
#  port = 1294
  port = 50007

  client = ipp.Client(host, port)

  if not client.connect():
    print("Failed to connect to server.")

  client.GetDMEVersion()

  message = client.handleMessage()

  print(message)
  print(client.transactions)


  
if __name__ == "__main__":
  main()
