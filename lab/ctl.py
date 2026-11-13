#!/usr/bin/env python3
"""Pilotage d'une VM QEMU sans écran via son moniteur (socket unix mon.sock dans <rundir>).
Lancer QEMU avec :  -display none -monitor unix:mon.sock,server,nowait  [-vnc 127.0.0.1:1]
Usage : ctl.py <rundir> shot <nom>        -> capture <nom>.ppm (convert en png avec ImageMagick)
        ctl.py <rundir> key <touche>...   -> sendkey (ex: down ret ctrl-f2 shift-cmd-t)
        ctl.py <rundir> type "texte"      -> tape du texte (clavier US)
        ctl.py <rundir> click <x> <y>     -> clic tablette absolue (écran 1280x800)
Note : sous macOS Recovery émulé, les déplacements de la tablette USB sont ignorés mais le clavier
fonctionne une fois les pilotes HID associés (~1 min après l'affichage). Préférer Ctrl-F2 + flèches."""
import socket, sys, time, os
d, cmd = os.path.abspath(sys.argv[1]), sys.argv[2]
os.chdir(d); s = socket.socket(socket.AF_UNIX); s.connect("mon.sock"); time.sleep(0.3); s.recv(65536)
def mon(c, wait=0.6):
    s.send((c+"\n").encode()); time.sleep(wait); return s.recv(65536)
W, H = 1280, 800
def move(x, y): mon(f"mouse_move {int(x*32767/W)} {int(y*32767/H)}")
if cmd == "shot": mon(f"screendump {sys.argv[3]}.ppm", 2.5)
elif cmd in ("click", "dblclick", "move"):
    x, y = int(sys.argv[3]), int(sys.argv[4]); move(x, y); time.sleep(0.8); move(x, y)
    if cmd != "move":
        for _ in range(2 if cmd == "dblclick" else 1):
            mon("mouse_button 1", 0.25); mon("mouse_button 0", 0.4)
elif cmd == "key":
    for k in sys.argv[3:]: mon(f"sendkey {k}", 0.8)
elif cmd == "type":
    m = {' ':'spc','-':'minus','.':'dot','/':'slash','_':'shift-minus',';':'semicolon',':':'shift-semicolon','|':'shift-backslash','"':'shift-apostrophe',"'":'apostrophe',',':'comma','=':'equal','+':'shift-equal','(':'shift-9',')':'shift-0','*':'shift-8','&':'shift-7','>':'shift-dot','<':'shift-comma','!':'shift-1','@':'shift-2','#':'shift-3','$':'shift-4','%':'shift-5','^':'shift-6','?':'shift-slash','\\':'backslash','[':'bracket_left',']':'bracket_right','{':'shift-bracket_left','}':'shift-bracket_right','~':'shift-grave_accent','`':'grave_accent'}
    for ch in sys.argv[3]:
        k = m.get(ch) or (('shift-'+ch.lower()) if ch.isupper() else ch); mon(f"sendkey {k}", 0.35)
print("ok")
