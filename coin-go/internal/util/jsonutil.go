package util

import (
	"encoding/json"
)

func FindValueByKey(jsonObj interface{}, targetKey string) interface{} {
	if s, ok := jsonObj.(string); ok {
		var parsed interface{}
		if err := json.Unmarshal([]byte(s), &parsed); err != nil {
			return nil
		}
		jsonObj = parsed
	}
	return search(jsonObj, targetKey)
}

func search(obj interface{}, targetKey string) interface{} {
	switch v := obj.(type) {
	case map[string]interface{}:
		for key, value := range v {
			if key == targetKey {
				return value
			}
			if result := search(value, targetKey); result != nil {
				return result
			}
		}
	case []interface{}:
		for _, item := range v {
			if result := search(item, targetKey); result != nil {
				return result
			}
		}
	}
	return nil
}

func DedupeByKey(items []interface{}, itemKey string) []interface{} {
	seen := make(map[string]struct{})
	result := make([]interface{}, 0, len(items))
	for _, item := range items {
		m, ok := item.(map[string]interface{})
		if !ok {
			continue
		}
		keyVal, ok := m[itemKey]
		if !ok {
			continue
		}
		keyStr := toString(keyVal)
		if _, exists := seen[keyStr]; exists {
			continue
		}
		seen[keyStr] = struct{}{}
		result = append(result, item)
	}
	return result
}

func toString(v interface{}) string {
	switch t := v.(type) {
	case string:
		return t
	default:
		b, _ := json.Marshal(t)
		return string(b)
	}
}

func ToInt64(v interface{}) (int64, bool) {
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

func ToUint32(v interface{}) (uint32, bool) {
	n, ok := ToInt64(v)
	if !ok || n < 0 {
		return 0, false
	}
	return uint32(n), true
}

func ToInt16(v interface{}) (int16, bool) {
	n, ok := ToInt64(v)
	if !ok || n < -32768 || n > 32767 {
		return 0, false
	}
	return int16(n), true
}

func ToUint8(v interface{}) (uint8, bool) {
	n, ok := ToInt64(v)
	if !ok || n < 0 || n > 255 {
		return 0, false
	}
	return uint8(n), true
}

func ToBool(v interface{}) (bool, bool) {
	switch t := v.(type) {
	case bool:
		return t, true
	case float64:
		return t != 0, true
	case int64:
		return t != 0, true
	case int:
		return t != 0, true
	default:
		return false, false
	}
}
