package main

import (
	"bytes"
	"testing"
)

func TestObserveBeforeExercise(t *testing.T) {
	var out bytes.Buffer
	run(&out)
	want := "切片赋值后修改 b：a=[活动价 现货] b=[活动价 现货]\n复制元素后修改 c：a=[活动价 现货] c=[会员价 现货]\nmap 赋值后修改 n：m.status=已付款\n"
	if out.String() != want {
		t.Fatalf("观察例子实际=%q，期待=%q", out.String(), want)
	}
}
