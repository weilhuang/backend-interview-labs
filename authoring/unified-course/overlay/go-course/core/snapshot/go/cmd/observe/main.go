// 先运行这个完整例子：它不依赖学生函数，直接观察赋值与底层数据的关系。
package main

import (
	"fmt"
	"io"
	"os"
)

func run(out io.Writer) {
	a := []string{"原价", "现货"}
	b := a
	b[0] = "活动价"
	fmt.Fprintf(out, "切片赋值后修改 b：a=%v b=%v\n", a, b)
	c := make([]string, len(a))
	copy(c, a)
	c[0] = "会员价"
	fmt.Fprintf(out, "复制元素后修改 c：a=%v c=%v\n", a, c)
	m := map[string]string{"status": "待付款"}
	n := m
	n["status"] = "已付款"
	fmt.Fprintf(out, "map 赋值后修改 n：m.status=%s\n", m["status"])
}

func main() { run(os.Stdout) }
