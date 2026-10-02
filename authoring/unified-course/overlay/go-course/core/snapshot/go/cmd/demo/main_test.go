package main

import (
	ownership "academy.example/go-ownership"
	"bytes"
	"encoding/json"
	"errors"
	"testing"
)

func TestDemoJSONEndToEnd(t *testing.T) {
	var out bytes.Buffer
	if err := run(&out); err != nil {
		t.Fatal(err)
	}
	var got ownership.DemoResult
	if err := json.Unmarshal(out.Bytes(), &got); err != nil {
		t.Fatal(err)
	}
	if len(got.Live) != 1 || len(got.Snapshot) != 1 {
		t.Fatal("完整调用方应输出live与snapshot各一条订单")
	}
	if got.Live[0].Lines[0].Quantity != 2 || got.Live[0].Metadata["status"] != "已付款" {
		t.Fatal("调用方应确实修改live，不能绕过问题")
	}
	if got.Snapshot[0].Lines[0].Quantity != 1 || got.Snapshot[0].Lines[0].Tags[0] != "原价" || got.Snapshot[0].Metadata["status"] != "待付款" {
		t.Fatal("C3 发货快照被购物车修改污染")
	}
}

var errOutput = errors.New("合成输出故障")

type failedWriter struct{}

func (failedWriter) Write([]byte) (int, error) { return 0, errOutput }
func TestDemoOutputFailure(t *testing.T) {
	if err := run(failedWriter{}); !errors.Is(err, errOutput) {
		t.Fatalf("输出错误须归还调用方，得到%v", err)
	}
}
