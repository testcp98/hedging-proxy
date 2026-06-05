package main

import (
	"encoding/hex"
	"encoding/json"
	"io"
	"log"
	"net/http"
	"os"
	"strings"

	lightersvc "github.com/testcp98/coin-go/internal/lighter"
	"github.com/testcp98/coin-go/internal/config"
	"github.com/testcp98/coin-go/internal/ws"
)

type Server struct {
	proxy   *config.ProxyConfig
	client  *http.Client
	ws      *ws.Manager
	lighter *lightersvc.Service
}

func main() {
	proxyCfg := config.NewProxyConfig()
	srv := &Server{
		proxy:   proxyCfg,
		client:  config.NewHTTPClient(proxyCfg),
		ws:      ws.NewManager(),
		lighter: lightersvc.NewService(),
	}

	mux := http.NewServeMux()
	mux.HandleFunc("/", srv.controlPage)
	mux.HandleFunc("/api/get", srv.getHealth)
	mux.HandleFunc("/api/proxy", srv.proxyRequest)
	mux.HandleFunc("/api/proxy/status", srv.proxyStatus)
	mux.HandleFunc("/api/proxy/config", srv.proxyConfig)
	mux.HandleFunc("/api/proxy/lighter/", srv.lighterProxy)
	mux.HandleFunc("/api/ws/connect", srv.wsConnect)
	mux.HandleFunc("/api/ws/message/", srv.wsMessage)
	mux.HandleFunc("/api/ws/all", srv.wsAll)
	mux.HandleFunc("/api/ws/keepalive/", srv.wsKeepalive)

	port := os.Getenv("PORT")
	if port == "" {
		port = "50888"
	}

	enabled, _ := proxyCfg.Status()
	log.Printf("coin-go listening on :%s (proxy enabled=%v)", port, enabled)

	server := &http.Server{
		Addr:    ":" + port,
		Handler: corsMiddleware(mux),
	}
	log.Fatal(server.ListenAndServe())
}

func corsMiddleware(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Access-Control-Allow-Origin", "*")
		w.Header().Set("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
		w.Header().Set("Access-Control-Allow-Headers", "Content-Type")
		if r.Method == http.MethodOptions {
			w.WriteHeader(http.StatusNoContent)
			return
		}
		next.ServeHTTP(w, r)
	})
}

func writeJSON(w http.ResponseWriter, status int, v interface{}) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(v)
}

func readJSON(r *http.Request, v interface{}) error {
	defer r.Body.Close()
	return json.NewDecoder(r.Body).Decode(v)
}

func (s *Server) getHealth(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		http.NotFound(w, r)
		return
	}
	writeJSON(w, http.StatusOK, map[string]string{"message": "插件开启成功"})
}

type proxyBody struct {
	U string            `json:"u"`
	M string            `json:"m"`
	D string            `json:"d"`
	H map[string]string `json:"h"`
	T string            `json:"t"`
}

func (s *Server) proxyRequest(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.NotFound(w, r)
		return
	}

	var data proxyBody
	if err := readJSON(r, &data); err != nil {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": err.Error()})
		return
	}

	method := strings.ToUpper(data.M)
	if method == "" {
		method = http.MethodGet
	}

	var body io.Reader
	if method == http.MethodPost && data.D != "" {
		raw, err := hex.DecodeString(data.D)
		if err != nil {
			writeJSON(w, http.StatusBadRequest, map[string]string{"error": "invalid hex data"})
			return
		}
		body = strings.NewReader(string(raw))
	}

	req, err := http.NewRequestWithContext(r.Context(), method, data.U, body)
	if err != nil {
		writeJSON(w, http.StatusInternalServerError, map[string]string{"error": err.Error()})
		return
	}
	for k, v := range data.H {
		req.Header.Set(k, v)
	}

	resp, err := s.client.Do(req)
	if err != nil {
		writeJSON(w, http.StatusInternalServerError, map[string]string{"error": err.Error()})
		return
	}
	defer resp.Body.Close()

	respBody, err := io.ReadAll(resp.Body)
	if err != nil {
		writeJSON(w, http.StatusInternalServerError, map[string]string{"error": err.Error()})
		return
	}

	if strings.ToUpper(data.T) == "JSON" {
		var parsed interface{}
		if err := json.Unmarshal(respBody, &parsed); err != nil {
			writeJSON(w, http.StatusInternalServerError, map[string]string{"error": "Invalid JSON response"})
			return
		}
		writeJSON(w, resp.StatusCode, parsed)
		return
	}

	w.Header().Set("Content-Type", "text/plain; charset=utf-8")
	w.WriteHeader(resp.StatusCode)
	_, _ = w.Write(respBody)
}

func (s *Server) proxyStatus(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		http.NotFound(w, r)
		return
	}
	enabled, port := s.proxy.Status()
	writeJSON(w, http.StatusOK, map[string]interface{}{"enabled": enabled, "port": port})
}

func (s *Server) proxyConfig(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.NotFound(w, r)
		return
	}

	var data struct {
		Enabled *bool `json:"enabled"`
		Port    *int  `json:"port"`
	}
	if err := readJSON(r, &data); err != nil {
		writeJSON(w, http.StatusBadRequest, map[string]interface{}{"success": false, "error": err.Error()})
		return
	}
	if data.Enabled == nil {
		writeJSON(w, http.StatusBadRequest, map[string]interface{}{"success": false, "error": "缺少enabled参数"})
		return
	}
	if data.Port == nil {
		writeJSON(w, http.StatusBadRequest, map[string]interface{}{"success": false, "error": "缺少port参数"})
		return
	}
	if *data.Port < 1 || *data.Port > 65535 {
		writeJSON(w, http.StatusBadRequest, map[string]interface{}{"success": false, "error": "端口号必须在1-65535之间"})
		return
	}

	s.proxy.Update(*data.Enabled, *data.Port)
	s.client = config.NewHTTPClient(s.proxy)

	writeJSON(w, http.StatusOK, map[string]interface{}{
		"success": true,
		"message": "代理配置已更新",
		"enabled": *data.Enabled,
		"port":    *data.Port,
	})
}

func (s *Server) lighterProxy(w http.ResponseWriter, r *http.Request) {
	typeName := strings.TrimPrefix(r.URL.Path, "/api/proxy/lighter/")
	if typeName != "init" && typeName != "order" {
		writeJSON(w, http.StatusOK, map[string]string{"message": "插件开启成功"})
		return
	}

	var data map[string]interface{}
	if r.Method == http.MethodPost {
		if err := readJSON(r, &data); err != nil {
			writeJSON(w, http.StatusBadRequest, map[string]string{"error": err.Error()})
			return
		}
	}

	switch typeName {
	case "init":
		if !s.lighter.InitAllowed() {
			writeJSON(w, http.StatusOK, map[string]string{"message": "插件开启成功"})
			return
		}
		result, err := s.lighter.Init(data)
		if err != nil {
			writeJSON(w, http.StatusInternalServerError, map[string]string{"error": err.Error()})
			return
		}
		s.lighter.MarkInitCalled()
		writeJSON(w, http.StatusOK, result)
	case "order":
		result, err := s.lighter.PlaceOrder(data)
		if err != nil {
			writeJSON(w, http.StatusInternalServerError, map[string]string{"error": err.Error()})
			return
		}
		writeJSON(w, http.StatusOK, result)
	}
}

func (s *Server) wsConnect(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.NotFound(w, r)
		return
	}

	var data struct {
		URL      string `json:"url"`
		Message  string `json:"message"`
		Key      string `json:"key"`
		Merge    bool   `json:"merge"`
		MergeKey string `json:"merge_key"`
		Item     string `json:"item"`
	}
	if err := readJSON(r, &data); err != nil {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": err.Error()})
		return
	}
	if data.URL == "" || data.Message == "" || data.Key == "" {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "Missing required parameters"})
		return
	}
	if s.ws.HasConnection(data.Key) {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "Connection with this key already exists"})
		return
	}

	s.ws.Connect(data.URL, data.Message, data.Key, data.Merge, data.MergeKey, data.Item)
	writeJSON(w, http.StatusOK, map[string]string{"message": "WebSocket connection initiated"})
}

func (s *Server) wsMessage(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		http.NotFound(w, r)
		return
	}
	key := strings.TrimPrefix(r.URL.Path, "/api/ws/message/")
	msg, ok := s.ws.GetMessage(key)
	if !ok {
		writeJSON(w, http.StatusNotFound, map[string]string{"error": "No messages found for this key"})
		return
	}
	writeJSON(w, http.StatusOK, msg)
}

func (s *Server) wsAll(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		http.NotFound(w, r)
		return
	}
	writeJSON(w, http.StatusOK, s.ws.AllKeys())
}

func (s *Server) wsKeepalive(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.NotFound(w, r)
		return
	}
	key := strings.TrimPrefix(r.URL.Path, "/api/ws/keepalive/")
	if !s.ws.Keepalive(key) {
		writeJSON(w, http.StatusNotFound, map[string]string{"error": "No active connection found for this key"})
		return
	}
	writeJSON(w, http.StatusOK, map[string]string{"message": "Keepalive successful"})
}

func (s *Server) controlPage(w http.ResponseWriter, r *http.Request) {
	if r.URL.Path != "/" {
		http.NotFound(w, r)
		return
	}
	w.Header().Set("Content-Type", "text/html; charset=utf-8")
	_, _ = w.Write([]byte(controlHTML))
}

const controlHTML = `<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>代理控制面板</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 600px; margin: 50px auto; padding: 20px; background-color: #f5f5f5; }
        .container { background: white; padding: 30px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
        h1 { color: #333; text-align: center; margin-bottom: 30px; }
        .form-group { margin-bottom: 20px; }
        label { display: block; margin-bottom: 8px; font-weight: 500; color: #555; }
        input[type="number"] { width: 100%; padding: 10px; border: 1px solid #ddd; border-radius: 5px; font-size: 16px; box-sizing: border-box; }
        .checkbox-group { display: flex; align-items: center; margin-bottom: 20px; }
        .checkbox-group input[type="checkbox"] { margin-right: 10px; transform: scale(1.2); }
        .btn { background-color: #007bff; color: white; padding: 12px 24px; border: none; border-radius: 5px; cursor: pointer; font-size: 16px; width: 100%; margin-top: 10px; }
        .btn:hover { background-color: #0056b3; }
        .status { margin-top: 20px; padding: 15px; border-radius: 5px; text-align: center; font-weight: 500; }
        .status.success { background-color: #d4edda; color: #155724; border: 1px solid #c3e6cb; }
        .status.error { background-color: #f8d7da; color: #721c24; border: 1px solid #f5c6cb; }
        .current-status { background-color: #e9ecef; padding: 15px; border-radius: 5px; margin-bottom: 20px; }
        .status-item { display: flex; justify-content: space-between; margin-bottom: 8px; }
        .status-value { font-weight: bold; color: #007bff; }
        .docker-note { background: #fff3cd; padding: 12px; border-radius: 5px; margin-bottom: 20px; font-size: 14px; color: #856404; }
    </style>
</head>
<body>
    <div class="container">
        <h1>代理控制面板</h1>
        <div class="docker-note">Docker 模式默认直连网络，无需本地代理。如需使用宿主机代理，请启用并设置端口（如 7890），代理地址为 host.docker.internal。</div>
        <div class="current-status">
            <h3>当前状态</h3>
            <div class="status-item"><span>代理状态:</span><span class="status-value" id="currentEnabled">加载中...</span></div>
            <div class="status-item"><span>代理端口:</span><span class="status-value" id="currentPort">加载中...</span></div>
        </div>
        <form id="proxyForm">
            <div class="checkbox-group"><input type="checkbox" id="proxyEnabled"><label for="proxyEnabled">启用代理</label></div>
            <div class="form-group"><label for="proxyPort">代理端口:</label><input type="number" id="proxyPort" min="1" max="65535" placeholder="请输入端口号"></div>
            <button type="submit" class="btn">保存设置</button>
        </form>
        <div id="statusMessage" class="status" style="display: none;"></div>
    </div>
    <script>
        function loadCurrentStatus() {
            fetch('/api/proxy/status').then(r => r.json()).then(data => {
                document.getElementById('currentEnabled').textContent = data.enabled ? '已启用' : '已禁用';
                document.getElementById('currentPort').textContent = data.port;
                document.getElementById('proxyEnabled').checked = data.enabled;
                document.getElementById('proxyPort').value = data.port;
            }).catch(() => {
                document.getElementById('currentEnabled').textContent = '加载失败';
                document.getElementById('currentPort').textContent = '加载失败';
            });
        }
        function showMessage(message, isError) {
            const statusDiv = document.getElementById('statusMessage');
            statusDiv.textContent = message;
            statusDiv.className = 'status ' + (isError ? 'error' : 'success');
            statusDiv.style.display = 'block';
            setTimeout(() => { statusDiv.style.display = 'none'; }, 3000);
        }
        document.getElementById('proxyForm').addEventListener('submit', function(e) {
            e.preventDefault();
            const enabled = document.getElementById('proxyEnabled').checked;
            const port = parseInt(document.getElementById('proxyPort').value);
            if (!port || port < 1 || port > 65535) { showMessage('请输入有效的端口号 (1-65535)', true); return; }
            fetch('/api/proxy/config', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ enabled, port })
            }).then(r => r.json()).then(data => {
                if (data.success) { showMessage('设置保存成功！'); loadCurrentStatus(); }
                else { showMessage('保存失败: ' + (data.error || '未知错误'), true); }
            }).catch(err => showMessage('保存失败: ' + err.message, true));
        });
        loadCurrentStatus();
    </script>
</body>
</html>`
