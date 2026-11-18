package output

import (
	"bytes"
	"encoding/json"
	"strings"
	"testing"
)

func TestTableMatchesPythonForCJKAndBusinessID(t *testing.T) {
	t.Setenv("COLUMNS", "80")
	fields := Fields{
		{Key: "环境", Value: "测试环境"},
		{Key: "账号", Value: "alice"},
		{Key: "中文名", Value: "张三"},
		{Key: "部门", Value: "平台部"},
		{Key: "businessId", Value: "12345678-1234-1234-1234-123456789012"},
	}
	want := `┏━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ 字段       ┃ 值                                   ┃
┡━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┩
│ 环境       │ 测试环境                             │
│ 账号       │ alice                                │
│ 中文名     │ 张三                                 │
│ 部门       │ 平台部                               │
│ businessId │ 12345678-1234-1234-1234-123456789012 │
└────────────┴──────────────────────────────────────┘
`
	var out bytes.Buffer
	if err := fields.Table(&out); err != nil || out.String() != want {
		t.Fatalf("table: %v\n%s", err, &out)
	}
}

func TestResultFormatsPreserveResponseOrderAndData(t *testing.T) {
	t.Setenv("COLUMNS", "80")
	raw := json.RawMessage(`{"result":{"code":0,"data":{"enabled":false}},"success":true,"empty":null,"message":"[OK]"}`)
	wantTable := `┏━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ 字段    ┃ 值                                      ┃
┡━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┩
│ result  │ {"code": 0, "data": {"enabled": false}} │
│ success │ True                                    │
│ empty   │ None                                    │
│ message │ [OK]                                    │
└─────────┴─────────────────────────────────────────┘
`
	var out bytes.Buffer
	if err := ResultTable(&out, raw); err != nil || out.String() != wantTable {
		t.Fatalf("table: %v\n%s", err, &out)
	}
	out.Reset()
	wantJSON := `{
  "result": {
    "code": 0,
    "data": {
      "enabled": false
    }
  },
  "success": true,
  "empty": null,
  "message": "[OK]"
}
`
	if err := JSON(&out, raw); err != nil || out.String() != wantJSON {
		t.Fatalf("JSON: %v\n%s", err, &out)
	}
}

func TestListTableKeepsFirstColumnIDAndWrapsLongFields(t *testing.T) {
	t.Setenv("COLUMNS", "58")
	const id = "12345678-1234-1234-1234-123456789012"
	raw := json.RawMessage(`[{"id":"` + id + `","描述":"人工智能平台长字段描述超过列宽"},{"id":"2","状态":"正常"}]`)
	var out bytes.Buffer
	if err := ResultTable(&out, raw); err != nil {
		t.Fatal(err)
	}
	lines := strings.Split(strings.TrimSuffix(out.String(), "\n"), "\n")
	if !strings.Contains(out.String(), "│ "+id+" │") || len(lines) <= 6 {
		t.Fatalf("expected complete ID and a folded description\n%s", &out)
	}
	for _, line := range lines {
		if cells.StringWidth(line) != cells.StringWidth(lines[0]) || cells.StringWidth(line) > 58 {
			t.Fatalf("misaligned line %q\n%s", line, &out)
		}
	}
}
