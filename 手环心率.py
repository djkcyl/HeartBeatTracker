import bleak
import asyncio
import fastapi
import uvicorn

from pathlib import Path
from loguru import logger

app = fastapi.FastAPI()
html = Path("心脏.html").read_text(encoding="utf-8")


async def get_device(need_name: str = "band", timeout: int = 10):
    bs = bleak.BleakScanner()
    await bs.start()
    t = asyncio.create_task(asyncio.sleep(timeout))
    while not t.done() and not await asyncio.sleep(0.1):
        for d in bs.discovered_devices:
            if d.name:
                if need_name in d.name.lower():
                    logger.success(f"发现目标设备：{d.address} {d.name}")
                    await bs.stop()
                    return d
                else:
                    logger.info(f"扫描到设备：{d.address} {d.name}")
            else:
                logger.debug(f"扫描到设备：{d.address} {d.name}")
    raise TimeoutError("未发现设备")


@app.get("/")
async def get():
    return fastapi.responses.HTMLResponse(html)


@app.websocket("/ws")
async def heart_rate(ws: fastapi.websockets.WebSocket):
    await ws.accept()
    await ws.send_text("连接成功")

    async def notification_handler(sender, data: bytearray):
        await ws.send_text(str(data[1]))

    while True:
        data = await ws.receive_text()
        if data == "ping":
            await ws.send_text("pong")
        elif data == "close":
            if "client" in locals():
                await client.disconnect()
            await ws.close()
            break
        else:
            await ws.send_text(f"正在搜索：{data}")
            try:
                device = await get_device(data, timeout=100)
                await ws.send_text(f"正在连接：{device.name} {device.address}")
                client = bleak.BleakClient(device)
                await client.connect()
                name = await client.read_gatt_char('00002a00-0000-1000-8000-00805f9b34fb')
                await ws.send_text(
                    f"连接成功：{name.decode()}"
                )
                await ws.send_text("开始扫描服务")
                services = client.services.services
                heart_rate_measure = ""
                for i, s in services.items():
                    await ws.send_text(f"{i} {s.description} {s.uuid}")
                    for c in s.characteristics:
                        if "heart" in c.description.lower():
                            heart_rate_measure = c.uuid

                if heart_rate_measure:
                    await ws.send_text(f"开始监听心率：{heart_rate_measure}")
                    await client.start_notify(heart_rate_measure, notification_handler)
                else:
                    await ws.send_text("未发现心率服务")

            except TimeoutError:
                await ws.send_text("未找到该设备")


uvicorn.run(app, host="0.0.0.0", port=8000)
