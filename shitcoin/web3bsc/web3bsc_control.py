from multiprocessing.connection import Client

address = ('localhost', 6006)
conn = Client(address, authkey=b'web3sbc control')
while 1:
    print('waiting for command...')
    cmd = str(input())
    conn.send(cmd)
    print('\t', cmd, 'command sent')
    if cmd == 'exit':
        print('exiting...')
        break
conn.close()
