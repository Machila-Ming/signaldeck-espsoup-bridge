"""Smoke-test the new IqSource against the live PZSDR (plutosdr)."""
import asyncio
import base64

import numpy as np

from signaldeck.engine.device_manager import DeviceManager
from signaldeck.engine.iq_source import get_iq_source


async def main() -> None:
    mgr = DeviceManager()
    infos = mgr.enumerate()
    pluto = next((i for i in infos if i.driver == "plutosdr"), None)
    if pluto is None:
        print("no plutosdr device found")
        return
    print("found:", pluto.label, "| driver=", pluto.driver, "| serial=", pluto.serial)

    dev = mgr.open(driver="plutosdr")
    print("open OK, hardware_key=", dev.info.hardware_key)

    src = get_iq_source()
    src.attach_device(dev)

    r = await src.capture(2402_000_000.0, 8_000_000.0, 16380, gain_db=0.0, gain_mode="MANUAL")
    print("ok=", r.get("ok"), "n=", r.get("n"), "rate=", r.get("rate"),
          "msg=", r.get("message"), "bits=", r.get("bits"))
    if r.get("ok"):
        raw = base64.b64decode(r["iq_b64"])
        a = np.frombuffer(raw, dtype=np.float32)
        c = a[0::2] + 1j * a[1::2]
        print("iq floats:", a.shape, "complex n:", c.shape,
              "peak=", round(float(np.max(np.abs(c))), 4),
              "rms=", round(float(np.sqrt(np.mean(np.abs(c) ** 2))), 4),
              "dc_after_mean=", round(float(np.abs(c.mean())), 6))

    dev.close()


asyncio.run(main())
