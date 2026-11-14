import subprocess, time, json, socket, sys, re
from pathlib import Path
esp = Path(sys.argv[1]).resolve(); out = Path(sys.argv[2]); out.mkdir(parents=True, exist_ok=True); wait = int(sys.argv[3])
cmdline = [r'C:\Program Files\qemu\qemu-system-aarch64.exe','-machine','virt,gic-version=3','-cpu','cortex-a76','-smp','1','-m','2048',
  '-bios',r'C:\Program Files\qemu\share\edk2-aarch64-code.fd','-drive',f'if=none,id=esp,format=raw,readonly=on,file=fat:{esp}',
  '-device','virtio-blk-pci,drive=esp','-device','ramfb','-device','qemu-xhci','-device','usb-kbd','-nic','none','-display','none',
  '-no-reboot','-serial',f'file:{out/"serial.log"}','-qmp','tcp:127.0.0.1:4451,server=on,wait=off']
p = subprocess.Popen(cmdline); time.sleep(2)
s = socket.create_connection(('127.0.0.1',4451)); f = s.makefile('rw'); f.readline()
def h(cmd):
    f.write(json.dumps({'execute':'human-monitor-command','arguments':{'command-line':cmd}})+'\n'); f.flush()
    while True:
        r = json.loads(f.readline())
        if 'return' in r or 'error' in r: return r.get('return', r)
f.write('{"execute":"qmp_capabilities"}\n'); f.flush(); f.readline()
time.sleep(wait); h('stop')
regs = h('info registers')
(out/'regs.txt').write_text(regs)
def q(addr):
    r = h(f'x /2gx {addr:#x}')
    vals = r.split(':')[1].split(); return int(vals[0],16), int(vals[1],16)
fp = int(re.search(r'X29=([0-9a-f]+)', regs).group(1), 16)
frames = []
for _ in range(24):
    if not fp or fp & 7: break
    try: nfp, lr = q(fp)
    except Exception as e: break
    frames.append(lr); fp = nfp
(out/'frames.txt').write_text('\n'.join(hex(x) for x in frames))
# strings pointed to by X0..X7 of the panic frame are not preserved; dump candidate registers
for r in ('X0','X1','X2','X19','X20','X21','X22'):
    m = re.search(rf'{r}=([0-9a-f]+)', regs)
    if m:
        v = int(m.group(1),16)
        try:
            raw = h(f'x /64bx {v:#x}')
            b = bytes(int(t,16) for line in raw.splitlines() for t in line.split(':')[1].split())
            txt = b.split(b'\0')[0]
            if len(txt) > 4 and all(32 <= c < 127 or c in (9,10) for c in txt): print(f'{r} -> {txt.decode()!r}')
        except Exception: pass
h('quit'); p.wait(10)
print('frames', len(frames))
