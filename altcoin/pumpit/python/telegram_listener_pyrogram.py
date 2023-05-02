#!/usr/bin/env python3
import json
import os 
from pyrogram import Client
from pyrogram import filters
import sys, traceback
from datetime import datetime
import grpc

FDIR = os.path.dirname(os.path.abspath(__file__))
sys.path.append(FDIR+'/../grpc/client')
import message_pb2
import message_pb2_grpc


# read credentials
f = open(os.path.dirname(os.path.realpath(__file__))+'/../secrets.json')
cred = json.load(f)
f.close()

channel = cred['tg_announcement_channel_name'].replace('https://t.me/', '')

try:
    # telegram client
    app = Client('pyrogram_listener',
        phone_number=cred['telephone'],
        api_id=cred['tg_api_id'],
        api_hash=cred['tg_api_hash']
    )

    # channel filter
    f = filters.chat(channel)

    # create grpc channel
    channel = grpc.insecure_channel('localhost:' + cred['grpc_port'])
    
    # message handler
    @app.on_message(f)
    def msg_handler(client, message):
        stub = message_pb2_grpc.MessengerStub(channel)
        response = stub.SendMessage(message_pb2.Message(text='[PYROGRAM] ' + message.text))

    app.run() 
except:
    print('pyrogram error')
print('telegram_listener_pyrogram.py exit')