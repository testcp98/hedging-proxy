import json
from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
import logging
import asyncio
import websockets
import threading
import time
from datetime import datetime

app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": "*"}}, supports_credentials=True)
proxy_port = 7890

# Configure logging
logging.basicConfig(level=logging.INFO)

# Session with connection pooling
session = requests.Session()

# Proxy configuration
proxies = {
    'http': f'http://127.0.0.1:{proxy_port}',
    'https': f'http://127.0.0.1:{proxy_port}'
}

# 存储 WebSocket 连接和消息的字典
ws_connections = {}
ws_messages = {}
ws_last_keepalive = {}
WS_TIMEOUT = 10  # 10秒超时

async def handle_websocket(url, message, key, merge, merge_key):
    try:
        async with websockets.connect(url) as websocket:
            # 存储连接
            ws_connections[key] = websocket
            ws_messages[key] = None
            ws_last_keepalive[key] = time.time()
            
            # 发送初始消息
            await websocket.send(message)
            
            # 监听消息
            while True:
                if time.time() - ws_last_keepalive[key] > WS_TIMEOUT:
                    logging.info(f"WebSocket {key} timeout, closing connection")
                    break
                
                try:
                    message = await asyncio.wait_for(websocket.recv(), timeout=1.0)
                    if merge:
                       message = find_value_by_key(message, merge_key)
                       if message:
                           if ws_messages[key]:
                               if isinstance(ws_messages[key], list):
                                   ws_messages[key].extend(message)
                               else:
                                   ws_messages[key].update(message)
                           else:
                               ws_messages[key] = message
                    else:
                        ws_messages[key] = message
                except asyncio.TimeoutError:
                    continue
                except Exception as e:
                    logging.error(f"WebSocket error: {e}")
                    break
                    
    except Exception as e:
        logging.error(f"WebSocket connection error: {e}")
    finally:
        # 清理连接
        if key in ws_connections:
            del ws_connections[key]
        if key in ws_last_keepalive:
            del ws_last_keepalive[key]

def send_request(data):
    url = data.get('u')
    method = data.get('m', 'GET').upper()
    request_data = data.get('d')
    headers = data.get('h')

    try:
        if method == 'GET':
            response = session.get(url, headers=headers, proxies=proxies, timeout=5)
        elif method == 'POST':
            payload = bytes.fromhex(request_data).decode('utf-8') if request_data else None
            response = session.post(url, data=payload, headers=headers, proxies=proxies, timeout=5)
        else:
            return None, "Unsupported HTTP method", 400
        return response, None, response.status_code
    except requests.exceptions.RequestException as e:
        logging.error(f"Request failed: {e}")
        return None, str(e), 500


@app.route('/api/proxy', methods=['OPTIONS'])
def options():
    return '', 204


@app.route('/api/proxy', methods=['POST'])
def proxy():
    data = request.get_json()
    logging.info(f"Received data: {data}")

    response, error, status_code = send_request(data)
    if error:
        return jsonify({"error": error}), status_code

    t = data.get('t', 'TEXT').upper()
    if t == 'JSON':
        try:
            return jsonify(response.json()), response.status_code
        except ValueError:
            return jsonify({"error": "Invalid JSON response"}), 500
    else:
        return response.text, response.status_code


@app.route('/api/get', methods=['GET'])
def get():
    return jsonify({"message": "插件开启成功"})

@app.route('/api/ws/connect', methods=['POST'])
def connect_websocket():
    data = request.get_json()
    url = data.get('url')
    message = data.get('message')
    key = data.get('key')
    merge = data.get('merge')
    merge_key = data.get('merge_key')
    
    if not all([url, message, key]):
        return jsonify({"error": "Missing required parameters"}), 400
    
    # 如果已存在相同key的连接,先关闭它
    if key in ws_connections:
        return jsonify({"error": "Connection with this key already exists"}), 400
    
    # 在新线程中启动WebSocket连接
    def run_async():
        asyncio.run(handle_websocket(url, message, key, merge, merge_key))
    
    thread = threading.Thread(target=run_async)
    thread.daemon = True
    thread.start()
    
    return jsonify({"message": "WebSocket connection initiated"}), 200

@app.route('/api/ws/message/<key>', methods=['GET'])
def get_ws_message(key):
    if key not in ws_messages:
        return jsonify({"error": "No messages found for this key"}), 404
    
    return ws_messages[key]

@app.route('/api/ws/all', methods=['GET'])
def get_ws_all():
    return jsonify(ws_connections.keys())


@app.route('/api/ws/keepalive/<key>', methods=['POST'])

def keepalive_ws(key):
    if key not in ws_connections:
        return jsonify({"error": "No active connection found for this key"}), 404
    
    ws_last_keepalive[key] = time.time()
    return jsonify({"message": "Keepalive successful"}), 200


def find_value_by_key(json_obj, target_key):
    json_obj = json.loads(json_obj)
    def _search(obj):
        if isinstance(obj, dict):
            for key, value in obj.items():
                if key == target_key:
                    return value
                if isinstance(value, (dict, list)):
                    result = _search(value)
                    if result is not None:
                        return result
        elif isinstance(obj, list):
            for item in obj:
                if isinstance(item, (dict, list)):
                    result = _search(item)
                    if result is not None:
                        return result
        return None
    
    return _search(json_obj)

if __name__ == '__main__':
    app.run(port=50888, threaded=True)
