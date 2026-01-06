import socket
import threading
import time

# 配置要测试的端口范围
START_PORT = 10110
END_PORT = 10115

def handle_tcp(port):
    try:
        # 监听 TCP
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        # 必须监听 127.0.0.1 或 0.0.0.0，因为 frpc 配置的是转发到 localIP
        sock.bind(('0.0.0.0', port)) 
        sock.listen(5)
        print(f"[TCP] 正在监听端口 {port}...")
        
        while True:
            conn, addr = sock.accept()
            # 收到连接后，发送一个简单的回复
            try:
                conn.send(b"TCP_PONG")
            except:
                pass
            conn.close()
    except Exception as e:
        print(f"[TCP] 端口 {port} 错误: {e}")

def handle_udp(port):
    try:
        # 监听 UDP
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind(('0.0.0.0', port))
        print(f"[UDP] 正在监听端口 {port}...")
        
        while True:
            data, addr = sock.recvfrom(1024)
            # 收到 UDP 包，原样发回 (Echo) 或者发特定消息
            sock.sendto(b"UDP_PONG", addr)
    except Exception as e:
        print(f"[UDP] 端口 {port} 错误: {e}")

# 启动多线程监听所有端口
threads = []
for port in range(START_PORT, END_PORT + 1):
    t_tcp = threading.Thread(target=handle_tcp, args=(port,), daemon=True)
    t_udp = threading.Thread(target=handle_udp, args=(port,), daemon=True)
    threads.append(t_tcp)
    threads.append(t_udp)
    t_tcp.start()
    t_udp.start()

print(f"✅ 模拟服务器已启动，正在监听 {START_PORT}-{END_PORT} 的 TCP/UDP...")
# 保持主线程运行
while True:
    time.sleep(1)
