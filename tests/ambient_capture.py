import SoapySDR, numpy as np, time

RATE = 8e6
NSAMP = 400000          # 50 ms per channel
CHANNELS = [(2402e6, 'ble37'), (2426e6, 'ble38'), (2480e6, 'ble39'), (2437e6, 'wifi6')]

d = SoapySDR.Device(dict(driver="plutosdr"))
d.setSampleRate(SoapySDR.SOAPY_SDR_RX, 0, RATE)
d.setBandwidth(SoapySDR.SOAPY_SDR_RX, 0, RATE)
d.setGain(SoapySDR.SOAPY_SDR_RX, 0, 10.0)
rx = d.setupStream(SoapySDR.SOAPY_SDR_RX, SoapySDR.SOAPY_SDR_CF32)
d.activateStream(rx)

for mhz, name in CHANNELS:
    d.setFrequency(SoapySDR.SOAPY_SDR_RX, 0, mhz)
    time.sleep(0.05)
    d.readStream(rx, [np.zeros(8192, dtype=np.complex64)], 8192, timeoutUs=1000000)   # flush
    chunks = []; got = 0; t0 = time.monotonic()
    while got < NSAMP and time.monotonic() - t0 < 5:
        b = np.zeros(min(65536, NSAMP - got), dtype=np.complex64)
        sr = d.readStream(rx, [b], b.size, timeoutUs=2000000)
        k = int(getattr(sr, 'ret', sr))
        if k > 0:
            chunks.append(b[:k]); got += k
    buf = np.concatenate(chunks) if chunks else np.zeros(0, dtype=np.complex64)
    out = np.zeros(got * 2, dtype=np.float32); out[0::2] = buf[:got].real; out[1::2] = buf[:got].imag
    out.tofile('/tmp/amb_%s.bin' % name)
    ma = float(np.sqrt(np.mean(np.abs(buf) ** 2))) if got else 0.0
    pk = float(np.max(np.abs(buf))) if got else 0.0
    print('%-7s @ %6.0f MHz : %d samples | meanAmp %.5f | peakAmp %.4f' % (name, mhz / 1e6, got, ma, pk))

d.deactivateStream(rx); d.closeStream(rx)
print('AMBIENT_DONE')
