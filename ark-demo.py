import asyncio
import json
import time
import sys
import os
import platform
from typing import Optional
from aiortc import RTCPeerConnection, RTCSessionDescription
from aiortc.contrib.media import MediaRecorder, MediaRelay
from wsconnect import (
    connect, object_from_string, encode_mess, decode_mess,
    pack_message, send_action, login, exit_game
)

GAME_CODE = "mrfz"
TOKEN_FILE = "token"
RECORD_PATH = "./a.mp4"
DEFAULT_SNAPSHOT_FORMAT = "bmp"   # 可选: bmp/png/npy/raw
WAIT_NEXT_FRAME_TIMEOUT = 5.0

if platform.system() == "Windows":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

relay = MediaRelay()

# ---------- 工具 ----------
def ensure_dir(path: str):
    d = os.path.dirname(path)
    if d and not os.path.exists(d):
        os.makedirs(d, exist_ok=True)

def swap_ext(path: str, new_ext: str):
    base, _ = os.path.splitext(path)
    if not new_ext.startswith("."):
        new_ext = "." + new_ext
    return base + new_ext


# ---------- 快照器 ----------
class VideoSnapshotper:
    def __init__(self, video_track):
        self._track = video_track
        self._task: Optional[asyncio.Task] = None
        self._last_frame = None
        self._got_first = asyncio.Event()
        self._running = False
        self._seq = 0

    def start(self):
        if self._task:
            return
        self._running = True
        self._task = asyncio.create_task(self._pump())

    async def _pump(self):
        try:
            while self._running:
                frame = await self._track.recv()
                self._last_frame = frame
                self._seq += 1
                if not self._got_first.is_set():
                    self._got_first.set()
        except Exception:
            pass

    async def wait_ready(self, timeout=10.0):
        """阻塞直到收到第一帧"""
        try:
            await asyncio.wait_for(self._got_first.wait(), timeout=timeout)
            return True
        except asyncio.TimeoutError:
            return False

    async def snapshot(self, path="./a.png", mode="latest", fmt=DEFAULT_SNAPSHOT_FORMAT):
        """保存当前或下一帧"""
        await self._got_first.wait()
        frame = self._last_frame
        if frame is None:
            print("[snap] no frame yet")
            return False

        ensure_dir(path)
        try:
            if fmt == "npy":
                import numpy as np
                arr = frame.to_ndarray(format="rgb24")
                np.save(swap_ext(path, ".npy"), arr)
                return True
            elif fmt == "raw":
                import numpy as np
                arr = frame.to_ndarray(format="rgb24")
                arr.tofile(swap_ext(path, ".raw"))
                return True
            else:
                from PIL import Image
                img = frame.to_image()
                ext = fmt.lower()
                img.save(swap_ext(path, "." + ext), format=ext.upper())
                return True
        except Exception as e:
            print(f"[snap] save failed: {e}")
            return False

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except Exception:
                pass
            self._task = None


# ---------- 主逻辑 ----------
async def test(game_code: str):
    try:
        token = open(TOKEN_FILE).read().strip()
    except FileNotFoundError:
        token = ""
    if not token:
        pnum = input("input your phone number: ").strip()
        login("86-" + pnum)
        token = open(TOKEN_FILE).read().strip()
        if not token:
            print("login failed")
            sys.exit(1)

    res, sock = await connect(token, game_code)
    remote = object_from_string(res)

    pc = RTCPeerConnection()
    recorder = MediaRecorder(RECORD_PATH)
    snapshotper: Optional[VideoSnapshotper] = None

    @pc.on("track")
    def on_track(track):
        nonlocal snapshotper
        subscribed = relay.subscribe(track)
        recorder.addTrack(subscribed)
        if track.kind == "video":
            snapshotper = VideoSnapshotper(subscribed)
            snapshotper.start()

    await pc.setRemoteDescription(remote)
    await recorder.start()

    answer = await pc.createAnswer()
    patched = RTCSessionDescription(
        sdp=answer.sdp.replace("a=setup:active", "a=setup:passive"),
        type=answer.type,
    )
    await pc.setLocalDescription(patched)
    msg = {"id": str(int(time.time() * 1000)), "op": "answer", "data": {"sdp": patched.sdp}}
    await sock.send(encode_mess(json.dumps(msg)))

    # 等待第一帧 ready
    print("[*] waiting for video stream ...")
    if not snapshotper:
        await asyncio.sleep(3)  # track还没触发
    if snapshotper:
        ready = await snapshotper.wait_ready(timeout=20.0)
        if not ready:
            print("[!] timeout: video never started streaming.")
        else:
            print("[✓] video stream ready, you can now send actions.")
    else:
        print("[!] no video track, exiting.")
        return

    print("commands: init | click start game | snap | quit")

    async def do_snap(fmt=DEFAULT_SNAPSHOT_FORMAT):
        ok = await snapshotper.snapshot(fmt=fmt)
        if ok:
            print(f"[✓] snapshot ({fmt}) done")
        else:
            print("[snap] failed")

    try:
        while True:
            cmd = input("> ").strip().lower()
            if cmd == "quit":
                break
            elif cmd == "init":
                # move mouse to select 默认语音
                action = pack_message("mm", {"x": 414, "y": 457})
                await send_action(sock, action)
                await asyncio.sleep(0.5)
                await do_snap()
                input("next step")
                # move mouse to click 默认语音
                action = pack_message("cm", {"x": 414, "y": 457})
                await send_action(sock, action)
                await asyncio.sleep(0.5)
                await do_snap()
                input("next step")
                # move mouse to select 确定
                action = pack_message("mm", {"x": 710, "y": 560})
                await send_action(sock, action)
                await asyncio.sleep(0.5)
                await do_snap()
                input("next step")
                # move mouse to click 确定
                action = pack_message("cm", {"x": 710, "y": 560})
                await send_action(sock, action)
                await asyncio.sleep(0.5)
                await do_snap()
            elif cmd == "click start game":
                action = pack_message("cm", {"x": 644, "y": 688})
                await send_action(sock, action)
                await asyncio.sleep(0.5)
                await do_snap()
            elif cmd == "snap":
                await do_snap()
            else:
                print("commands: init | click start game | snap | quit")
    except KeyboardInterrupt:
        pass
    finally:
        if snapshotper:
            await snapshotper.stop()
        await recorder.stop()
        await pc.close()
        await sock.close()

        print("[✓] closed cleanly")


if __name__ == "__main__":
    asyncio.run(test(GAME_CODE))
