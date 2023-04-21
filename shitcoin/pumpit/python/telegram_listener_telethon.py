#!/usr/bin/python3

import json
import os 
from telethon import TelegramClient, events, sync
import sys
import grpc

FDIR = os.path.dirname(os.path.abspath(__file__))
sys.path.append(FDIR+'/../grpc/client')
import message_pb2
import message_pb2_grpc

# read credentials
f = open(FDIR+'/../secrets.json')
cred = json.load(f)
f.close()

api_id = cred['tg_api_id']
api_hash = cred['tg_api_hash']

client = TelegramClient('telethon_listener', api_id, api_hash)
client.start()

#client.send_message('https://t.me/ShitcoinTrader_bot', '[python] msg')
#client.send_message(cred['tg_announcement_channel_name'], '[ppython] msg')

@client.on(events.NewMessage(chats=cred['tg_announcement_channel_name']))
async def my_event_handler(event):
    with grpc.insecure_channel('localhost:' + cred['grpc_port']) as channel:
        stub = message_pb2_grpc.MessengerStub(channel)
        response = stub.SendMessage(message_pb2.Message(text='[TELETHON] ' + event.text))

client.run_until_disconnected()
print('exit from telegram_listener_telethon.py')