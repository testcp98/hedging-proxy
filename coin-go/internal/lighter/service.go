package lighter

import (
	"encoding/json"
	"fmt"
	"sync"
	"time"

	lclient "github.com/0xJord4n/lighter-go/client"
	lhttp "github.com/0xJord4n/lighter-go/client/http"
	"github.com/0xJord4n/lighter-go/types"
	"github.com/0xJord4n/lighter-go/types/txtypes"
)

const BaseURL = "https://mainnet.zklighter.elliot.ai"

type Service struct {
	mu                sync.RWMutex
	privateKey        string
	accountIndex      int64
	apiKeyIndex       uint8
	lastInitCall      time.Time
	initRateLimit     time.Duration
}

func NewService() *Service {
	return &Service{
		initRateLimit: 10 * time.Second,
	}
}

func (s *Service) Init(data map[string]interface{}) (map[string]interface{}, error) {
	s.mu.Lock()
	defer s.mu.Unlock()

	if pk, ok := data["private_key"].(string); ok {
		s.privateKey = pk
	}
	if v, ok := data["account_index"]; ok {
		if n, ok := toInt64(v); ok {
			s.accountIndex = n
		}
	}
	if v, ok := data["api_key_index"]; ok {
		if n, ok := toInt64(v); ok {
			s.apiKeyIndex = uint8(n)
		}
	}

	return map[string]interface{}{"message": "插件开启成功"}, nil
}

func (s *Service) InitAllowed() bool {
	s.mu.RLock()
	defer s.mu.RUnlock()
	return time.Since(s.lastInitCall) >= s.initRateLimit
}

func (s *Service) MarkInitCalled() {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.lastInitCall = time.Now()
}

func (s *Service) PlaceOrder(data map[string]interface{}) (map[string]interface{}, error) {
	s.mu.RLock()
	privateKey := s.privateKey
	accountIndex := s.accountIndex
	apiKeyIndex := s.apiKeyIndex
	s.mu.RUnlock()

	if privateKey == "" {
		return map[string]interface{}{"error": "lighter not initialized"}, nil
	}

	marketIndex, ok := toInt16(data["market_index"])
	if !ok {
		return map[string]interface{}{"error": "invalid market_index"}, nil
	}
	baseAmount, ok := toInt64(data["base_amount"])
	if !ok {
		return map[string]interface{}{"error": "invalid base_amount"}, nil
	}
	avgPrice, ok := toUint32(data["avg_execution_price"])
	if !ok {
		return map[string]interface{}{"error": "invalid avg_execution_price"}, nil
	}
	isAsk, ok := toUint8(data["is_ask"])
	if !ok {
		return map[string]interface{}{"error": "invalid is_ask"}, nil
	}

	clientOrderIndex := time.Now().UnixMilli()
	if v, ok := data["client_order_index"]; ok {
		if n, ok := toInt64(v); ok {
			clientOrderIndex = n
		}
	}

	httpClient := lhttp.NewFullClient(BaseURL)
	signerClient, err := lclient.NewSignerClient(
		httpClient,
		privateKey,
		lclient.Mainnet.ChainID(),
		apiKeyIndex,
		accountIndex,
		nil,
	)
	if err != nil {
		return map[string]interface{}{"error": err.Error()}, nil
	}

	req := &types.CreateOrderTxReq{
		MarketIndex:      marketIndex,
		ClientOrderIndex: clientOrderIndex,
		BaseAmount:       baseAmount,
		Price:            avgPrice,
		IsAsk:            isAsk,
		Type:             txtypes.MarketOrder,
		TimeInForce:      txtypes.ImmediateOrCancel,
		ReduceOnly:       0,
		TriggerPrice:     0,
		OrderExpiry:      0,
	}

	txInfo, err := signerClient.GetCreateOrderTransaction(req, &types.TransactOpts{
		Nonce: types.NewInt64(-1),
	})
	if err != nil {
		return map[string]interface{}{"error": err.Error()}, nil
	}

	resp, err := signerClient.SendAndSubmit(txInfo)
	if err != nil {
		return map[string]interface{}{"error": err.Error()}, nil
	}

	if resp != nil && resp.TxHash != "" {
		return map[string]interface{}{"tx": resp.TxHash}, nil
	}

	return map[string]interface{}{"error": "交易失败，未知错误"}, nil
}

func toInt64(v interface{}) (int64, bool) {
	switch t := v.(type) {
	case float64:
		return int64(t), true
	case int64:
		return t, true
	case int:
		return int64(t), true
	case json.Number:
		n, err := t.Int64()
		return n, err == nil
	default:
		return 0, false
	}
}

func toInt16(v interface{}) (int16, bool) {
	n, ok := toInt64(v)
	if !ok || n < -32768 || n > 32767 {
		return 0, false
	}
	return int16(n), true
}

func toUint32(v interface{}) (uint32, bool) {
	n, ok := toInt64(v)
	if !ok || n < 0 {
		return 0, false
	}
	return uint32(n), true
}

func toUint8(v interface{}) (uint8, bool) {
	n, ok := toInt64(v)
	if !ok || n < 0 || n > 255 {
		return 0, false
	}
	return uint8(n), true
}

func (s *Service) String() string {
	s.mu.RLock()
	defer s.mu.RUnlock()
	return fmt.Sprintf("account=%d api_key=%d", s.accountIndex, s.apiKeyIndex)
}
