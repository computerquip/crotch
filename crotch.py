import asyncio
from websockets import ConnectionClosed
from websockets.asyncio.client import connect
import json

token = ''
user_id = ''
uri = 'wss://open.rocket.chat/websocket'

class CrotchException(Exception):
    pass

class CrotchApplication:
    def __init__(self, socket):
        loop = asyncio.get_running_loop()

        self.connected_future = loop.create_future()
        self.result_futures = {}
        self.socket = socket
        self._counter = 0

    async def _send(self, value: dict):
        msg = json.dumps(value, separators=(',', ':'))

        print(f"==> '{msg}'")
        await self.socket.send(msg)

    async def _send_method(self, method: str, params: list):
        unique_id = str(self._counter)

        self._counter += 1
        self.result_futures[unique_id] = asyncio.get_running_loop().create_future()

        await self._send({
            'msg': 'method',
            'method': method,
            'id': f'{unique_id}',
            'params': params
        })

        return unique_id

    async def _get_result(self, unique_id):
        return await self.result_futures[unique_id]

    # RPC here implies a result so this sends
    # the message, waits for the result, and
    # returns it.
    async def _rpc_method(self, method: str, params: list):
        unique_id = await self._send_method(method, params)
        return await self._get_result(unique_id)

    async def _rpc_connect(self):
        await self._send_connect()
        await self.connected_future

    async def _send_pong(self):
        await self._send({ 'msg': 'pong' })

    async def _send_connect(self):
        await self._send({
            'msg': 'connect',
            'version': '1',
            'support': ['1']
        })

    async def _process_connected(self):
        self.connected_future.set_result(None)

    async def _process_ping(self):
        await self._send_pong()

    async def _process_result(self, root: dict):
        if not 'id' in root:
            raise CrotchException("method response did not contain an id, skipping")

        unique_id = root['id']

        if not unique_id in self.result_futures:
            raise CrotchException("method response contained an unknown id, skipping")
            return

        future = self.result_futures[unique_id]

        if 'result' in root:
            future.set_result(root['result'])
        elif 'error' in root:
            future.set_result(root['error'])
        else:
            # This should never happen, log but accept the future.
            print("method response didn't contain a result or error (warning)")
            future.set_result(None)

    async def _process_msg(self, msg):
        print(f"<== '{msg}'")
        root = json.loads(msg)

        if not isinstance(root, object):
            raise CrotchException("message didn't contain a json object, skipping")

        # I have no clue what this message is doing here. I think
        # it's the initial message from the server but it doesn't
        # fit the RPC schema. Also, all of the official demo servers
        # give this so...???
        if 'server_id' in root:
            return

        if not 'msg' in root:
            raise CrotchException("message did not contain a type, skipping")

        msg_type = root['msg']

        if not isinstance(msg_type, str):
            raise CrotchException("message contained type but wasn't a string, skipping")

        # Finally, handle the response
        match msg_type:
            case 'ping':
                await self._process_ping()
            case 'result':
                await self._process_result(root)
            case 'connected':
                await self._process_connected()
            case _:
                raise CrotchException(f"unknown message type '{msg_type}', skipping")

    async def listen(self):
        async for msg in self.socket:
            try:
                await self._process_msg(msg)
            except CrotchException as e:
                print(f"failed to process rocketchat message: {e}")

    async def start(self):
        # Send "connect" packet
        await self._rpc_connect()

        # Login persists through the connection, since we're using
        # a token, we don't need the info provided so we skip it.
        login_result = await self._rpc_method('login', [{ 'resume': token }])
        roles_result = await self._rpc_method('getUserRoles', [])
        avail_result = await self._rpc_method('checkUsernameAvailability', [ "henry103433" ])

        # Fetch rooms
        # So uh... this doesn't work.
        rooms_result = await self._rpc_method('asdf', [])

async def main():
    async for socket in connect(uri):
        try:
            app = CrotchApplication(socket)

            await asyncio.gather(app.listen(), app.start())

        except ConnectionClosed as e:
            print(f"connection closed: {e}")
            print(f"reconnecting in a few seconds")
            await asyncio.sleep(5)
            continue

asyncio.run(main())
