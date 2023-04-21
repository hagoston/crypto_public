import grpc
import message_pb2
import message_pb2_grpc

def run():
    with grpc.insecure_channel('localhost:50051') as channel:
        stub = message_pb2_grpc.MessengerStub(channel)
        response = stub.SendMessage(message_pb2.Message(text="Hello from Python"))
    print("Response received: " + response.text)

if __name__ == '__main__':
    run()