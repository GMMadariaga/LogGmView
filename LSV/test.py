#!/usr/bin/env python3
"""
udp_listener.py: escucha en el puerto UDP 9999 y muestra en consola cualquier paquete recibido.
"""
import socket

HOST = "0.0.0.0"   # todas las interfaces
PORT = 9999
BUFFER_SIZE = 4096

def main():
    # Aviso de arranque
    print(f"🔊 Escuchando UDP en {HOST}:{PORT} (presiona Ctrl+C para salir)")

    # Configurar socket UDP
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((HOST, PORT))

    try:
        while True:
            data, addr = sock.recvfrom(BUFFER_SIZE)
            text = data.decode(errors="replace").rstrip()
            print(f"[{addr[0]}:{addr[1]}] → {text}")
    except KeyboardInterrupt:
        print("\nDeteniendo listener.")
    finally:
        sock.close()

if __name__ == "__main__":
    main()
