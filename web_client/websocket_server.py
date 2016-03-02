# encoding: utf-8

from tornado import websocket, web, ioloop
import json
import zmq
import jwt

from mltsp.cfg import config as cfg
secret = cfg['flask']['secret-key']

ctx = zmq.Context()


# Could also use: http://aaugustin.github.io/websockets/


class WebSocket(websocket.WebSocketHandler):
    participants = set()

    def __init__(self, *args, **kwargs):
        websocket.WebSocketHandler.__init__(self, *args, **kwargs)

        self.authenticated = False
        self.auth_failures = 0
        self.username = None

    def check_origin(self, origin):
        return True

    def open(self):
        if self not in self.participants:
            self.participants.add(self)
            self.request_auth()

    def on_close(self):
        if self in self.participants:
            self.participants.remove(self)

    def on_message(self, auth_token):
        self.authenticate(auth_token)
        if not self.authenticated and self.auth_failures < 3:
            self.request_auth()

    def request_auth(self):
        self.auth_failures += 1
        self.send_json(id="AUTH REQUEST")

    def send_json(self, **kwargs):
        self.write_message(json.dumps(kwargs))

    def authenticate(self, auth_token):
        try:
            token_payload = jwt.decode(auth_token, secret)
            self.username = token_payload['username']
            self.authenticated = True
            self.send_json(id='AUTH OK')
        except DecodeError:
            self.send_json(id='AUTH FAILED')

    @classmethod
    def heartbeat(cls):
        for p in cls.participants:
            p.write_message(b'<3')

    # http://mrjoes.github.io/2013/06/21/python-realtime.html
    @classmethod
    def broadcast(cls, data):
        channel, data = data[0].decode('utf-8').split(" ", 1)
        user = json.loads(data)["username"]

        for p in cls.participants:
            if p.authenticated and p.username == user:
                p.write_message(data)


if __name__ == "__main__":
    PORT = 4567
    LOCAL_OUTPUT = 'ipc:///tmp/message_flow_out'

    import zmq

    # https://zeromq.github.io/pyzmq/eventloop.html
    from zmq.eventloop import ioloop, zmqstream

    ioloop.install()

    sub = ctx.socket(zmq.SUB)
    sub.connect(LOCAL_OUTPUT)
    sub.setsockopt(zmq.SUBSCRIBE, b'')

    print('[websocket_server] Broadcasting {} to all websockets'.format(LOCAL_OUTPUT))
    stream = zmqstream.ZMQStream(sub)
    stream.on_recv(WebSocket.broadcast)

    server = web.Application([
        (r'/websocket', WebSocket),
    ])
    server.listen(PORT)

    # We send a heartbeat every 45 seconds to make sure that nginx
    # proxy does not time out and close the connection
    ioloop.PeriodicCallback(WebSocket.heartbeat, 45000).start()

    print('[websocket_server] Listening for incoming websocket connections on port {}'.format(PORT))
    ioloop.IOLoop.instance().start()
