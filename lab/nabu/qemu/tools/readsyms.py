import subprocess, time, json, socket, sys
from pathlib import Path
sys.path.insert(0, __import__('os').environ.get('XNUPRELINK', 'work/XnuPrelink-source'))
from kc_image import Image
esp = Path(sys.argv[1]).resolve(); kern = sys.argv[2]; wait = int(sys.argv[3]); names = sys.argv[4:]
k = Image(open(kern,'rb').read()); by = {n:a for a,ns in k.symbols().items() for n in ns}
cmdline = [r'C:\Program Files\qemu\qemu-system-aarch64.exe','-machine','virt,gic-version=3','-cpu','cortex-a76','-smp','1','-m','2048',
  '-bios',r'C:\Program Files\qemu\share\edk2-aarch64-code.fd','-drive',f'if=none,id=esp,format=raw,readonly=on,file=fat:{esp}',
  '-device','virtio-blk-pci,drive=esp','-device','ramfb','-device','qemu-xhci','-device','usb-kbd','-nic','none','-display','none',
  '-no-reboot','-qmp','tcp:127.0.0.1:4452,server=on,wait=off']
p = subprocess.Popen(cmdline); time.sleep(2)
s = socket.create_connection(('127.0.0.1',4452)); f = s.makefile('rw'); f.readline()
def h(cmd):
    f.write(json.dumps({'execute':'human-monitor-command','arguments':{'command-line':cmd}})+'\n'); f.flush()
    while True:
        r = json.loads(f.readline())
        if 'return' in r or 'error' in r: return r.get('return', r)
f.write('{"execute":"qmp_capabilities"}\n'); f.flush(); f.readline()
time.sleep(wait); h('stop')
for n in names:
    a = by.get(n)
    if a is None: print(n, 'symbole absent'); continue
    r = h(f'x /1gx {a:#x}'); print(f'{n:28} {r.strip()}')
h('quit'); p.wait(10)
