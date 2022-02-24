from wsconnect import *

async def test(game_code):
    token = open("token").read().strip()
    if token == "":
        print("login first!")
        pnum = input("input your phone number: ")
        login("86-"+pnum.strip())
        token = open("token").read().strip()
        if token == "":
            print("something wrong when login")
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
            await sock.send(answer_mess)
            print("err")
            continue
        print("---------input---------")
        b = input()
        if b.strip() == "init":
            # 1=>move (638,627)
            action = pack_message("mm", {"x":638, "y":627})
            await send_action(sock, action)
            # 3=>click (638,627)
            action = pack_message("cm", {"x":638, "y":627})
            await send_action(sock, action)
        if b.strip() == "click start game":
            #action = {"id":str(int(round(time.time() * 1000))),"op":"input","data":{"cmd":"1 571 528 0"}}
            action = pack_message("mm", {"x":571, "y":528})
            await send_action(sock, action)
            #action = {"id":str(int(round(time.time() * 1000))),"op":"input","data":{"cmd":"3 571 528 0"}}
            action = pack_message("cm", {"x":571, "y":528})
            await send_action(sock, action)
        if b.strip() == "input abc":
            action = pack_message("ip", {"word":"a"})
            await send_action(sock, action)
            action = pack_message("ip", {"word":"b"})
            await send_action(sock, action)
            action = pack_message("ip", {"word":"c"})
            await send_action(sock, action)
        
        a.to_image().save("./a.png")
    await recorder.stop() 

#login("86-138xxxxxxxx")

game_code = "mrfz"
asyncio.get_event_loop().run_until_complete(test(game_code))


