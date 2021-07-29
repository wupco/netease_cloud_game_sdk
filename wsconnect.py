import asyncio
import websockets
import base64
import time
import json
import requests
from aiortc.sdp import candidate_from_sdp, candidate_to_sdp
from aiortc.contrib.signaling import object_from_string, object_to_string
from aiortc import RTCIceCandidate, RTCPeerConnection, RTCSessionDescription
from aiortc.contrib.signaling import BYE, add_signaling_arguments, create_signaling
from aiortc.contrib.media import MediaBlackhole, MediaPlayer, MediaRecorder, MediaRelay
import cv2

relay = MediaRelay()
sub_key = None

def login(phonenumber):
    req_smscode = requests.post('https://n.cg.163.com/api/v1/phone-captchas/' + phonenumber)
    print("input the code recieved by your phone")
    code = input().strip()
    headers = {"Content-Type": "application/json;charset=utf-8"}
    data = {
        "auth_method":"phone-captcha",
        "ctcode": phonenumber.split("-")[0],
        "phone": phonenumber.split("-")[1],
        "captcha": code,
        "device_info":{
            "userAgent":"Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:91.0) Gecko/20100101 Firefox/91.0",
            "appVersion":"5.0 (Macintosh)",
            "codecs":["h264","vp8","vp9"]
            }
        }
    data = json.dumps(data)
    user_info = requests.post("https://n.cg.163.com/api/v1/tokens", headers=headers, data=data).text
    user_obj = json.loads(user_info)
    try:
        token = user_obj["token"]
        with open("token","w") as f:
            f.write(token)
        print("login ok!")
    except:
        print("login error! try again")
        exit(-1)
    return 


def encode_mess(message):
    global sub_key
    mess = str.encode(message)
    m = b""
    for i in mess:
        m += ((i+sub_key)%256).to_bytes(1, byteorder='big')
    res = base64.b64encode(m)
    return res

def decode_mess(message):
    try:
        mess = base64.b64decode(message)
    except:
        return message
    global sub_key
    if sub_key == None:
        fbyte = mess[0]
        sbyte = mess[1]
        for j in range(0, 256):
            if chr((fbyte-j)%256) == "{" and chr((sbyte-j)%256) == "\"":
                sub_key = j
                break
    m = ""
    for i in mess:
         m += chr((i-sub_key)%256)
    return m

def get_basic_info(token):
    headers = {
        "Authorization": "Bearer " +token
    }
    info = requests.get("https://n.cg.163.com/api/v2/users/@me", headers=headers).text
    info = json.loads(decode_mess(info))
    return info["yunxin_account"]["accid"]

def request_ticket(token, game_code, regions=["hdcz","hbsjz"], codecs = ["h264","vp8","vp9"], width = 1280, height = 720):
    req_obj = {
        "regions": regions,
        "game_code": game_code,
        "codecs": codecs,
        "width": width,
        "height": height
    }
    global sub_key
    
    req_str = encode_mess(json.dumps(req_obj).replace("'","\""))
    headers = {
        "Authorization": "Bearer " +token,
        "Content-Type": "application/octet-stream" 
    }
    info = requests.post("https://n.cg.163.com/api/v2/tickets", headers=headers, data= req_str).text
    info_obj = json.loads(decode_mess(info))
    return info_obj["gateway_url"]

def exit_game(token):
    headers = {
        "Authorization": "Bearer " +token
    }
    print(requests.get("https://n.cg.163.com/api/v2/customize-settings/exitgame_room_recommend/time", headers=headers).text)

async def connect(token, game_code, w=1280, h=720, quality="high", codecs=["h264","vp8","vp9"], platform=0, fps="30"):
        user_id = get_basic_info(token)
        uri = request_ticket(token, game_code)
        websocket = await websockets.connect(uri)
        auth_obj = { 
            "id": str(int(round(time.time() * 1000))),
            "op": "auth",
            "data": {
                "user_id": user_id,
                "token": token,
                "game_code": game_code,
                "w": w,
                "h": h,
                "quality": quality,
                "codecs": codecs,
                "platform": platform,
                "fps": fps
            }
        }
        auth_str = json.dumps(auth_obj)
        await websocket.send(auth_str)
        auth_res = await websocket.recv()
        auth_res = decode_mess(auth_res)
        try:
            de_res = json.loads(auth_res)
        except:
            print("[x] something went wrong when decoding auth response")
            exit(-1)
        if de_res["op"] != "offer":
            print("[x] "+ de_res["data"]["errmsg"])
            exit(-1)
        new_sdp = {}
        new_sdp["type"] = de_res["op"]
        new_sdp["sdp"] = de_res["data"]["sdp"]
        new_sdp = json.dumps(new_sdp)
        return new_sdp, websocket


def channel_log(channel, t, message):
    print("channel(%s) %s %s" % (channel.label, t, message))

async def send_action(sock, action):
    action = encode_mess(json.dumps(action).replace("'","\""))
    await sock.send(action)
    pong_waiter = await sock.ping()
    await pong_waiter

async def test(game_code):
    token = open("token").read().strip()
    if token == "":
        print("login first!")
        exit(-1)
    res, sock = await connect(token, game_code)
    obj = object_from_string(res)
    recorder = MediaRecorder("./a.mp4")
    pc = RTCPeerConnection()
    @pc.on("track")
    def on_track(track):
        if track.kind == "audio":
            recorder.addTrack(track)
        elif track.kind == "video":
            print("vedio")
            recorder.addTrack(relay.subscribe(track))
        
    await pc.setRemoteDescription(obj)
    await recorder.start()
    await pc.setLocalDescription(await pc.createAnswer())
    local_d = object_to_string(pc.localDescription)
    local_d = json.loads(local_d)
    new_answer = {
        "id" : str(int(round(time.time() * 1000))),
        "op" : "answer",
        "data" : {
            "sdp" : local_d["sdp"]
        }
    }
    answer_mess = encode_mess(json.dumps(new_answer))
    await sock.send(answer_mess)
    print(decode_mess(await sock.recv()))
    while 1:
        try:
            a = await pc.getReceivers()[1].track.recv()
        except:
            print("err")
            continue
        print("---------input---------")
        b = input()
        if b.strip() == "s":
            # 1=>move (640,675)
            action = {"id":str(int(round(time.time() * 1000))),"op":"input","data":{"cmd":"1 640 675 0"}}
            await send_action(sock, action)
            # 3=>click (640,675)
            action = {"id":str(int(round(time.time() * 1000))),"op":"input","data":{"cmd":"3 640 675 0"}}
            await send_action(sock, action)
            

        a.to_image().save("./a.png")
    await recorder.stop() 

#login("86-138xxxxxxxx")

game_code = "mrfz"
asyncio.get_event_loop().run_until_complete(test(game_code))


