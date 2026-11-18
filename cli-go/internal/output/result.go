package output

import (
	"bytes"
	"encoding/json"
	"io"
	"strings"
)

type Field struct {
	Key   string
	Value string
}

type Fields []Field

func (fields Fields) MarshalJSON() ([]byte, error) {
	var result bytes.Buffer
	encoder := json.NewEncoder(&result)
	encoder.SetEscapeHTML(false)
	result.WriteByte('{')
	for i, field := range fields {
		if i != 0 {
			result.WriteByte(',')
		}
		if err := encoder.Encode(field.Key); err != nil {
			return nil, err
		}
		result.WriteByte(':')
		if err := encoder.Encode(field.Value); err != nil {
			return nil, err
		}
	}
	result.WriteByte('}')
	return result.Bytes(), nil
}

func (fields Fields) Table(out io.Writer) error {
	rows := make([][]string, 0, len(fields))
	for _, field := range fields {
		rows = append(rows, []string{field.Key, field.Value})
	}
	return Table(out, []string{"字段", "值"}, rows)
}

func JSON(out io.Writer, value any) error {
	encoder := json.NewEncoder(out)
	encoder.SetEscapeHTML(false)
	encoder.SetIndent("", "  ")
	return encoder.Encode(value)
}

func ResultTable(out io.Writer, raw json.RawMessage) error {
	raw = bytes.TrimSpace(raw)
	if len(raw) > 0 && raw[0] == '{' {
		fields := Fields{}
		if err := objectFields(raw, func(key, value string) {
			fields = append(fields, Field{Key: key, Value: value})
		}); err != nil {
			return err
		}
		return fields.Table(out)
	}
	if len(raw) > 0 && raw[0] == '[' {
		var items []json.RawMessage
		if err := json.Unmarshal(raw, &items); err != nil {
			return err
		}
		for _, item := range items {
			if len(item) == 0 || item[0] != '{' {
				return Table(out, []string{"结果"}, [][]string{{displayValue(raw)}})
			}
		}
		return objectListTable(out, items)
	}
	return Table(out, []string{"结果"}, [][]string{{displayValue(raw)}})
}

func objectListTable(out io.Writer, items []json.RawMessage) error {
	var headers []string
	columns := make(map[string]bool)
	rows := make([][]string, 0, len(items))
	cells := make([]map[string]string, 0, len(items))
	for _, item := range items {
		row := make(map[string]string)
		if err := objectFields(item, func(key, value string) {
			if !columns[key] {
				columns[key] = true
				headers = append(headers, key)
			}
			row[key] = value
		}); err != nil {
			return err
		}
		cells = append(cells, row)
	}
	for _, row := range cells {
		ordered := make([]string, len(headers))
		for i, key := range headers {
			ordered[i] = row[key]
		}
		rows = append(rows, ordered)
	}
	return Table(out, headers, rows)
}

func objectFields(raw json.RawMessage, visit func(key, value string)) error {
	decoder := json.NewDecoder(bytes.NewReader(raw))
	if _, err := decoder.Token(); err != nil {
		return err
	}
	for decoder.More() {
		key, err := decoder.Token()
		if err != nil {
			return err
		}
		var value json.RawMessage
		if err := decoder.Decode(&value); err != nil {
			return err
		}
		visit(key.(string), displayValue(value))
	}
	_, err := decoder.Token()
	return err
}

func displayValue(raw json.RawMessage) string {
	var text string
	if len(raw) > 0 && raw[0] == '"' && json.Unmarshal(raw, &text) == nil {
		return text
	}
	switch string(raw) {
	case "true":
		return "True"
	case "false":
		return "False"
	case "null":
		return "None"
	}
	if len(raw) > 0 && (raw[0] == '{' || raw[0] == '[') {
		return compactWithSpaces(raw)
	}
	return string(raw)
}

func compactWithSpaces(raw json.RawMessage) string {
	var compact bytes.Buffer
	if json.Compact(&compact, raw) != nil {
		return string(raw)
	}
	var value strings.Builder
	var inString, escaped bool
	for _, char := range compact.Bytes() {
		value.WriteByte(char)
		if inString {
			if escaped {
				escaped = false
			} else if char == '\\' {
				escaped = true
			} else if char == '"' {
				inString = false
			}
		} else if char == '"' {
			inString = true
		} else if char == ',' || char == ':' {
			value.WriteByte(' ')
		}
	}
	return value.String()
}
