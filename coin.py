import json
from flask import Flask, request, jsonify, render_template_string
from flask_cors import CORS
import requests
import logging
import threading
import time
from datetime import datetime
import websocket
import lighter

app = Flask(__name__)
CORS(app)

# 代理配置
proxy_enabled = True
proxy_port = 7890

# 只配置错误日志，关闭所有debug信息
logging.basicConfig(level=logging.ERROR)

# 关闭各个模块的debug日志
logging.getLogger('urllib3.connectionpool').setLevel(logging.WARNING)
logging.getLogger('werkzeug').setLevel(logging.WARNING)
logging.getLogger('asyncio').setLevel(logging.WARNING)
logging.getLogger('aiohttp').setLevel(logging.WARNING)
logging.getLogger('root').setLevel(logging.WARNING)
logging.getLogger().setLevel(logging.WARNING)

# 禁用所有DEBUG级别的日志
import logging
logging.disable(logging.DEBUG)

# Session with connection pooling
session = requests.Session()
API_KEY_PRIVATE_KEY = None
ACCOUNT_INDEX = None
API_KEY_INDEX = None
LIGHTER_BASE_URL = 'https://mainnet.zklighter.elliot.ai'


lighter_cache = {}
# 代理配置缓存
_cached_proxies = None
_last_proxy_enabled = None
_last_proxy_port = None
# lighter_init 调用频率限制
_last_lighter_init_call = 0

# 获取代理配置（带缓存）
def get_proxies():
    global _cached_proxies, _last_proxy_enabled, _last_proxy_port
    
    # 如果配置没有变化，直接返回缓存的代理配置
    if (_last_proxy_enabled == proxy_enabled and 
        _last_proxy_port == proxy_port and 
        _cached_proxies is not None):
        return _cached_proxies
    
    # 配置发生变化，更新缓存
    _last_proxy_enabled = proxy_enabled
    _last_proxy_port = proxy_port
    
    if proxy_enabled:
        _cached_proxies = {
            'http': f'http://127.0.0.1:{proxy_port}',
            'https': f'http://127.0.0.1:{proxy_port}'
        }
        lighter.api_client.configuration.proxy = _cached_proxies
    else:
        _cached_proxies = None
    
    return _cached_proxies

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
        proxies = get_proxies()
        if method == 'GET':
            response = session.get(url, headers=headers, proxies=proxies, timeout=5)
        elif method == 'POST':
            payload = bytes.fromhex(request_data).decode('utf-8') if request_data else None
            response = session.post(url, data=payload, headers=headers, proxies=proxies, timeout=5)
        else:
            return None, "Unsupported HTTP method", 400
        return response, None, response.status_code
    except requests.exceptions.RequestException as e:
        #输出堆栈
        import traceback
        traceback.print_exc()
        logging.error(f"Request failed: {e}")
        return None, str(e), 500


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

@app.route('/api/proxy/lighter/<type>', methods=['GET', 'POST'])
async def lighter_proxy(type):
    data = request.get_json()
    if type == 'init':
        # 检查10秒内是否已经调用过
        global _last_lighter_init_call
        current_time = time.time()
        if current_time - _last_lighter_init_call < 10:
            return jsonify({"message": "插件开启成功"}), 200
        try:
            result = lighter_init(data)
            _last_lighter_init_call = current_time  
            return jsonify(result)
        except Exception as e:
            return jsonify({"error": str(e)}), 500
    elif type == 'order':
        try:
            result = await lighter_order(data)
            return jsonify(result)
        except Exception as e:
            import traceback
            traceback.print_exc()
            return jsonify({"error": str(e)}), 500
    else:
        return jsonify({"message": "插件开启成功"})

# 代理控制页面
@app.route('/')
def proxy_control():
    html_template = """
    <!DOCTYPE html>
    <html lang="zh-CN">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>代理控制面板</title>
        <style>
            body {
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                max-width: 600px;
                margin: 50px auto;
                padding: 20px;
                background-color: #f5f5f5;
            }
            .container {
                background: white;
                padding: 30px;
                border-radius: 10px;
                box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            }
            h1 {
                color: #333;
                text-align: center;
                margin-bottom: 30px;
            }
            .form-group {
                margin-bottom: 20px;
            }
            label {
                display: block;
                margin-bottom: 8px;
                font-weight: 500;
                color: #555;
            }
            input[type="number"] {
                width: 100%;
                padding: 10px;
                border: 1px solid #ddd;
                border-radius: 5px;
                font-size: 16px;
                box-sizing: border-box;
            }
            .checkbox-group {
                display: flex;
                align-items: center;
                margin-bottom: 20px;
            }
            .checkbox-group input[type="checkbox"] {
                margin-right: 10px;
                transform: scale(1.2);
            }
            .btn {
                background-color: #007bff;
                color: white;
                padding: 12px 24px;
                border: none;
                border-radius: 5px;
                cursor: pointer;
                font-size: 16px;
                width: 100%;
                margin-top: 10px;
            }
            .btn:hover {
                background-color: #0056b3;
            }
            .status {
                margin-top: 20px;
                padding: 15px;
                border-radius: 5px;
                text-align: center;
                font-weight: 500;
            }
            .status.success {
                background-color: #d4edda;
                color: #155724;
                border: 1px solid #c3e6cb;
            }
            .status.error {
                background-color: #f8d7da;
                color: #721c24;
                border: 1px solid #f5c6cb;
            }
            .current-status {
                background-color: #e9ecef;
                padding: 15px;
                border-radius: 5px;
                margin-bottom: 20px;
            }
            .status-item {
                display: flex;
                justify-content: space-between;
                margin-bottom: 8px;
            }
            .status-value {
                font-weight: bold;
                color: #007bff;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>代理控制面板</h1>
            
            <div class="current-status">
                <h3>当前状态</h3>
                <div class="status-item">
                    <span>代理状态:</span>
                    <span class="status-value" id="currentEnabled">加载中...</span>
                </div>
                <div class="status-item">
                    <span>代理端口:</span>
                    <span class="status-value" id="currentPort">加载中...</span>
                </div>
            </div>

            <form id="proxyForm">
                <div class="checkbox-group">
                    <input type="checkbox" id="proxyEnabled" name="proxyEnabled">
                    <label for="proxyEnabled">启用代理</label>
                </div>
                
                <div class="form-group">
                    <label for="proxyPort">代理端口:</label>
                    <input type="number" id="proxyPort" name="proxyPort" min="1" max="65535" placeholder="请输入端口号">
                </div>
                
                <button type="submit" class="btn">保存设置</button>
            </form>
            
            <div id="statusMessage" class="status" style="display: none;"></div>
        </div>

        <script>
            // 加载当前状态
            function loadCurrentStatus() {
                fetch('/api/proxy/status')
                    .then(response => response.json())
                    .then(data => {
                        document.getElementById('currentEnabled').textContent = data.enabled ? '已启用' : '已禁用';
                        document.getElementById('currentPort').textContent = data.port;
                        document.getElementById('proxyEnabled').checked = data.enabled;
                        document.getElementById('proxyPort').value = data.port;
                    })
                    .catch(error => {
                        console.error('加载状态失败:', error);
                        document.getElementById('currentEnabled').textContent = '加载失败';
                        document.getElementById('currentPort').textContent = '加载失败';
                    });
            }

            // 显示状态消息
            function showMessage(message, isError = false) {
                const statusDiv = document.getElementById('statusMessage');
                statusDiv.textContent = message;
                statusDiv.className = 'status ' + (isError ? 'error' : 'success');
                statusDiv.style.display = 'block';
                
                setTimeout(() => {
                    statusDiv.style.display = 'none';
                }, 3000);
            }

            // 表单提交
            document.getElementById('proxyForm').addEventListener('submit', function(e) {
                e.preventDefault();
                
                const enabled = document.getElementById('proxyEnabled').checked;
                const port = parseInt(document.getElementById('proxyPort').value);
                
                if (!port || port < 1 || port > 65535) {
                    showMessage('请输入有效的端口号 (1-65535)', true);
                    return;
                }
                
                fetch('/api/proxy/config', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({
                        enabled: enabled,
                        port: port
                    })
                })
                .then(response => response.json())
                .then(data => {
                    if (data.success) {
                        showMessage('设置保存成功！');
                        loadCurrentStatus(); // 重新加载状态
                    } else {
                        showMessage('保存失败: ' + (data.error || '未知错误'), true);
                    }
                })
                .catch(error => {
                    console.error('保存失败:', error);
                    showMessage('保存失败: ' + error.message, true);
                });
            });

            // 页面加载时获取当前状态
            loadCurrentStatus();
        </script>
    </body>
    </html>
    """
    return render_template_string(html_template)

# 获取代理状态API
@app.route('/api/proxy/status', methods=['GET'])
def get_proxy_status():
    return jsonify({
        "enabled": proxy_enabled,
        "port": proxy_port
    })

# 设置代理配置API
@app.route('/api/proxy/config', methods=['POST'])
def set_proxy_config():
    global proxy_enabled, proxy_port
    
    data = request.get_json()
    enabled = data.get('enabled')
    port = data.get('port')
    
    if enabled is None:
        return jsonify({"success": False, "error": "缺少enabled参数"}), 400
    
    if port is None:
        return jsonify({"success": False, "error": "缺少port参数"}), 400
    
    if not isinstance(port, int) or port < 1 or port > 65535:
        return jsonify({"success": False, "error": "端口号必须在1-65535之间"}), 400
    
    try:
        proxy_enabled = bool(enabled)
        proxy_port = int(port)
        
        # 清除代理配置缓存，强制下次调用时重新生成
        global _cached_proxies, _last_proxy_enabled, _last_proxy_port
        _cached_proxies = None
        _last_proxy_enabled = None
        _last_proxy_port = None
        
        return jsonify({
            "success": True,
            "message": "代理配置已更新",
            "enabled": proxy_enabled,
            "port": proxy_port
        })
    except Exception as e:
        return jsonify({"success": False, "error": f"更新配置失败: {str(e)}"}), 500

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

def lighter_init(data):
    global API_KEY_PRIVATE_KEY, ACCOUNT_INDEX, API_KEY_INDEX
    API_KEY_PRIVATE_KEY = data.get('private_key')
    ACCOUNT_INDEX = int(data.get('account_index'))
    API_KEY_INDEX = int(data.get('api_key_index'))
    return {
        'message': '插件开启成功'
    }
async def lighter_order(data):
    
    lighter_client = lighter.SignerClient(
        url=LIGHTER_BASE_URL,
        private_key=API_KEY_PRIVATE_KEY,
        account_index=ACCOUNT_INDEX,
        api_key_index=API_KEY_INDEX,
    )

    tx = await lighter_client.create_market_order(
        market_index=data.get('market_index'),
        client_order_index=int(time.time()*1000),
        base_amount=data.get('base_amount'),
        avg_execution_price=data.get('avg_execution_price'),
        is_ask=data.get('is_ask'),
    )
    await lighter_client.close()
    # 检查交易是否成功
    if tx[1] and hasattr(tx[1], 'tx_hash') and tx[1].tx_hash:
        # 成功：返回交易哈希
        return {'tx': tx[1].tx_hash}
    elif tx[2]:
        # 失败：返回错误信息
        return {'error': tx[2]}
    else:
        # 其他情况：返回默认错误
        return {'error': '交易失败，未知错误'}




if __name__ == '__main__':
    websocket.enableTrace(False)  # 禁用 WebSocket 调试日志
    app.run(port=50888, threaded=True)
