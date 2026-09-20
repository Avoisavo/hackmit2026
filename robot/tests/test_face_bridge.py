import unittest
from unittest.mock import Mock
import requests
from robot.face_bridge import FaceBridge, board_origins


class BoardURLTests(unittest.TestCase):
    def test_only_configured_local_origins_are_used_without_auth_urls_or_redirects(self):
        self.assertEqual(board_origins({'BOARD_URL':'http://127.0.0.1:8090','NEXT_PUBLIC_ROBOT_FACE_URL':'http://10.254.159.201:8080'}),
            ['http://127.0.0.1:8090','http://127.0.0.1:8080','http://[::1]:8080','http://10.254.159.201:8080'])
        for url in ['http://example.com','http://key@127.0.0.1','http://127.0.0.1/x','file:///tmp/file']:
            self.assertNotIn(url,board_origins({'BOARD_URL':url}))


class BoardTests(unittest.IsolatedAsyncioTestCase):
    async def test_discovers_existing_hb_tunnel_and_sends_only_allowed_expression(self):
        board=FaceBridge({},clock=lambda:10)
        def request(method,url,payload=None):
            if method=='GET':return {'ok':True,'version':'rabbit-v1-glossy','faces':1}
            return {'ok':True,'faces':1,**payload}
        board.request=Mock(side_effect=request)
        board.select('Thinking','OpenAI');await board.sync()
        board.request.assert_any_call('POST','http://127.0.0.1:8080/emote',{'name':'Thinking','hold':0})
        self.assertTrue(board.status()['delivered'])
        before=board.request.call_count;await board.sync();self.assertEqual(board.request.call_count,before)
        with self.assertRaises(ValueError):board.select('arbitrary command')

    async def test_reachable_server_without_a_display_is_not_reported_as_connected_face(self):
        board=FaceBridge({},clock=lambda:10)
        board.request=Mock(return_value={'ok':True,'version':'rabbit-v1-glossy','faces':0})
        await board.sync()
        self.assertTrue(board.online);self.assertFalse(board.status()['delivered'])
        self.assertTrue(all(call.args[0]=='GET' for call in board.request.call_args_list))

    async def test_wrong_service_and_network_failure_keep_local_preview_working(self):
        board=FaceBridge({},clock=lambda:10)
        board.request=Mock(side_effect=requests.ConnectionError('private error'))
        await board.sync();board.select('Celebrate','OpenAI')
        self.assertFalse(board.status()['delivered']);self.assertEqual(board.face,'Celebrate')
        self.assertNotIn('private error',board.error)
        board.request=Mock(return_value={'ok':True,'version':'some-other-service','faces':1})
        await board.sync(force=True);self.assertFalse(board.online)

    async def test_face_change_during_a_send_is_delivered_on_the_next_sync(self):
        board=FaceBridge({},clock=lambda:10)
        calls=[]
        def request(method,url,payload=None):
            if method=='GET':return {'ok':True,'version':'rabbit-v1-glossy','faces':1}
            calls.append(payload['name'])
            if len(calls)==1:board.select('Ready','lesson')
            return {'ok':True,'faces':1,**payload}
        board.request=request;board.select('Go','OpenAI')
        await board.sync();self.assertFalse(board.status()['delivered'])
        await board.sync();self.assertEqual(calls,['Go','Ready']);self.assertTrue(board.status()['delivered'])
