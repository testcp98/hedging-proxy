import json
from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
import logging
import threading
import time
from datetime import datetime
import websocket

app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": "*"}}, supports_credentials=True)
proxy_port = 7890

# 只配置错误日志
logging.basicConfig(level=logging.ERROR)

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
WS_TIMEOUT = 10

def handle_websocket(url, message, key, merge, merge_key, item_key):
    def on_message(ws, message):
        try:
            if merge:
                data = find_value_by_key(message, merge_key)
                if data:
                    if ws_messages[key]:
                        if isinstance(ws_messages[key], list):
                            ws_messages[key].extend(data)
                        else:
                            ws_messages[key].update(data)
                    else:
                        ws_messages[key] = data
                if item_key:
                    ws_messages[key] = list({item[item_key]: item for item in ws_messages[key]}.values())
            else:
                ws_messages[key] = message
        except Exception as e:
            logging.error(f"Message handling error: {e}")

    def on_error(ws, error):
        logging.error(f"WebSocket error: {error}")

    def on_close(ws, close_status_code, close_msg):
        if key in ws_connections:
            del ws_connections[key]
        if key in ws_last_keepalive:
            del ws_last_keepalive[key]

    def on_open(ws):
        ws.send(message)

    def check_timeout():
        while True:
            time.sleep(1)
            if key not in ws_last_keepalive:
                break
            if time.time() - ws_last_keepalive[key] > WS_TIMEOUT:
                ws.close()
                break

    # 创建 WebSocket 连接
    ws = websocket.WebSocketApp(
        url,
        on_message=on_message,
        on_error=on_error,
        on_close=on_close,
        on_open=on_open
    )
    
    ws_connections[key] = ws
    ws_messages[key] = None
    ws_last_keepalive[key] = time.time()

    # 启动超时检查线程
    timeout_thread = threading.Thread(target=check_timeout)
    timeout_thread.daemon = True
    timeout_thread.start()

    # 运行 WebSocket
    ws.run_forever()

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
    item = data.get('item')
    
    if not all([url, message, key]):
        return jsonify({"error": "Missing required parameters"}), 400
    
    if key in ws_connections:
        return jsonify({"error": "Connection with this key already exists"}), 400
    
    thread = threading.Thread(
        target=handle_websocket,
        args=(url, message, key, merge, merge_key, item)
    )
    thread.daemon = True
    thread.start()
    
    return jsonify({"message": "WebSocket connection initiated"}), 200

@app.route('/api/ws/message/<key>', methods=['GET'])
def get_ws_message(key):
    if key not in ws_messages:
        return jsonify({"error": "No messages found for this key"}), 404
    
    try:
        return jsonify(ws_messages[key]), 200
    except Exception as e:
        return jsonify({"error": f"获取消息失败: {str(e)}"}), 500

@app.route('/api/ws/all', methods=['GET'])
def get_ws_all():
    return jsonify(list(ws_connections.keys()))

@app.route('/api/ws/keepalive/<key>', methods=['POST'])
def keepalive_ws(key):
    if key not in ws_connections:
        return jsonify({"error": "No active connection found for this key"}), 404
    
    ws_last_keepalive[key] = time.time()
    return jsonify({"message": "Keepalive successful"}), 200

def find_value_by_key(json_obj, target_key):
    if isinstance(json_obj, str):
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
    websocket.enableTrace(False)  # 禁用 WebSocket 调试日志
    app.run(port=50888, threaded=True)
