package ws

import (
	"sync"
	"time"

	"github.com/gorilla/websocket"
	"github.com/testcp98/coin-go/internal/util"
)

const WSTimeout = 10 * time.Second

type Manager struct {
	mu            sync.RWMutex
	connections   map[string]*websocket.Conn
	messages      map[string]interface{}
	lastKeepalive map[string]time.Time
}

func NewManager() *Manager {
	return &Manager{
		connections:   make(map[string]*websocket.Conn),
		messages:      make(map[string]interface{}),
		lastKeepalive: make(map[string]time.Time),
	}
}

func (m *Manager) HasConnection(key string) bool {
	m.mu.RLock()
	defer m.mu.RUnlock()
	_, ok := m.connections[key]
	return ok
}

func (m *Manager) Connect(url, message, key string, merge bool, mergeKey, itemKey string) {
	m.mu.Lock()
	m.messages[key] = nil
	m.lastKeepalive[key] = time.Now()
	m.mu.Unlock()

	go m.run(url, message, key, merge, mergeKey, itemKey)
}

func (m *Manager) run(url, message, key string, merge bool, mergeKey, itemKey string) {
	conn, _, err := websocket.DefaultDialer.Dial(url, nil)
	if err != nil {
		m.cleanup(key)
		return
	}

	m.mu.Lock()
	m.connections[key] = conn
	m.mu.Unlock()

	if err := conn.WriteMessage(websocket.TextMessage, []byte(message)); err != nil {
		m.cleanup(key)
		return
	}

	go m.watchTimeout(key, conn)

	for {
		_, msg, err := conn.ReadMessage()
		if err != nil {
			break
		}
		m.handleMessage(key, string(msg), merge, mergeKey, itemKey)
	}

	m.cleanup(key)
}

func (m *Manager) watchTimeout(key string, conn *websocket.Conn) {
	ticker := time.NewTicker(time.Second)
	defer ticker.Stop()

	for range ticker.C {
		m.mu.RLock()
		last, ok := m.lastKeepalive[key]
		m.mu.RUnlock()
		if !ok {
			return
		}
		if time.Since(last) > WSTimeout {
			conn.Close()
			return
		}
	}
}

func (m *Manager) handleMessage(key, message string, merge bool, mergeKey, itemKey string) {
	m.mu.Lock()
	defer m.mu.Unlock()

	if !merge {
		m.messages[key] = message
		return
	}

	data := util.FindValueByKey(message, mergeKey)
	if data == nil {
		return
	}

	existing := m.messages[key]
	if existing != nil {
		switch ex := existing.(type) {
		case []interface{}:
			if newList, ok := data.([]interface{}); ok {
				m.messages[key] = append(ex, newList...)
			}
		case map[string]interface{}:
			if newMap, ok := data.(map[string]interface{}); ok {
				for k, v := range newMap {
					ex[k] = v
				}
				m.messages[key] = ex
			}
		default:
			m.messages[key] = data
		}
	} else {
		m.messages[key] = data
	}

	if itemKey != "" {
		if list, ok := m.messages[key].([]interface{}); ok {
			m.messages[key] = util.DedupeByKey(list, itemKey)
		}
	}
}

func (m *Manager) cleanup(key string) {
	m.mu.Lock()
	defer m.mu.Unlock()
	if conn, ok := m.connections[key]; ok {
		conn.Close()
		delete(m.connections, key)
	}
	delete(m.lastKeepalive, key)
}

func (m *Manager) GetMessage(key string) (interface{}, bool) {
	m.mu.RLock()
	defer m.mu.RUnlock()
	msg, ok := m.messages[key]
	return msg, ok
}

func (m *Manager) AllKeys() []string {
	m.mu.RLock()
	defer m.mu.RUnlock()
	keys := make([]string, 0, len(m.connections))
	for k := range m.connections {
		keys = append(keys, k)
	}
	return keys
}

func (m *Manager) Keepalive(key string) bool {
	m.mu.Lock()
	defer m.mu.Unlock()
	if _, ok := m.connections[key]; !ok {
		return false
	}
	m.lastKeepalive[key] = time.Now()
	return true
}
